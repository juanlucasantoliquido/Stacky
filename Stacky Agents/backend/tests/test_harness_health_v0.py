"""V0.4 / V0.5 — Extensión de harness_health: failure_kinds, estimated_cost_runs, active_runs."""
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


def _mk_ticket(ado_id: int = 1) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _mk_exec(tid: int, *, status: str, md: dict) -> int:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        ex = AgentExecution(
            ticket_id=tid, agent_type="developer", status=status,
            input_context_json="{}", started_by="test",
            started_at=datetime.utcnow(),
        )
        ex.metadata_dict = {"runtime": "codex_cli", **md}
        session.add(ex)
        session.flush()
        return ex.id


def test_failure_kinds_breakdown():
    from services.harness_health import compute_health

    tid = _mk_ticket()
    _mk_exec(tid, status="error", md={"failure_kind": "timeout"})
    _mk_exec(tid, status="error", md={"failure_kind": "timeout"})
    _mk_exec(tid, status="needs_review", md={"failure_kind": "contract_failed"})
    _mk_exec(tid, status="completed", md={})  # sin failure_kind

    h = compute_health(window_days=30).to_dict()
    assert h["failure_kinds"] == {"timeout": 2, "contract_failed": 1}
    # por runtime
    assert h["by_runtime"]["codex_cli"]["failure_kinds"] == {
        "timeout": 2, "contract_failed": 1,
    }


def test_estimated_cost_runs_counted():
    from services.harness_health import compute_health

    tid = _mk_ticket()
    _mk_exec(tid, status="completed",
             md={"harness_telemetry": {"total_cost_usd": 0.1, "cost_estimated": True}})
    _mk_exec(tid, status="completed",
             md={"harness_telemetry": {"total_cost_usd": 0.2, "cost_estimated": False}})

    h = compute_health(window_days=30).to_dict()
    assert h["estimated_cost_runs"] == 1
    assert h["by_runtime"]["codex_cli"]["estimated_cost_runs"] == 1


def test_active_runs_field_present():
    from services.harness_health import compute_health
    from services import run_slots

    run_slots._reset_for_tests()
    h = compute_health(window_days=30).to_dict()
    assert h["active_runs"] == 0


def test_old_runs_without_failure_kind_dont_break():
    from services.harness_health import compute_health

    tid = _mk_ticket()
    _mk_exec(tid, status="error", md={})  # run viejo sin la clave
    h = compute_health(window_days=30).to_dict()
    assert h["failure_kinds"] == {}
