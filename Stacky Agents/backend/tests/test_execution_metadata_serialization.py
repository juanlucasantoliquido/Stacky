"""Test C4 (Plan 144 F4) — el endpoint GET de ejecución expone metadata.stall.

El drawer del frontend asume execution.metadata.stall; si el serializer NO
expone ese campo, el bloque de aviso de stall nunca se ve. Este test lo
garantiza contra el endpoint HTTP real (no solo contra to_dict()).
"""
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

_STALL_META = {
    "detected_at": "2026-07-15T10:00:00",
    "last_event_at": "2026-07-15T09:50:00",
    "last_signal": "tool_use:Read",
    "seconds_idle": 600,
    "watchdog_seconds": 600,
    "trust_ok": True,
}


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


def _make_execution_with_stall():
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=9401, project="X", title="plan 144 F4 C4 fixture",
                   ado_state="Active", stacky_status="error")
        session.add(t)
        session.flush()
        ticket_id = t.id
        ex = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status="failed",
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        ex.metadata_dict = {"stall": dict(_STALL_META)}
        session.add(ex)
        session.flush()
        exec_id = ex.id
    return exec_id


def test_get_execution_exposes_stall(client):
    exec_id = _make_execution_with_stall()

    resp = client.get(f"/api/executions/{exec_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "metadata" in body
    stall = body["metadata"].get("stall")
    assert stall is not None
    assert set(stall.keys()) == set(_STALL_META.keys())
    assert stall["trust_ok"] is True
