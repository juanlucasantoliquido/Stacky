"""Plan 210 F4 — Gate del estado final del Developer.

Sin veredicto de máquina FRESCO, el developer no avanza: degrada al estado de
revisión, o cancela la transición si el perfil no lo declara.
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

from services import dev_build_verify as dbv  # noqa: E402

_ADO = 210500
_NEXT_OK = "Reviewed by Dev"
_REVIEW = "Ready for Dev"


@pytest.fixture(autouse=True)
def _perfil(monkeypatch):
    from services import client_profile

    monkeypatch.setattr(
        client_profile, "load_effective_client_profile",
        lambda project: {"tracker_state_machine": {"developer": {
            "input_states": [_REVIEW], "in_progress": "In Progress",
            "next_state_ok": _NEXT_OK,
        }}},
        raising=True,
    )


def _verdict(monkeypatch, **kw):
    base = {"ok": True, "gate_ok": True, "entry_kind": "sln", "reason": "ok",
            "execution_id": 0}
    base.update(kw)
    monkeypatch.setattr(dbv, "read_verdict", lambda a, w: dbv.BuildVerdict(**base),
                        raising=True)


def _gate(**kw):
    args = {"project_name": "p", "agent_type": "developer", "ado_id": _ADO,
            "workspace_root": "C:\\ws", "proposed_state": _NEXT_OK, "execution_id": 0}
    args.update(kw)
    return dbv.gate_final_state(**args)


def test_gate_passthrough_for_non_developer(monkeypatch):
    _verdict(monkeypatch, gate_ok=False, ok=False, reason="build_failed")

    estado, meta = _gate(agent_type="technical")

    assert estado == _NEXT_OK, "el gate no toca a ningún otro agente"
    assert meta["applied"] is False


def test_gate_passthrough_when_flag_off(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DEV_BUILD_VERIFY_ENABLED", False, raising=False)
    _verdict(monkeypatch, gate_ok=False, ok=False, reason="build_failed")

    estado, meta = _gate()

    assert estado == _NEXT_OK
    assert meta["applied"] is False


def test_gate_allows_when_verdict_gate_ok(monkeypatch):
    _verdict(monkeypatch, gate_ok=True, ok=True, reason="ok", execution_id=42)

    estado, meta = _gate(execution_id=42)

    assert estado == _NEXT_OK
    assert meta["gate_ok"] is True


def test_gate_downgrades_when_no_verdict(monkeypatch):
    monkeypatch.setattr(dbv, "read_verdict", lambda a, w: None, raising=True)

    estado, meta = _gate()

    assert estado == _REVIEW, "la AUSENCIA de veredicto no es OK"
    assert meta["gate_ok"] is False
    assert meta["reason"] == "not_verified"
    assert meta["downgraded_from"] == _NEXT_OK


def test_gate_downgrades_when_build_failed(monkeypatch):
    _verdict(monkeypatch, gate_ok=False, ok=False, reason="build_failed")

    estado, meta = _gate()

    assert estado == _REVIEW
    assert meta["reason"] == "build_failed"


@pytest.mark.parametrize("reason", ["no_sln", "toolchain_missing",
                                    "build_workshop_unavailable", "csproj_not_allowed"])
def test_gate_downgrades_en_toda_razon_bloqueante(monkeypatch, reason):
    _verdict(monkeypatch, gate_ok=False, ok=False, reason=reason)

    estado, meta = _gate()

    assert estado == _REVIEW
    assert meta["gate_ok"] is False


def test_gate_downgrades_on_stale_verdict(monkeypatch):
    """Un verde de OTRA corrida no vale como verde de la actual."""
    _verdict(monkeypatch, gate_ok=True, ok=True, reason="ok", execution_id=41)

    estado, meta = _gate(execution_id=42)

    assert estado == _REVIEW, "veredicto viejo NO deja pasar"
    assert meta["reason"] == "stale_verdict"
    assert meta["gate_ok"] is False


def test_gate_verdict_sin_execution_id_no_se_considera_stale(monkeypatch):
    """Veredictos viejos (pre-C1) sin execution_id degradan a best-effort, no a stale."""
    _verdict(monkeypatch, gate_ok=True, ok=True, reason="ok", execution_id=0)

    estado, meta = _gate(execution_id=42)

    assert estado == _NEXT_OK
    assert meta["gate_ok"] is True


def test_gate_cancels_when_no_review_state(monkeypatch):
    from services import client_profile

    monkeypatch.setattr(client_profile, "load_effective_client_profile",
                        lambda project: {"tracker_state_machine": {"developer": {}}},
                        raising=True)
    monkeypatch.setattr(dbv, "read_verdict", lambda a, w: None, raising=True)

    estado, meta = _gate()

    assert estado is None, "mejor dejar el ticket donde está que avanzarlo en falso"
    assert meta["gate_ok"] is False


def test_gate_nunca_lanza(monkeypatch):
    def _boom(a, w):
        raise RuntimeError("disco roto")

    monkeypatch.setattr(dbv, "read_verdict", _boom, raising=True)

    estado, meta = _gate()

    assert meta["reason"] == "exception"
    assert estado == _NEXT_OK, "ante un error del propio gate no se rompe el flujo"


def test_apply_task_state_early_returns_when_gate_cancels(monkeypatch):
    """Integración: si el gate cancela, `_safe_transition` NO se llama."""
    import api.tickets as tickets
    from harness import task_states

    monkeypatch.setattr(tickets, "load_effective_client_profile",
                        lambda p: {"tracker_state_machine": {"developer": {
                            "next_state_ok": _NEXT_OK}}}, raising=True)
    monkeypatch.setattr(dbv, "workspace_root_for_ado", lambda a: "C:\\ws", raising=True)
    monkeypatch.setattr(dbv, "latest_execution_id_for_ado", lambda a: 7, raising=True)
    monkeypatch.setattr(dbv, "gate_final_state",
                        lambda **kw: (None, {"applied": True, "gate_ok": False,
                                             "reason": "not_verified"}),
                        raising=True)
    llamadas: list = []
    monkeypatch.setattr(task_states, "_safe_transition",
                        lambda *a, **kw: llamadas.append(a), raising=True)
    monkeypatch.setattr(tickets, "_safe_transition",
                        lambda *a, **kw: llamadas.append(a), raising=True)

    class T:
        stacky_project_name = "p"
        work_item_type = "Task"
        ado_id = _ADO

    out = tickets._apply_task_state(ticket=T(), agent_type="developer", phase="final",
                                    correlation_id="c1")

    assert out == {"skipped": True, "reason": "dev_build_gate_no_state",
                   "gate_reason": "not_verified"}
    assert llamadas == [], "no se transiciona nada si el gate canceló"


def test_apply_task_state_usa_el_estado_degradado(monkeypatch):
    import api.tickets as tickets

    monkeypatch.setattr(tickets, "load_effective_client_profile",
                        lambda p: {"tracker_state_machine": {"developer": {
                            "next_state_ok": _NEXT_OK}}}, raising=True)
    monkeypatch.setattr(dbv, "workspace_root_for_ado", lambda a: "C:\\ws", raising=True)
    monkeypatch.setattr(dbv, "latest_execution_id_for_ado", lambda a: 7, raising=True)
    monkeypatch.setattr(dbv, "gate_final_state",
                        lambda **kw: (_REVIEW, {"applied": True, "gate_ok": False,
                                                "reason": "build_failed"}),
                        raising=True)
    aplicados: list = []
    monkeypatch.setattr(tickets, "_provider_for_ticket", lambda ticket: None, raising=True)
    monkeypatch.setattr(tickets, "_safe_transition",
                        lambda prov, ado_id, target, **kw: aplicados.append(target) or {"ok": True},
                        raising=True)

    class T:
        stacky_project_name = "p"
        work_item_type = "Task"
        ado_id = _ADO

    tickets._apply_task_state(ticket=T(), agent_type="developer", phase="final",
                              correlation_id="c1")

    assert aplicados == [_REVIEW], "se aplica el estado de revisión, no el next_state_ok"


def test_sin_import_de_api_en_el_service():
    fuente = (ROOT / "services" / "dev_build_verify.py").read_text(encoding="utf-8")

    assert "from api" not in fuente, "service→api invertiría la dependencia"
