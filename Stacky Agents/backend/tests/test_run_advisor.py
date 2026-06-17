"""V1.2 — Tests del advisor de runtime/modelo (services/run_advisor.py)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _db_ready():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()
    yield


def _mk_ticket(ado_id: int = 900) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _mk_exec(ticket_id: int, *, runtime: str, status: str,
             agent_type: str = "developer", cost: float | None = None) -> None:
    from db import session_scope
    from models import AgentExecution

    md: dict = {"runtime": runtime}
    if cost is not None:
        md["claude_telemetry"] = {"total_cost_usd": cost}
    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id, agent_type=agent_type, status=status,
            input_context_json="[]", started_by="test",
            started_at=datetime.utcnow() - timedelta(days=1),
            metadata_json=json.dumps(md),
        )
        session.add(e)
        session.flush()


def test_clear_dominance_recommends_winner():
    from services.run_advisor import advise

    t = _mk_ticket()
    # codex: 9/10 completed; claude: 5/10 completed para developer
    for _ in range(9):
        _mk_exec(t, runtime="codex_cli", status="completed")
    _mk_exec(t, runtime="codex_cli", status="error")
    for _ in range(5):
        _mk_exec(t, runtime="claude_code_cli", status="completed")
    for _ in range(5):
        _mk_exec(t, runtime="claude_code_cli", status="error")

    adv = advise(agent_type="developer")
    assert adv.runtime == "codex_cli"
    assert adv.confidence == "high"
    assert "codex" in adv.reason.lower() or "%" in adv.reason


def test_insufficient_data_defaults():
    from services.run_advisor import advise

    t = _mk_ticket()
    _mk_exec(t, runtime="codex_cli", status="completed")  # solo 1 run (< 5)

    adv = advise(agent_type="developer")
    assert adv.confidence == "default"
    assert adv.runtime == "github_copilot"


def test_no_data_at_all_defaults():
    from services.run_advisor import advise

    adv = advise(agent_type="qa")
    assert adv.confidence == "default"
    assert adv.runtime == "github_copilot"


def test_only_capability_runtimes_considered():
    from services.run_advisor import advise

    t = _mk_ticket()
    for _ in range(6):
        _mk_exec(t, runtime="bogus_runtime", status="completed")
    adv = advise(agent_type="developer")
    # runtime fuera de CAPABILITIES no debe ganar
    assert adv.runtime != "bogus_runtime"


def test_model_never_exceeds_cap():
    from services.run_advisor import advise

    t = _mk_ticket()
    for _ in range(6):
        _mk_exec(t, runtime="claude_code_cli", status="completed")
    adv = advise(agent_type="developer")
    if adv.model:
        assert "opus" not in adv.model.lower()
        assert "fable" not in adv.model.lower()


# ── Endpoint ─────────────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def test_advise_endpoint(client):
    t = _mk_ticket()
    for _ in range(6):
        _mk_exec(t, runtime="codex_cli", status="completed")
    r = client.get("/api/agents/advise?agent_type=developer")
    assert r.status_code == 200
    data = r.get_json()
    assert "runtime" in data and "reason" in data and "confidence" in data
