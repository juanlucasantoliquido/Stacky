"""Tests del check de runs huérfanos en local_diagnostics (Fase P5)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def app_ctx(monkeypatch, tmp_path):
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    (tmp_path / "Agentes" / "outputs").mkdir(parents=True)
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")

    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher
    from services.output_watcher import stop_output_watcher

    app = create_app()
    stop_stale_recovery()
    stop_manifest_watcher()
    stop_output_watcher()
    yield app
    stop_stale_recovery()
    stop_manifest_watcher()
    stop_output_watcher()


def _mk_running_exec(started_minutes_ago: float, agent_type: str = "functional", ado_id: int = 70001) -> int:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        ticket = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
        if ticket is None:
            ticket = Ticket(ado_id=ado_id, project="Test", title=f"t-{ado_id}", ado_state="To Do")
            session.add(ticket)
            session.flush()
        e = AgentExecution(
            ticket_id=ticket.id,
            agent_type=agent_type,
            status="running",
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow() - timedelta(minutes=started_minutes_ago),
        )
        session.add(e)
        session.flush()
        return e.id


def test_orphan_check_ok_when_no_stale(app_ctx, monkeypatch):
    monkeypatch.setenv("STACKY_RUNNING_ALERT_MINUTES", "30")
    _mk_running_exec(started_minutes_ago=2)  # joven

    from services.local_diagnostics import _check_orphan_runs
    res = _check_orphan_runs()
    assert res["status"] == "ok"


def test_orphan_check_warns_on_stale_running(app_ctx, monkeypatch):
    monkeypatch.setenv("STACKY_RUNNING_ALERT_MINUTES", "10")
    _mk_running_exec(started_minutes_ago=45)  # > umbral

    from services.local_diagnostics import _check_orphan_runs
    res = _check_orphan_runs()
    assert res["status"] == "warning"
    assert res["detail"]["running_over_threshold"] >= 1
    assert "huérfano" in res["message"] or "running" in res["message"]
