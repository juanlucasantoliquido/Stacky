"""Tests del esquema de metadata['stall'] + correlación de trust (Plan 144 F4,
cierra D2). Unit puro: no spawnea el CLI ni corre streaming real."""
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

_EXPECTED_STALL_KEYS = {
    "detected_at", "last_event_at", "last_signal",
    "seconds_idle", "watchdog_seconds", "trust_ok",
}


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app  # noqa: F401 — fuerza el wiring de la app/DB
    from db import init_db

    create_app()
    init_db()
    yield


def _new_ticket_and_exec(**kw):
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=kw.pop("ado_id", 9301),
            project="X",
            title="plan 144 F4 fixture",
            ado_state="Active",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        ticket_id = t.id
        ex = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status="running",
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(ex)
        session.flush()
        execution_id = ex.id
    return ticket_id, execution_id


def _stall_meta_keys_from_source(mod) -> set[str]:
    """Escanea el literal `stall_meta = {...}` del módulo (misma técnica de
    escaneo de fuente que F0 usa para final_status — evita tautología)."""
    src = inspect.getsource(mod)
    m = re.search(r"stall_meta\s*=\s*\{([^}]*)\}", src, re.DOTALL)
    assert m, f"no se encontró literal stall_meta = {{...}} en {mod.__name__}"
    body = m.group(1)
    return set(re.findall(r'"(\w+)":', body))


def test_stall_meta_has_six_keys():
    from services import claude_code_cli_runner

    keys = _stall_meta_keys_from_source(claude_code_cli_runner)
    assert keys == _EXPECTED_STALL_KEYS


def test_trust_ok_from_persisted_untrusted(db):
    from services import claude_code_cli_runner as runner

    ticket_id, execution_id = _new_ticket_and_exec(ado_id=9302)
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        row.metadata_dict = {"trust": {"trusted": False, "project_key": "C:/fake/ws"}}

    trust_ok = runner._derive_stall_trust_ok(execution_id, None)
    assert trust_ok is False


def test_trust_ok_indeterminate_is_none(db):
    from services import claude_code_cli_runner as runner

    ticket_id, execution_id = _new_ticket_and_exec(ado_id=9303)
    # Sin key "trust" persistida y sin cwd → indeterminado, NUNCA False.
    trust_ok = runner._derive_stall_trust_ok(execution_id, None)
    assert trust_ok is None
