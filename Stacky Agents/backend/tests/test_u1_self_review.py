from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@dataclass(frozen=True)
class _FakeReview:
    score: float
    checklist: list[dict]
    skipped_reason: str | None


@pytest.fixture(autouse=True)
def clean_db():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()
    yield
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()


def _seed_execution(status: str = "completed") -> int:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=88001, project="TEST", title="t", ado_state="Active")
        session.add(t)
        session.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status=status,
            input_context_json="[]",
            output="artifact text",
            started_by="test",
        )
        session.add(e)
        session.flush()
        return e.id


def test_self_review_off_does_not_change_status(monkeypatch):
    from services import self_review

    execution_id = _seed_execution("completed")
    monkeypatch.setattr(self_review.config, "STACKY_SELF_REVIEW_MODE", "off")

    result = self_review.apply_to_execution(execution_id=execution_id)
    assert result["applied"] is False


def test_self_review_gate_moves_to_needs_review(monkeypatch):
    from db import session_scope
    from models import AgentExecution
    from services import self_review

    execution_id = _seed_execution("completed")
    monkeypatch.setattr(self_review.config, "STACKY_SELF_REVIEW_MODE", "gate")
    monkeypatch.setattr(self_review.config, "STACKY_SELF_REVIEW_MIN_SCORE", 0.7)
    monkeypatch.setattr(
        self_review,
        "review_artifact",
        lambda **_kwargs: _FakeReview(
            score=0.4,
            checklist=[{"criterion": "c1", "met": False, "evidence": "missing"}],
            skipped_reason=None,
        ),
    )

    result = self_review.apply_to_execution(execution_id=execution_id)
    assert result["status"] == "needs_review"

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        assert row is not None
        assert row.status == "needs_review"
        assert (row.metadata_dict or {}).get("self_review", {}).get("score") == 0.4
