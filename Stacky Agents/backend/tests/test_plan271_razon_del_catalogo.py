# backend/tests/test_plan271_razon_del_catalogo.py
"""Plan 271 F9 — Ninguna razón fuera del catálogo (centinela de contrato).

D3: hasta el v2 inclusive, la rama de error de `_safe_transition` devolvía un
dict SIN `reason`, y el helper de F5 lo bautizaba "unknown" — un string que no
está en ningún catálogo. F3-bis-3 tapó el agujero conocido; este test impide
que se abra otro, hoy Y a futuro (test 3, estático)."""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from services.final_state_resolver import ALL_FINAL_STATE_REASONS
from tests.plan271_helpers import FakeProvider, patch_motor_a


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


def _assert_reason_valido(out: dict):
    assert "reason" in out or out.get("ok") is True, f"retorno mudo: {out}"
    if "reason" in out:
        assert out["reason"] in ALL_FINAL_STATE_REASONS, f"reason fuera del catálogo: {out}"


def test_1_motor_a_runtime_todos_los_reasons_en_el_catalogo(monkeypatch):
    from services import completion_state

    def _ev(**over):
        base = {"ticket_id": 1, "execution_id": 9, "final_status": "completed", "agent_type": "technical"}
        base.update(over)
        return base

    import config as _config

    # (a) perfil vacío -> no_config
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", True, raising=False)
    patch_motor_a(monkeypatch, profile={}, work_item_type=None)
    _assert_reason_valido(completion_state.maybe_apply_state_transition(_ev()))

    # (b) sin agent_type -> no_agent_type
    patch_motor_a(monkeypatch, profile={"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}})
    _assert_reason_valido(completion_state.maybe_apply_state_transition(_ev(agent_type=None)))

    # (c) flag OFF -> flag_off
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", False, raising=False)
    patch_motor_a(monkeypatch, profile={"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}})
    _assert_reason_valido(completion_state.maybe_apply_state_transition(_ev()))
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", True, raising=False)

    # (d) final_status="error" -> not_ok_status
    patch_motor_a(monkeypatch, profile={"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}})
    _assert_reason_valido(completion_state.maybe_apply_state_transition(_ev(final_status="error")))

    # (e) ado_id ausente -> no_ado_id_or_stacky_project
    patch_motor_a(monkeypatch, profile={"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}},
                  ado_id=None)
    _assert_reason_valido(completion_state.maybe_apply_state_transition(_ev()))

    # (f) get_tracker_provider lanza -> no_provider (via _safe_transition)
    import services.tracker_provider as _tp
    patch_motor_a(monkeypatch, profile={"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}})

    def _boom(*_a, **_k):
        raise RuntimeError("sin conexion")

    monkeypatch.setattr(_tp, "get_tracker_provider", _boom)
    _assert_reason_valido(completion_state.maybe_apply_state_transition(_ev()))

    # (g) provider que lanza al escribir -> exception (capturado por el try/except externo)
    class _RaisingProvider(FakeProvider):
        def update_item_state(self, item_id, logical_state):
            raise RuntimeError("boom")

    import db as _db

    def _raise_scope(*_a, **_k):
        raise RuntimeError("db caída")

    monkeypatch.setattr(_db, "session_scope", _raise_scope)
    out = completion_state.maybe_apply_state_transition(_ev())
    _assert_reason_valido(out)
    assert out.get("reason") == "exception"


def test_2_motor_b_runtime_todos_los_reasons_en_el_catalogo(monkeypatch):
    from services import agent_completion_internal as aci
    from services.tracker_provider import CapabilityUnavailable
    from services.tracker_write_router import StateWriter

    def _flag(value: bool):
        import config as _config
        monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED", value, raising=False)

    def _seed(*, ado_id=4242, tracker_type="azure_devops"):
        from db import session_scope
        from models import Ticket
        with session_scope() as s:
            t = Ticket(ado_id=ado_id, project="P271", stacky_project_name="P271",
                       tracker_type=tracker_type, title="t", ado_state="New",
                       stacky_status="running")
            s.add(t)
            s.flush()
            return t.id

    _flag(True)

    # ticket_id None -> no_ticket_id
    _assert_reason_valido(aci._attempt_state_change(ticket_id=None, target_state="To Do", execution_id=1))

    # ticket inexistente -> no_ado_id (ado_id no se pudo leer)
    _assert_reason_valido(aci._attempt_state_change(ticket_id=999999, target_state="To Do", execution_id=1))

    # provider_unavailable
    tid = _seed(tracker_type="gitlab")
    import services.tracker_write_router as twr
    monkeypatch.setattr(twr, "resolve_state_writer",
                        lambda _t: (_ for _ in ()).throw(CapabilityUnavailable("x", "gitlab", reason="off")))
    _assert_reason_valido(aci._attempt_state_change(ticket_id=tid, target_state="To Do",
                                                     execution_id=1, project_name="P271"))

    # provider lanza al escribir -> transition_failed
    class _Raising(FakeProvider):
        def update_item_state(self, item_id, logical_state):
            raise RuntimeError("boom")

    monkeypatch.setattr(twr, "resolve_state_writer",
                        lambda _t: StateWriter(tracker_type="gitlab", kind="provider", handle=_Raising()))
    _assert_reason_valido(aci._attempt_state_change(ticket_id=tid, target_state="To Do",
                                                     execution_id=2, project_name="P271"))

    # legacy: AdoClient (doble) lanza -> transition_failed
    _flag(False)
    tid_ado = _seed(tracker_type="azure_devops")

    class _RaisingAdo:
        def update_work_item_state(self, *_a, **_k):
            raise RuntimeError("ADO 400")

    monkeypatch.setattr(aci, "_legacy_ado_client", lambda: _RaisingAdo())
    _assert_reason_valido(aci._attempt_state_change(ticket_id=tid_ado, target_state="To Do", execution_id=3))


# ── test estático (E4 — alcance ACOTADO a las funciones escritoras) ──────────

_ARCHIVOS_Y_FUNCIONES = {
    "services/completion_state.py": ("maybe_apply_state_transition", "_logged"),
    "services/agent_completion_internal.py": ("_attempt_state_change",),
    "harness/task_states.py": ("_safe_transition", "apply_task_start_state"),
}


def _dict_literal_del_return_o_del_ultimo_arg(call_or_dict) -> "ast.Dict | None":
    if isinstance(call_or_dict, ast.Dict):
        return call_or_dict
    if isinstance(call_or_dict, ast.Call) and call_or_dict.args:
        last = call_or_dict.args[-1]
        if isinstance(last, ast.Dict):
            return last
    return None


def _keys_de(d: ast.Dict) -> list[str]:
    return [k.value for k in d.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]


def _ok_es_true_literal(d: ast.Dict) -> bool:
    for k, v in zip(d.keys, d.values):
        if isinstance(k, ast.Constant) and k.value == "ok":
            return isinstance(v, ast.Constant) and v.value is True
    return False


def test_3_estatico_ningun_return_mudo_en_las_funciones_escritoras():
    violaciones: list[str] = []
    for rel, nombres in _ARCHIVOS_Y_FUNCIONES.items():
        path = ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name in nombres):
                continue
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Return) or sub.value is None:
                    continue
                d = _dict_literal_del_return_o_del_ultimo_arg(sub.value)
                if d is None:
                    continue
                keys = _keys_de(d)
                if "skipped" not in keys and "ok" not in keys:
                    continue
                if "reason" in keys:
                    continue
                if _ok_es_true_literal(d):
                    continue
                violaciones.append(
                    f"Retorno mudo en {rel}:{d.lineno} ({node.name}): un no-cambio "
                    "de estado sin `reason` es un defecto del plan 271 (§3-4)."
                )
    assert violaciones == [], "\n".join(violaciones)
