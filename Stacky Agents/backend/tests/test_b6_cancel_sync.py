"""
Tests de B6 — cancel_execution sincroniza el stacky_status del ticket
(POST /api/executions/<id>/cancel, plan 2026-06-02).

Antes el endpoint marcaba la execution 'cancelled' pero dejaba el ticket en
'running' hasta el próximo reconcile. Ahora dispara ticket_status.on_execution_end
y, para runtimes sin subproceso (github_copilot), el flag cooperativo.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app
    from db import init_db

    app = create_app()
    app.config["TESTING"] = True
    init_db()
    with app.test_client() as c:
        yield c


def _make_running(runtime="github_copilot"):
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import ticket_status as ts

    with session_scope() as session:
        t = Ticket(ado_id=901, project="X", title="run me", ado_state="Active",
                   stacky_status="running")
        session.add(t)
        session.flush()
        ticket_id = t.id
        ex = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status="running",
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        ex.metadata_dict = {"runtime": runtime}
        session.add(ex)
        session.flush()
        exec_id = ex.id
    return ticket_id, exec_id


def test_cancel_marks_cancelled_and_syncs_ticket(client):
    from db import session_scope
    from models import AgentExecution, Ticket

    ticket_id, exec_id = _make_running()

    resp = client.post(f"/api/executions/{exec_id}/cancel")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    with session_scope() as session:
        ex = session.get(AgentExecution, exec_id)
        t = session.get(Ticket, ticket_id)
        assert ex.status == "cancelled"
        assert ex.completed_at is not None
        # B6: el ticket salió de 'running' sin esperar al reaper.
        assert t.stacky_status == "cancelled"


def test_cancel_terminal_returns_409(client):
    from db import session_scope
    from models import AgentExecution

    ticket_id, exec_id = _make_running()
    with session_scope() as session:
        session.get(AgentExecution, exec_id).status = "completed"

    resp = client.post(f"/api/executions/{exec_id}/cancel")
    assert resp.status_code == 409
