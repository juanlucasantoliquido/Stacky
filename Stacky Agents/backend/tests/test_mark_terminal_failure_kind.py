"""V0.4 — _mark_terminal sella metadata["failure_kind"] en runs terminados en error."""
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


@pytest.fixture(autouse=True)
def _db_ready():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()
    yield


def _mk_exec(status: str = "running") -> int:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=1, project="P", title="t", ado_state="To Do",
                   stacky_status="idle")
        session.add(t)
        session.flush()
        ex = AgentExecution(
            ticket_id=t.id, agent_type="developer", status=status,
            input_context_json="{}", started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(ex)
        session.flush()
        return ex.id


def _kind(exec_id: int):
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        return session.get(AgentExecution, exec_id).metadata_dict.get("failure_kind")


def test_codex_mark_terminal_classifies_spawn_error():
    from services.codex_cli_runner import _mark_terminal

    eid = _mk_exec()
    _mark_terminal(eid, status="error", error="FileNotFoundError: codex not found")
    assert _kind(eid) == "spawn_error"


def test_claude_mark_terminal_classifies_timeout():
    from services.claude_code_cli_runner import _mark_terminal

    eid = _mk_exec()
    _mark_terminal(eid, status="error", error="session timed out after 7200s")
    assert _kind(eid) == "timeout"


def test_completed_run_has_no_failure_kind():
    from services.codex_cli_runner import _mark_terminal

    eid = _mk_exec()
    _mark_terminal(eid, status="completed", output="ok")
    assert _kind(eid) is None
