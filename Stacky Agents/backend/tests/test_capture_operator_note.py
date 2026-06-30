"""Plan 47 F2 — Hook capture_operator_note (promoción de nota a memoria)."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_ADO_SEQ = iter(range(820000, 829999))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    yield app


def _seed(*, verdict, note, project="ONP", with_ticket=True):
    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as session:
        ticket_id = None
        if with_ticket:
            tk = Ticket(ado_id=next(_ADO_SEQ), project=project, stacky_project_name=project,
                        title="t", ado_state="Active", work_item_type="Task")
            session.add(tk)
            session.flush()
            ticket_id = tk.id
        ex = AgentExecution(
            ticket_id=ticket_id or 0, agent_type="business", status="needs_review",
            input_context_json="[]", started_by="op", started_at=datetime.utcnow(),
        )
        block = {"verdict": verdict, "note": note, "reviewed_by": "op@x"}
        ex.metadata_dict = {"human_review": block}
        session.add(ex)
        session.flush()
        return ex.id


def test_disabled_returns_none(app_ctx, monkeypatch):
    monkeypatch.delenv("STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED", raising=False)
    from services import post_run_memory
    eid = _seed(verdict="rejected", note="falta batch")
    with patch("services.memory_store.save_observation") as save:
        with app_ctx.app_context():
            assert post_run_memory.capture_operator_note(eid) is None
        save.assert_not_called()


def test_enabled_with_note_saves_operator_note(app_ctx, monkeypatch):
    monkeypatch.setenv("STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED", "true")
    from services import post_run_memory
    eid = _seed(verdict="rejected", note="falta batch")
    with patch("services.memory_store.save_observation", return_value="mem-1") as save:
        with app_ctx.app_context():
            mid = post_run_memory.capture_operator_note(eid)
    assert mid == "mem-1"
    kwargs = save.call_args.kwargs
    assert kwargs["type"] == "operator_note"
    assert "Veredicto: rejected" in kwargs["content"]
    assert "falta batch" in kwargs["content"]


def test_enabled_without_note_skips(app_ctx, monkeypatch):
    monkeypatch.setenv("STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED", "true")
    from services import post_run_memory
    eid = _seed(verdict="approved", note=None)
    with patch("services.memory_store.save_observation") as save:
        with app_ctx.app_context():
            assert post_run_memory.capture_operator_note(eid) is None
        save.assert_not_called()


def test_enabled_no_project_skips(app_ctx, monkeypatch):
    monkeypatch.setenv("STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED", "true")
    from services import post_run_memory
    eid = _seed(verdict="rejected", note="x", with_ticket=False)
    with patch("services.memory_store.save_observation") as save:
        with app_ctx.app_context():
            assert post_run_memory.capture_operator_note(eid) is None
        save.assert_not_called()


def test_operator_note_not_reserved():
    from services import memory_store
    assert "operator_note" not in memory_store.RESERVED_TYPES


def test_pii_redacted(app_ctx, monkeypatch):
    monkeypatch.setenv("STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED", "true")
    from services import post_run_memory
    eid = _seed(verdict="rejected", note="contactar a juan@mail.com")
    with patch("services.memory_store.save_observation", return_value="m"), \
         patch("services.pii_masker.redact_irreversible", return_value="REDACTED") as red:
        with app_ctx.app_context():
            post_run_memory.capture_operator_note(eid)
    red.assert_called_once()


def test_auto_categorization_rejected_reason(app_ctx, monkeypatch):
    monkeypatch.setenv("STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED", "true")
    from services import post_run_memory
    eid = _seed(verdict="rejected", note="razón del fallo")
    with patch("services.memory_store.save_observation", return_value="m") as save:
        with app_ctx.app_context():
            post_run_memory.capture_operator_note(eid)
    assert "rejected_reason" in save.call_args.kwargs["tags"]


def test_auto_categorization_approval_condition(app_ctx, monkeypatch):
    monkeypatch.setenv("STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED", "true")
    from services import post_run_memory
    eid = _seed(verdict="approved_with_notes", note="precondición")
    with patch("services.memory_store.save_observation", return_value="m") as save:
        with app_ctx.app_context():
            post_run_memory.capture_operator_note(eid)
    assert "approval_condition" in save.call_args.kwargs["tags"]
