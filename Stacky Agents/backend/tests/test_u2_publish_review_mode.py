from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _init_app_for_schema():
    from app import create_app

    create_app()


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


def _seed_running_execution() -> int:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=99001,
            project="TEST",
            stacky_project_name="TEST",
            title="ticket",
            ado_state="Active",
        )
        session.add(t)
        session.flush()

        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status="running",
            input_context_json="[]",
            started_by="test",
        )
        session.add(e)
        session.flush()
        return e.id


def _seed_completed_hold_execution() -> int:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=99002,
            project="TEST",
            stacky_project_name="TEST",
            title="ticket hold",
            ado_state="Active",
        )
        session.add(t)
        session.flush()

        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status="completed",
            input_context_json="[]",
            started_by="test",
        )
        e.metadata_dict = {
            "publish_hold": {
                "reason": "review_mode",
                "artifacts": ["outputs/comment.html"],
                "created_at": "2026-01-01T00:00:00Z",
            },
            "agent_filename": "Developer.agent.md",
        }
        session.add(e)
        session.flush()
        return e.id


def test_close_execution_sets_publish_hold_in_review_mode(monkeypatch):
    from db import session_scope
    from models import AgentExecution
    from services import agent_completion_internal as aci

    execution_id = _seed_running_execution()

    monkeypatch.setattr(aci, "_resolve_publish_mode", lambda **_kwargs: "review")
    monkeypatch.setattr(aci, "_attempt_publish", lambda **_kwargs: pytest.fail("publish no debe ejecutarse en review"))

    result = aci.close_execution_with_publish(
        execution_id=execution_id,
        triggered_by="test",
        final_status="completed",
        html_output_path="outputs/comment.html",
        user="tester",
    )

    assert result.ok is True
    assert result.publish.get("reason") == "review_mode_hold"

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        assert row is not None
        hold = (row.metadata_dict or {}).get("publish_hold")
        assert isinstance(hold, dict)
        assert hold.get("reason") == "review_mode"
        assert hold.get("artifacts") == ["outputs/comment.html"]


def test_publish_to_ado_requires_hold(client):
    execution_id = _seed_running_execution()

    resp = client.post(f"/api/executions/{execution_id}/publish-to-ado", json={})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["ok"] is False
    assert body["reason"] == "publish_hold_missing"


def test_publish_execution_from_review_releases_hold(monkeypatch):
    from db import session_scope
    from models import AgentExecution
    from services import agent_completion_internal as aci

    execution_id = _seed_completed_hold_execution()

    monkeypatch.setattr(
        aci,
        "_attempt_publish",
        lambda **_kwargs: {"ok": True, "event": "publish.succeeded"},
    )
    monkeypatch.setattr(aci, "_resolve_transition_state_from_config", lambda **_kwargs: "Done")
    monkeypatch.setattr(
        aci,
        "_attempt_state_change",
        lambda **_kwargs: {"ok": True, "to": "Done", "ado_id": 99002},
    )

    result = aci.publish_execution_from_review(execution_id=execution_id, triggered_by="operator")
    assert result["ok"] is True
    assert result["ado_state_change"].get("ok") is True

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        assert row is not None
        hold = (row.metadata_dict or {}).get("publish_hold")
        assert isinstance(hold, dict)
        assert hold.get("released_by") == "operator"
        assert isinstance(hold.get("released_at"), str)
