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


def _seed_ticket_with_execs(*, ado_id: int, project_name: str, costs: list[dict], started_at: datetime | None = None) -> int:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project=project_name,
            stacky_project_name=project_name,
            title=f"ticket-{ado_id}",
            ado_state="Active",
        )
        session.add(t)
        session.flush()

        when = started_at or datetime.utcnow()
        for c in costs:
            e = AgentExecution(
                ticket_id=t.id,
                agent_type="developer",
                status="completed",
                input_context_json="[]",
                started_by="test",
                started_at=when,
            )
            md = {}
            if "reported" in c:
                md["claude_telemetry"] = {"total_cost_usd": c["reported"]}
            if "estimated" in c:
                md["cost_estimated"] = c["estimated"]
            e.metadata_dict = md
            session.add(e)
        session.flush()
        return t.id


def test_ticket_costs_returns_aggregated_values(client):
    t1 = _seed_ticket_with_execs(
        ado_id=91001,
        project_name="PRJ-A",
        costs=[{"reported": 0.2}, {"estimated": 0.3}],
    )
    t2 = _seed_ticket_with_execs(
        ado_id=91002,
        project_name="PRJ-A",
        costs=[{"reported": 0.5}],
    )

    resp = client.get(f"/api/metrics/ticket-costs?ticket_ids={t1},{t2}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    items = body["items"]
    assert len(items) == 2

    by_ticket = {x["ticket_id"]: x for x in items}
    assert by_ticket[t1]["total_usd"] == pytest.approx(0.5)
    assert by_ticket[t1]["estimated"] is True
    assert by_ticket[t2]["total_usd"] == pytest.approx(0.5)


def test_ticket_costs_requires_ticket_ids(client):
    resp = client.get("/api/metrics/ticket-costs")
    assert resp.status_code == 400


def test_project_costs_rollup_groups_by_month_and_project(client):
    now = datetime.utcnow()
    _seed_ticket_with_execs(
        ado_id=92001,
        project_name="PRJ-A",
        costs=[{"reported": 1.0}],
        started_at=now,
    )
    _seed_ticket_with_execs(
        ado_id=92002,
        project_name="PRJ-B",
        costs=[{"estimated": 0.4}],
        started_at=now - timedelta(days=35),
    )

    resp = client.get("/api/metrics/project-costs?months=3")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["months"] == 3
    assert len(body["series"]) >= 2
    assert any(row["project"] == "PRJ-A" and row["total_usd"] == pytest.approx(1.0) for row in body["series"])
    assert any(row["project"] == "PRJ-B" and row["estimated"] is True for row in body["series"])
