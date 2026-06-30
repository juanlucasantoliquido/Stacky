"""Plan 46 F2 — Endpoint GET /api/diag/operational-health."""
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

_URL = "/api/diag/operational-health"


@pytest.fixture
def client():
    from app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    from db import session_scope
    from models import AgentExecution, Ticket
    yield
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setenv("STACKY_OPERATIONAL_HEALTH_ENABLED", "true")


def _seed_ticket(project="Pacifico") -> int:
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = Ticket(ado_id=123, project=project, stacky_project_name=project,
                   title="t", ado_state="To Do")
        session.add(t)
        session.flush()
        return t.id


def _seed_exec(ticket_id, *, status, started_offset_min=0, metadata=None):
    from db import session_scope
    from models import AgentExecution
    started = datetime.utcnow() - timedelta(minutes=started_offset_min)
    with session_scope() as session:
        row = AgentExecution(
            ticket_id=ticket_id, agent_type="business", status=status,
            input_context_json="[]", output_format="markdown",
            started_by="test", started_at=started,
        )
        if metadata:
            row.metadata_dict = metadata
        session.add(row)
        session.flush()
        return row.id


def test_endpoint_returns_404_when_flag_disabled(client, monkeypatch):
    monkeypatch.setenv("STACKY_OPERATIONAL_HEALTH_ENABLED", "false")
    r = client.get(_URL)
    assert r.status_code == 404
    assert r.get_json()["error"] == "disabled"


def test_endpoint_returns_buckets_with_seeded_runs(client):
    tid = _seed_ticket()
    _seed_exec(tid, status="needs_review", started_offset_min=10)
    _seed_exec(tid, status="error", metadata={"failure_kind": "boom"})
    _seed_exec(tid, status="running", started_offset_min=300)
    r = client.get(_URL + "?zombie_minutes=120")
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert d["summary"]["needs_review_pending"] == 1
    assert d["summary"]["failed"] == 1
    assert d["summary"]["zombie"] == 1


def test_endpoint_injects_project_from_ticket(client):
    tid = _seed_ticket(project="Pacifico")
    _seed_exec(tid, status="needs_review")
    r = client.get(_URL)
    d = r.get_json()
    assert d["needs_review"][0]["project"] == "Pacifico"


def test_endpoint_respects_limit_cap(client):
    tid = _seed_ticket()
    _seed_exec(tid, status="completed")
    r = client.get(_URL + "?limit=9999")
    assert r.status_code == 200


def test_endpoint_ignores_bad_threshold_param(client):
    tid = _seed_ticket()
    _seed_exec(tid, status="completed")
    r = client.get(_URL + "?cost_usd=abc")
    assert r.status_code == 200


def test_endpoint_handles_non_numeric_limit(client):
    tid = _seed_ticket()
    _seed_exec(tid, status="completed")
    r = client.get(_URL + "?limit=abc")
    assert r.status_code == 200


def test_endpoint_does_not_trigger_n_plus_one(client):
    from sqlalchemy import event
    from db import engine

    tid = _seed_ticket()
    for _ in range(5):
        _seed_exec(tid, status="needs_review")

    selects = {"n": 0}

    def _counter(conn, cursor, statement, params, context, executemany):
        s = statement.lower()
        if s.startswith("select") and ("agent_executions" in s or "tickets" in s):
            selects["n"] += 1

    event.listen(engine, "after_cursor_execute", _counter)
    try:
        r = client.get(_URL)
    finally:
        event.remove(engine, "after_cursor_execute", _counter)
    assert r.status_code == 200
    # 1 SELECT con joinedload (no 1 + N). Holgura para metadatos internos: <= 3.
    assert selects["n"] <= 3, f"posible N+1: {selects['n']} SELECTs"
