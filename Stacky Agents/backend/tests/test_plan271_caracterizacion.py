# backend/tests/test_plan271_caracterizacion.py
"""Plan 271 F0 — Caracterización del bug reportado.

Describen el comportamiento ESPERADO por el operador. Al escribirlos (antes de
F1..F8) DEBEN FALLAR LOS CUATRO. Si alguno pasa en verde acá, el diagnóstico del
plan está equivocado y hay que rehacerlo antes de tocar producción.
"""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from tests.plan271_helpers import FakeProvider, close_sin_html, patch_motor_a


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


PERFIL_SOLO_ROL = {"tracker_state_machine": {"technical": {
    "input_states": ["New"], "in_progress": "Doing", "next_state_ok": "To Do",
}}}


def test_rc1_rol_sin_matriz_deberia_transicionar(monkeypatch):
    """RC-1: el operador configuró tracker_state_machine.technical.next_state_ok
    = 'To Do' desde StatesConfigPage (nivel ROL, sin by_work_item_type).
    Hoy completion_state devuelve skipped/no_matrix_cell. Debe transicionar."""
    from services import completion_state
    prov = patch_motor_a(monkeypatch, profile=PERFIL_SOLO_ROL, work_item_type=None)
    out = completion_state.maybe_apply_state_transition(
        {"ticket_id": 1, "execution_id": 9, "final_status": "completed",
         "agent_type": "technical"}
    )
    assert out.get("ok") is True, f"esperaba transición, obtuve {out}"
    assert out.get("to") == "To Do"
    assert prov.writes == [("4242", "To Do")]


def test_rc1_celda_parcial_no_debe_enterrar_el_nivel_rol(monkeypatch):
    """RC-1 agravante 2: by_work_item_type['Bug'] con SOLO in_progress hace que
    resolve_task_state_plan devuelva source='matrix' y final_ok=None
    (task_states.py:107-108). El next_state_ok de rol queda inalcanzable."""
    from services import completion_state
    perfil = {"tracker_state_machine": {"technical": {
        "next_state_ok": "To Do",
        "by_work_item_type": {"Bug": {"in_progress": "Doing"}},
    }}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type="Bug")
    out = completion_state.maybe_apply_state_transition(
        {"ticket_id": 1, "execution_id": 9, "final_status": "completed",
         "agent_type": "technical"}
    )
    assert out.get("ok") is True, f"la celda parcial enterró el nivel rol: {out}"
    assert prov.writes == [("4242", "To Do")]


def test_rc2_sin_html_no_debe_bloquear_la_transicion(monkeypatch):
    """RC-2: cierre completed sin html_output_path (nada que publicar) NO debe
    impedir el cambio de estado configurado."""
    res = close_sin_html(monkeypatch, transition_state="To Do")
    assert res.ado_state_change.get("ok") is True, \
        f"publish sin nada que publicar no debe gatear el estado: {res.ado_state_change}"


def test_e3_el_escritor_rutea_por_provider():
    """E-3: _attempt_state_change debe rutear por el router del plan 270 para
    tener paridad ADO/GitLab. Forma POSITIVA a propósito: el camino legacy con
    la flag OFF conserva el import de AdoClient y NO puede prohibirse.

    [v6, E23] Busca `resolve_state_writer`, NO `get_tracker_provider`: ese
    segundo nombre es justo lo que test_5_centinela_del_residuo_s5 del plan 270
    prohíbe dentro de esta función (F3-bis-0). Si esta aserción buscara
    "get_tracker_provider", F0 sólo se pondría verde violando el centinela del
    270 — la misma trampa que E23 encontró en el diff de la v5.
    """
    from services import agent_completion_internal as aci
    src = inspect.getsource(aci._attempt_state_change)
    assert "resolve_state_writer" in src, "el escritor de estado sigue siendo ADO-only"
