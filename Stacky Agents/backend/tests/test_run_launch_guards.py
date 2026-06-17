"""V0.2 / V0.3 — Integración del launch: guard de duplicados (409) y cap de concurrencia (429)."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()

    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher
    from services import run_slots

    run_slots._reset_for_tests()
    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()
    run_slots._reset_for_tests()


def _mk_ticket(ado_id: int = 500) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _mk_active_exec(tid: int, agent_type: str = "developer") -> int:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        ex = AgentExecution(
            ticket_id=tid, agent_type=agent_type, status="running",
            input_context_json="{}", started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(ex)
        session.flush()
        return ex.id


def test_duplicate_run_returns_409(client, monkeypatch):
    tid = _mk_ticket()
    active_id = _mk_active_exec(tid)

    # run_agent no debería siquiera llamarse en el path 409
    import agent_runner
    monkeypatch.setattr(agent_runner, "run_agent",
                        lambda **kw: pytest.fail("run_agent no debe ejecutarse"))

    r = client.post("/api/agents/run", json={
        "agent_type": "developer", "ticket_id": tid, "runtime": "github_copilot",
    })
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "duplicate_run"
    assert body["active_execution_id"] == active_id


def test_force_bypasses_duplicate_guard(client, monkeypatch):
    tid = _mk_ticket()
    _mk_active_exec(tid)

    import agent_runner
    monkeypatch.setattr(agent_runner, "run_agent", lambda **kw: 9999)

    r = client.post("/api/agents/run", json={
        "agent_type": "developer", "ticket_id": tid,
        "runtime": "github_copilot", "force": True,
    })
    assert r.status_code == 202
    assert r.get_json()["execution_id"] == 9999


def test_max_concurrent_returns_429(client, monkeypatch):
    from config import config
    from services import run_slots

    tid = _mk_ticket()
    monkeypatch.setattr(config, "STACKY_MAX_CONCURRENT_RUNS", 1, raising=False)
    # ocupar el único slot
    assert run_slots.try_acquire() is True

    import agent_runner
    monkeypatch.setattr(agent_runner, "run_agent",
                        lambda **kw: pytest.fail("no debe spawnear con slots llenos"))

    r = client.post("/api/agents/run", json={
        "agent_type": "developer", "ticket_id": tid,
        "runtime": "claude_code_cli", "vscode_agent_filename": "Dev.agent.md",
    })
    assert r.status_code == 429
    assert r.get_json()["error"] == "max_concurrent_runs"


def test_copilot_does_not_consume_slot(client, monkeypatch):
    from config import config
    from services import run_slots

    tid = _mk_ticket()
    monkeypatch.setattr(config, "STACKY_MAX_CONCURRENT_RUNS", 1, raising=False)
    assert run_slots.try_acquire() is True  # slot lleno

    import agent_runner
    monkeypatch.setattr(agent_runner, "run_agent", lambda **kw: 7777)

    # copilot no usa subproceso CLI → no chequea slot → 202 aunque esté lleno
    r = client.post("/api/agents/run", json={
        "agent_type": "developer", "ticket_id": tid, "runtime": "github_copilot",
    })
    assert r.status_code == 202
