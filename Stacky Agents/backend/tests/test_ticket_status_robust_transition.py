"""Tests de transición terminal garantizada e inmediata (Plan 144 F1, cierra D3).

Con F0, needs_review ya no estalla `set_status`. F1 agrega el cinturón de
seguridad: on_execution_end NUNCA deja el ticket en 'running', ni siquiera
ante un final_status desconocido (defensa en profundidad).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app  # noqa: F401 — fuerza el wiring de la app/DB
    from db import init_db

    create_app()
    init_db()
    yield


def _new_ticket(**kw):
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=kw.pop("ado_id", 9101),
            project=kw.pop("project", "X"),
            title=kw.pop("title", "plan 144 F1 fixture"),
            ado_state=kw.pop("ado_state", "Active"),
            stacky_status=kw.pop("stacky_status", "running"),
            **kw,
        )
        session.add(t)
        session.flush()
        return t.id


def test_needs_review_end_transitions_immediately(db):
    from services import ticket_status

    tid = _new_ticket()
    ticket_status.on_execution_end(
        ticket_id=tid, execution_id=1, final_status="needs_review", agent_type="developer",
    )
    assert ticket_status.get_current_status(tid) == "needs_review"


def test_unknown_status_coerces_to_error(db):
    from services import ticket_status

    tid = _new_ticket()
    ticket_status.on_execution_end(
        ticket_id=tid, execution_id=2, final_status="weird_state", agent_type="developer",
    )
    assert ticket_status.get_current_status(tid) == "error"


def test_error_end_unchanged(db):
    from services import ticket_status

    tid = _new_ticket()
    ticket_status.on_execution_end(
        ticket_id=tid, execution_id=3, final_status="error", agent_type="developer",
    )
    assert ticket_status.get_current_status(tid) == "error"


def test_no_ticket_is_noop(db, monkeypatch):
    from services import ticket_status

    # Hermético (C2 crítica): on_execution_end también corre _run_post_hooks;
    # aislar de hooks registrados por otros módulos al importar.
    monkeypatch.setattr(ticket_status, "_POST_HOOKS", [])
    monkeypatch.setattr(ticket_status, "_PRE_HOOKS", [])
    ticket_status.on_execution_end(
        ticket_id=999999, execution_id=4, final_status="error", agent_type="developer",
    )  # no debe lanzar
