"""V0.2 — Tests del guard anti-duplicados (services/run_guard.py)."""
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


def _mk_ticket(ado_id: int = 100) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _mk_exec(ticket_id: int, *, status: str, agent_type: str = "developer") -> int:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        ex = AgentExecution(
            ticket_id=ticket_id, agent_type=agent_type, status=status,
            input_context_json="{}",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(ex)
        session.flush()
        return ex.id


def test_active_run_blocks():
    from db import session_scope
    from services.run_guard import find_active_run

    tid = _mk_ticket()
    _mk_exec(tid, status="running")
    with session_scope() as session:
        found = find_active_run(session, tid, "developer")
        assert found is not None


def test_preparing_blocks():
    from db import session_scope
    from services.run_guard import find_active_run

    tid = _mk_ticket()
    _mk_exec(tid, status="preparing")
    with session_scope() as session:
        assert find_active_run(session, tid, "developer") is not None


def test_terminal_does_not_block():
    from db import session_scope
    from services.run_guard import find_active_run

    tid = _mk_ticket()
    for st in ("completed", "error", "needs_review"):
        _mk_exec(tid, status=st)
    with session_scope() as session:
        assert find_active_run(session, tid, "developer") is None


def test_other_agent_type_does_not_block():
    from db import session_scope
    from services.run_guard import find_active_run

    tid = _mk_ticket()
    _mk_exec(tid, status="running", agent_type="qa")
    with session_scope() as session:
        # developer no está bloqueado por un run activo de qa
        assert find_active_run(session, tid, "developer") is None
        # pero qa sí
        assert find_active_run(session, tid, "qa") is not None


def test_other_ticket_does_not_block():
    from db import session_scope
    from services.run_guard import find_active_run

    tid1 = _mk_ticket(ado_id=100)
    tid2 = _mk_ticket(ado_id=200)
    _mk_exec(tid1, status="running")
    with session_scope() as session:
        assert find_active_run(session, tid2, "developer") is None
