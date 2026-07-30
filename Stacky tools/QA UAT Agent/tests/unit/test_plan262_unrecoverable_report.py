"""Plan 262 F10 — el reporte de no-recuperable y los 6 eventos de recuperacion.

12 casos. test_los_4_campos_del_operador_estan_presentes es el criterio de cierre
del operador convertido en gate, y su mensaje NOMBRA los faltantes en vez de
colapsarlos. test_app_alive_true_cuando_la_app_respondio es el que prueba que el
reporte dice "la aplicacion estaba viva" — la informacion que hoy no existe en
ninguna parte y sin la cual el operador no puede saber que NO fue una caida.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import agenda_health
import hot_recovery as hr
import recovery_budget as rb
import uat_test_runner
from agenda_health import HealthProbe

_TOOL_ROOT = Path(__file__).resolve().parents[2]
_BASE = "http://localhost:35017/AgendaWeb/"

_LOS_6_EVENTOS = [
    "recovery_attempt_start", "recovery_health_probe", "recovery_classified",
    "recovery_action", "recovery_budget_state", "recovery_outcome",
]


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", _BASE)
    for k in ("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "STACKY_QA_UAT_ROUTE_ALLOWLIST",
              "STACKY_QA_UAT_SAFE_ROUTE"):
        monkeypatch.delenv(k, raising=False)


class _FakeLog:
    def __init__(self):
        self.eventos = []
        self.flakes = []

    def event(self, event_name, data, **kw):
        self.eventos.append(event_name)

    def flake_suspected(self, **kw):
        self.flakes.append(kw)


def _viva():
    return HealthProbe(True, 200, _BASE, 5, "", "http_probe_confirmed", 2)


def _run_dict(status="fail"):
    return {"scenario_id": "esc1", "spec_file": str(_TOOL_ROOT / "x.spec.ts"),
            "status": status, "reason": "BOOM", "raw_stderr": "detalle"}


def _reporte(nav_code="NAV_DEVIATION", exec_log=None, retry_status="fail",
             route="FrmMala.aspx"):
    with patch.object(agenda_health, "probe_agenda_confirmed", return_value=_viva()), \
            patch.object(uat_test_runner, "run_single_spec",
                         return_value=_run_dict(status=retry_status)):
        out = hr.recover(case_id="esc1", exc_text="TimeoutError: waiting for x",
                         route_used=route, nav_code=nav_code,
                         budget=rb.RecoveryBudget(6, 1, 1), exec_log=exec_log,
                         run_dict=_run_dict())
    return out


def test_los_4_campos_del_operador_estan_presentes():
    rep = _reporte().as_report()
    exigidos = ["route_used", "exception", "attempts", "final_reason"]
    faltantes = [c for c in exigidos if c not in rep]
    assert faltantes == [], f"campos que pidio el operador y faltan: {faltantes}"


def test_ningun_campo_obligatorio_es_none():
    rep = _reporte().as_report()
    nulos = [c for c in ("route_used", "exception", "attempts", "final_reason")
             if rep.get(c) is None]
    assert nulos == [], f"un None obliga al operador a adivinar. Campos nulos: {nulos}"


def test_route_used_desconocida_cuando_no_se_sabe():
    rep = _reporte(route="").as_report()
    assert rep["route_used"] == "<desconocida>"


def test_attempts_es_entero_no_none():
    rep = _reporte().as_report()
    assert isinstance(rep["attempts"], int)


def test_final_reason_nunca_vacio():
    rep = _reporte().as_report()
    assert rep["final_reason"], "un motivo vacio no es un diagnostico"


def test_app_alive_true_cuando_la_app_respondio():
    """LA prueba de que NO fue una caida. Es el corazon del pedido del operador."""
    rep = _reporte().as_report()
    assert rep["app_alive"] is True


def test_los_6_eventos_se_emiten_en_orden():
    log = _FakeLog()
    _reporte(exec_log=log)
    emitidos = [e for e in log.eventos if e in _LOS_6_EVENTOS]
    assert emitidos == _LOS_6_EVENTOS, f"secuencia real: {emitidos}"


def test_ningun_evento_existente_se_renombra():
    """Hay consumidores del JSONL: los 6 eventos nuevos son ADITIVOS."""
    texto = (_TOOL_ROOT / "execution_logger.py").read_text(encoding="utf-8")
    faltantes = [m for m in ("event", "stage_error", "flake_suspected",
                             "pipeline_verdict", "screenshot", "human_decision",
                             "error")
                 if f"def {m}(" not in texto]
    assert faltantes == [], f"metodos del logger renombrados o borrados: {faltantes}"


def test_flake_suspected_cuando_pasa_tras_reintento():
    """Un PASS con historial de reintento NO es un PASS limpio."""
    log = _FakeLog()
    _reporte(exec_log=log, retry_status="pass")
    assert log.flakes, "un caso que pasa al reintentar debe marcarse como inestable"
    assert log.flakes[0]["reason"] == "PASS_ON_RETRY"


def test_reporte_es_json_serializable():
    json.dumps(_reporte().as_report())


def test_reporte_no_contiene_credenciales(monkeypatch):
    monkeypatch.setenv("AGENDA_WEB_USER", "usuario_secreto")
    monkeypatch.setenv("AGENDA_WEB_PASS", "clave_secreta")
    texto = json.dumps(_reporte().as_report())
    for prohibido in ("AGENDA_WEB_PASS", "clave_secreta", "usuario_secreto"):
        assert prohibido not in texto, f"el reporte expone {prohibido}"


def test_sin_exec_log_el_reporte_se_arma_igual():
    rep = _reporte(exec_log=None).as_report()
    assert rep["route_used"]
    assert rep["final_reason"]
