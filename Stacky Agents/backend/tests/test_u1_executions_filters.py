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


def _seed_ticket(ado_id: int = 99901) -> int:
    from db import session_scope
    from models import Ticket
    from services.project_context import resolve_project_context

    # El endpoint /executions scopea por el proyecto activo cuando no se pasa
    # ?project (igual que hace el frontend, que siempre manda project). Sembramos
    # el ticket dentro del proyecto activo para validar los filtros de status/days
    # sin que el scope por defecto los descarte.
    ctx = resolve_project_context()
    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project=getattr(ctx, "tracker_project", "TEST"),
            stacky_project_name=getattr(ctx, "stacky_project_name", None),
            title="ticket",
            ado_state="Active",
        )
        session.add(t)
        session.flush()
        return t.id


def _seed_exec(ticket_id: int, status: str, started_at: datetime) -> None:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=started_at,
        )
        session.add(e)


def test_executions_supports_comma_multi_status(client):
    ticket_id = _seed_ticket()
    now = datetime.utcnow()
    _seed_exec(ticket_id, "needs_review", now - timedelta(minutes=1))
    _seed_exec(ticket_id, "error", now - timedelta(minutes=2))
    _seed_exec(ticket_id, "completed", now - timedelta(minutes=3))

    resp = client.get("/api/executions?status=needs_review,error&limit=10")
    assert resp.status_code == 200
    data = resp.get_json()
    statuses = sorted(x["status"] for x in data)
    assert statuses == ["error", "needs_review"]


def test_executions_days_filter_excludes_old_rows(client):
    ticket_id = _seed_ticket(ado_id=99902)
    now = datetime.utcnow()
    _seed_exec(ticket_id, "error", now - timedelta(hours=2))
    _seed_exec(ticket_id, "error", now - timedelta(days=10))

    resp = client.get("/api/executions?status=error&days=1&limit=10")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
