# backend/tests/test_plan271_role_fallback.py
"""Plan 271 F2 — el motor A honra tracker_state_machine.<rol>.next_state_ok de
NIVEL ROL cuando la matriz no define estado final. Cierra RC-1."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from tests.plan271_helpers import FakeProvider, patch_motor_a


@pytest.fixture(autouse=True)
def _init_app_for_schema():
    from app import create_app

    create_app()


def _flag(monkeypatch, value: bool):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", value, raising=False)


def _ev(**over):
    base = {"ticket_id": 1, "execution_id": 9, "final_status": "completed", "agent_type": "technical"}
    base.update(over)
    return base


def test_1_rol_sin_matriz_transiciona(monkeypatch):
    """El bug reportado: nivel rol solo, sin by_work_item_type."""
    from services import completion_state
    _flag(monkeypatch, True)
    perfil = {"tracker_state_machine": {"technical": {
        "input_states": ["New"], "in_progress": "Doing", "next_state_ok": "To Do",
    }}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type=None)
    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("ok") is True
    assert out.get("to") == "To Do"
    assert prov.writes == [("4242", "To Do")]


def test_2_matriz_completa_gana_sobre_rol_distinto(monkeypatch):
    from services import completion_state
    _flag(monkeypatch, True)
    perfil = {"tracker_state_machine": {"technical": {
        "next_state_ok": "To Do",  # nivel rol, DEBE perder frente a la celda
        "by_work_item_type": {"Bug": {"in_progress": "En curso Bug", "next_state_ok": "Bug Done"}},
    }}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type="Bug")
    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("ok") is True
    assert out.get("to") == "Bug Done"
    assert prov.writes == [("4242", "Bug Done")]


def test_3_matriz_configurada_pero_work_item_type_null_cae_a_rol(monkeypatch):
    from services import completion_state
    _flag(monkeypatch, True)
    perfil = {"tracker_state_machine": {"technical": {
        "next_state_ok": "To Do",
        "by_work_item_type": {"Bug": {"in_progress": "En curso Bug", "next_state_ok": "Bug Done"}},
    }}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type=None)
    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("ok") is True
    assert out.get("to") == "To Do"
    assert prov.writes == [("4242", "To Do")]


def test_4_celda_parcial_no_entierra_el_nivel_rol(monkeypatch):
    """C13 — by_work_item_type['Bug'] con SOLO in_progress: source='matrix' con
    final_ok=None. El next_state_ok de rol tiene que seguir alcanzable."""
    from services import completion_state
    _flag(monkeypatch, True)
    perfil = {"tracker_state_machine": {"technical": {
        "next_state_ok": "To Do",
        "by_work_item_type": {"Bug": {"in_progress": "Doing"}},
    }}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type="Bug")
    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("ok") is True
    assert out.get("to") == "To Do"
    assert prov.writes == [("4242", "To Do")]


def test_5_sin_matriz_ni_rol_no_config(monkeypatch):
    from services import completion_state
    _flag(monkeypatch, True)
    prov = patch_motor_a(monkeypatch, profile={}, work_item_type=None)
    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("skipped") is True
    assert out.get("reason") == "no_config"
    assert out.get("reason")
    assert prov.writes == []


def test_6_flag_off_solo_rol_no_transiciona(monkeypatch):
    """E7 — la CONDUCTA es idéntica a hoy (no se escribe), pero el `reason` NO
    lo es: hoy ese camino emite `no_matrix_cell`; acá pasa a `flag_off`."""
    from services import completion_state
    _flag(monkeypatch, False)
    perfil = {"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type=None)
    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("skipped") is True
    assert out.get("reason") == "flag_off"
    assert prov.writes == []


def test_6bis_flag_off_pero_matriz_con_final_transiciona_igual(monkeypatch):
    """E7 fila 11 — sin este caso, apagar la flag de ESTE plan regresionaría el
    plan 208: la matriz no depende de STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED."""
    from services import completion_state
    _flag(monkeypatch, False)
    perfil = {"tracker_state_machine": {"technical": {
        "by_work_item_type": {"Bug": {"in_progress": "En curso Bug", "next_state_ok": "Bug Done"}},
    }}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type="Bug")
    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("ok") is True
    assert out.get("to") == "Bug Done"
    assert prov.writes == [("4242", "Bug Done")]


def test_7_origin_guard_sigue_bloqueando(monkeypatch):
    from services import completion_state
    _flag(monkeypatch, True)
    perfil = {"tracker_state_machine": {"technical": {
        "input_states": ["New"], "in_progress": "Doing", "next_state_ok": "To Do",
    }}}
    prov = FakeProvider(current_state="Cerrado a mano")
    patch_motor_a(monkeypatch, profile=perfil, work_item_type=None, provider=prov)
    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("skipped") is True
    assert out.get("reason") == "human_moved_out_of_flow"
    assert prov.writes == []


def test_8_needs_review_no_transiciona(monkeypatch):
    from services import completion_state
    _flag(monkeypatch, True)
    perfil = {"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type=None)
    out = completion_state.maybe_apply_state_transition(_ev(final_status="needs_review"))
    assert out.get("skipped") is True
    assert out.get("reason") == "not_ok_status"
    assert prov.writes == []


def test_9_centinela_runtime_state_not_applicable(monkeypatch):
    """Defensa en profundidad: con el contrato REAL de resolve_final_state este
    camino es inalcanzable (decision.state siempre es matrix_state o role_state,
    ambos ya incluidos en `permitidos`). Se fuerza acá para probar que el
    CENTINELA EN RUNTIME de completion_state.py está de verdad cableado, no
    muerto — forzando un `resolve_final_state` que devuelve un estado ajeno al
    de rol leído del perfil (perfil "manipulado": el rol dice 'Otro Valor' pero
    el resolver, forzado, devuelve 'Un Estado Ajeno')."""
    from services import completion_state
    from services import final_state_resolver as fsr

    _flag(monkeypatch, True)
    perfil = {"tracker_state_machine": {"technical": {"next_state_ok": "Otro Valor"}}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type=None)

    monkeypatch.setattr(
        fsr, "resolve_final_state",
        lambda **_k: fsr.FinalStateDecision("Un Estado Ajeno", "role", "ok"),
    )
    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("skipped") is True
    assert out.get("reason") == "state_not_applicable"
    assert prov.writes == []
