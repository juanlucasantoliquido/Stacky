# backend/tests/test_plan271_final_state_resolver.py
"""Plan 271 F1 — Tabla de verdad del resolutor puro final_state_resolver."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from services.final_state_resolver import (
    ALL_FINAL_STATE_REASONS,
    PRECEDENCE,
    REASONS,
    final_state_already_written,
    resolve_final_state,
)


@pytest.fixture(autouse=True)
def _init_app_for_schema():
    from app import create_app

    create_app()


@pytest.fixture(autouse=True)
def clean_db():
    from db import session_scope
    from models import AgentExecution, Ticket

    yield
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()


def _flag(monkeypatch, value: bool):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", value, raising=False)


# ── las 12 filas de la tabla de verdad (§F1) ────────────────────────────────

def test_fila_1_caller_gana_sobre_todo(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state="X", matrix_state="A", role_state="B",
                             employee_state="C", agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == ("X", "caller", "ok")


def test_fila_2_matrix_gana_sin_caller(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state=None, matrix_state="A", role_state="B",
                             employee_state="C", agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == ("A", "matrix", "ok")


def test_fila_3_role_gana_sin_caller_ni_matrix(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state=None, matrix_state=None, role_state="B",
                             employee_state="C", agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == ("B", "role", "ok")


def test_fila_4_role_con_flag_off_no_transiciona(monkeypatch):
    _flag(monkeypatch, False)
    d = resolve_final_state(caller_state=None, matrix_state=None, role_state="B",
                             employee_state="C", agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == (None, "none", "flag_off")


def test_fila_5_employee_config_como_ultimo_recurso(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state=None, matrix_state=None, role_state=None,
                             employee_state="C", agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == ("C", "employee_config", "ok")


def test_fila_6_sin_nada_configurado(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state=None, matrix_state=None, role_state=None,
                             employee_state=None, agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == (None, "none", "no_config")


def test_fila_7_sin_agent_type(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state=None, matrix_state="A", role_state=None,
                             employee_state=None, agent_type=None, final_status="completed")
    assert (d.state, d.source, d.reason) == (None, "none", "no_agent_type")


def test_fila_8_final_status_error(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state=None, matrix_state="A", role_state="B",
                             employee_state="C", agent_type="technical", final_status="error")
    assert (d.state, d.source, d.reason) == (None, "none", "not_ok_status")


def test_fila_9_final_status_needs_review(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state=None, matrix_state="A", role_state="B",
                             employee_state="C", agent_type="technical", final_status="needs_review")
    assert (d.state, d.source, d.reason) == (None, "none", "not_ok_status")


def test_fila_10_caller_ignora_la_flag(monkeypatch):
    _flag(monkeypatch, False)
    d = resolve_final_state(caller_state="X", matrix_state=None, role_state=None,
                             employee_state=None, agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == ("X", "caller", "ok")


def test_fila_11_matrix_ignora_la_flag(monkeypatch):
    """E7 — sin esta fila, apagar la flag de este plan regresionaría el 208."""
    _flag(monkeypatch, False)
    d = resolve_final_state(caller_state=None, matrix_state="A", role_state="B",
                             employee_state="C", agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == ("A", "matrix", "ok")


def test_fila_12_employee_config_ignora_la_flag(monkeypatch):
    _flag(monkeypatch, False)
    d = resolve_final_state(caller_state=None, matrix_state=None, role_state=None,
                             employee_state="C", agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == ("C", "employee_config", "ok")


# ── casos borde ──────────────────────────────────────────────────────────

def test_borde_string_vacio_es_none(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state="", matrix_state="", role_state="",
                             employee_state="", agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == (None, "none", "no_config")


def test_borde_string_solo_blancos_es_none(monkeypatch):
    _flag(monkeypatch, True)
    d = resolve_final_state(caller_state="   ", matrix_state="   ", role_state="   ",
                             employee_state="   ", agent_type="technical", final_status="completed")
    assert (d.state, d.source, d.reason) == (None, "none", "no_config")


# ── estructurales ────────────────────────────────────────────────────────

def test_precedence_congelada():
    assert PRECEDENCE == ("caller", "matrix", "role", "employee_config")


def test_reasons_subconjunto_de_all():
    assert REASONS <= ALL_FINAL_STATE_REASONS


def test_catalogo_completo_27_sin_unknown():
    assert len(ALL_FINAL_STATE_REASONS) == 27
    assert "unknown" not in ALL_FINAL_STATE_REASONS


# ── final_state_already_written ─────────────────────────────────────────

def test_already_written_sin_execution_id_es_false():
    assert final_state_already_written(None) is False


def test_already_written_con_applied_true_es_true():
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as s:
        t = Ticket(ado_id=4242, project="P271", stacky_project_name="P271",
                   title="t", ado_state="New", stacky_status="running")
        s.add(t)
        s.flush()
        e = AgentExecution(ticket_id=t.id, agent_type="technical", status="running",
                           input_context_json="[]", started_by="test")
        e.metadata_dict = {"final_state_outcome": {"applied": True, "to": "To Do"}}
        s.add(e)
        s.flush()
        exec_id = e.id

    assert final_state_already_written(exec_id) is True
