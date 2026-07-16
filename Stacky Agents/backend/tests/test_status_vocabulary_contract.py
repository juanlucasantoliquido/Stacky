"""Tests de contrato del vocabulario único de estados (Plan 144 F0, cierra D4).

Antes de este fix, agent_completion.TERMINAL_STATUSES incluía "needs_review"
pero ticket_status.VALID_STATUSES no, así que set_status(tid, "needs_review")
lanzaba ValueError y estrancaba el ticket en 'running'. Este módulo reconcilia
ambos vocabularios en services.status_vocabulary (fuente única de verdad).
"""
from __future__ import annotations

import inspect
import os
import re
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
            ado_id=kw.pop("ado_id", 9001),
            project=kw.pop("project", "X"),
            title=kw.pop("title", "plan 144 F0 fixture"),
            ado_state=kw.pop("ado_state", "Active"),
            stacky_status=kw.pop("stacky_status", "running"),
            **kw,
        )
        session.add(t)
        session.flush()
        return t.id


def test_terminal_subset_of_valid_ticket():
    """Invariante central: todo estado terminal de completion es aceptado por el ticket."""
    from services.status_vocabulary import TERMINAL_STATUSES, VALID_TICKET_STATUSES

    assert TERMINAL_STATUSES <= VALID_TICKET_STATUSES


def test_ticket_status_valid_is_shared():
    from services import ticket_status
    from services.status_vocabulary import VALID_TICKET_STATUSES

    assert ticket_status.VALID_STATUSES == VALID_TICKET_STATUSES


def test_completion_terminal_is_shared():
    from services.agent_completion import TERMINAL_STATUSES as A
    from services.status_vocabulary import TERMINAL_STATUSES as B

    assert A is B  # misma referencia, no copia


def test_set_status_accepts_needs_review(db):
    from services import ticket_status

    tid = _new_ticket()
    ticket_status.set_status(tid, "needs_review", changed_by="test")
    assert ticket_status.get_current_status(tid) == "needs_review"


def test_set_status_rejects_garbage(db):
    from services import ticket_status

    tid = _new_ticket()
    with pytest.raises(ValueError):
        ticket_status.set_status(tid, "banana", changed_by="test")


def _literals(mod) -> set[str]:
    src = inspect.getsource(mod)
    return set(re.findall(r'final_status\s*=\s*"([a-z_]+)"', src))


def test_all_runner_final_status_literals_subset():
    """Guarda proactiva de D4: todo literal final_status="..." de los runners
    debe pertenecer al vocabulario único (los paths dinámicos los cubre F1)."""
    from services import claude_code_cli_runner, codex_cli_runner
    from services.status_vocabulary import VALID_TICKET_STATUSES

    found = _literals(claude_code_cli_runner) | _literals(codex_cli_runner)
    assert found, "esperaba al menos un literal final_status en los runners"
    assert found <= VALID_TICKET_STATUSES, (
        f"literales fuera del vocabulario: {sorted(found - VALID_TICKET_STATUSES)}"
    )
