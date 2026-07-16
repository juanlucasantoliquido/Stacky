"""Tests de paridad de runtimes (Plan 144 F5).

Deja constancia ejecutable de que D3/D4 (vocabulario de estados + transición
terminal) aplican idénticos a los 3 runtimes, y que D1/D2 (trust/stall,
Claude-específicos) degradan de forma controlada en Codex/Copilot.
"""
from __future__ import annotations

import inspect
import os
import re
import sys
from datetime import datetime
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
            ado_id=kw.pop("ado_id", 9501),
            project="X",
            title="plan 144 F5 fixture",
            ado_state="Active",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        return t.id


def test_codex_runaway_needs_review_transitions(db):
    """Prueba que el fix D4 (F0) cubre la ruta que Codex usa en runaway
    (codex_cli_runner.py, on_execution_end(final_status="needs_review"))."""
    from services import ticket_status

    tid = _new_ticket(ado_id=9501)
    ticket_status.on_execution_end(
        ticket_id=tid, execution_id=1, final_status="needs_review", agent_type="developer",
    )
    assert ticket_status.get_current_status(tid) == "needs_review"


def test_trust_preflight_is_claude_only():
    """D1 es específico de Claude CLI: Codex no debe referenciar el módulo de trust."""
    from services import codex_cli_runner

    assert "claude_workspace_trust" not in inspect.getsource(codex_cli_runner)


def _stall_meta_keys_from_source(mod) -> set[str]:
    src = inspect.getsource(mod)
    m = re.search(r"stall_meta\s*=\s*\{([^}]*)\}", src, re.DOTALL)
    assert m, f"no se encontró literal stall_meta = {{...}} en {mod.__name__}"
    body = m.group(1)
    return set(re.findall(r'"(\w+)":', body))


def test_stall_schema_parity():
    from services import claude_code_cli_runner, codex_cli_runner

    claude_keys = _stall_meta_keys_from_source(claude_code_cli_runner)
    codex_keys = _stall_meta_keys_from_source(codex_cli_runner)
    assert claude_keys == codex_keys
