"""Plan 262 F11 — LA LEY DEL 241: la recuperacion reintenta, JAMAS ablanda.

15 casos, el gate mas importante del plan. Sin esta fase, la recuperacion es la
mejor maquina de verdes falsos jamas construida en este repo.

El caso 6 es el gate exhaustivo: una implementacion "servicial" que al recuperar
con exito marque el caso como PASS pasa 14 de 15 y falla ESE, nombrando la
combinacion ofensora. El caso 9 es estructural: impide que una fase futura cablee
la recuperacion al veredicto funcional del 241, que es la unica forma de que INV-1
se rompa sin que nadie lo note.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import agenda_health
import hot_recovery as hr
import playwright_result_classifier
import recovery_budget as rb
import recovery_classifier as rc
import uat_test_runner as utr
from agenda_health import HealthProbe

_TOOL_ROOT = Path(__file__).resolve().parents[2]
_BASE = "http://localhost:35017/AgendaWeb/"
_LOS_4_MODULOS = ("hot_recovery.py", "recovery_classifier.py",
                  "recovery_budget.py", "route_allowlist.py")


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", _BASE)
    for k in ("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "STACKY_QA_UAT_ROUTE_ALLOWLIST",
              "STACKY_QA_UAT_SAFE_ROUTE"):
        monkeypatch.delenv(k, raising=False)


def _viva(samples=2):
    return HealthProbe(True, 200, _BASE, 5, "", "http_probe_confirmed", samples)


def _muerta(samples=2):
    return HealthProbe(False, None, _BASE, 5000, "URLError: refused",
                       "http_probe_confirmed", samples)


def _run_dict(status="fail", reason="ORIGINAL"):
    return {"scenario_id": "esc1", "spec_file": str(_TOOL_ROOT / "x.spec.ts"),
            "status": status, "reason": reason, "raw_stderr": "detalle original"}


def _recover(nav_code=None, health=None, retry_status="fail", route="FrmBusqueda.aspx",
             budget=None, exec_log=None):
    with patch.object(agenda_health, "probe_agenda_confirmed",
                      return_value=health or _viva()), \
            patch.object(agenda_health, "probe_agenda", return_value=health or _viva()), \
            patch.object(utr, "run_single_spec",
                         return_value=_run_dict(status=retry_status)) as spec:
        out = hr.recover(case_id="esc1", exc_text="boom", route_used=route,
                         nav_code=nav_code, budget=budget or rb.RecoveryBudget(6, 1, 1),
                         exec_log=exec_log, run_dict=_run_dict())
    return out, spec


def test_functional_error_no_dispara_recuperacion():
    out, spec = _recover(health=_viva(), route="FrmBusqueda.aspx")
    assert out.recovery_class == "FUNCTIONAL_ERROR"
    assert out.attempted is False
    assert spec.call_count == 0


def test_fail_tras_reintento_sigue_siendo_fail():
    out, _ = _recover(nav_code="NAV_DEVIATION", retry_status="fail")
    assert out.retried_result["status"] == "fail"
    assert out.retried_result["status"] not in ("skipped", "mixed", "pass")


def test_fail_que_pasa_al_reintentar_no_se_reporta_como_pass_limpio():
    """Un PASS con historial de reintento NO es un PASS limpio y debe decirlo."""
    log = MagicMock()
    out, _ = _recover(nav_code="NAV_DEVIATION", retry_status="pass", exec_log=log)
    assert out.retried_result["status"] == "pass"
    assert out.as_report()["attempts"] >= 1
    assert log.flake_suspected.called, "falta la senal honesta de inestabilidad"


def test_blocked_honesto_no_se_convierte_en_mixed():
    out, _ = _recover(health=_muerta(), retry_status="fail")
    assert out.recovery_class == "SERVICE_DOWN"
    assert rc._CLASS_TO_TAXONOMY["SERVICE_DOWN"]["verdict"] == "BLOCKED"


def test_recuperacion_no_puede_producir_pass_con_cero_tests(tmp_path):
    """GATE DE INV-3: total == 0 sigue siendo BLOCKED, con o sin recuperacion."""
    spy = MagicMock()
    tests_dir = tmp_path / "uat"
    tests_dir.mkdir(parents=True)
    (tests_dir / "a.spec.ts").write_text("//", encoding="utf-8")
    evidencia = tmp_path / "evidence"
    evidencia.mkdir()
    with patch.object(utr, "_run_all_specs_once", return_value=([], 1, 0)), \
            patch.object(hr, "recover", spy):
        salida = utr.run(tests_dir=tests_dir, evidence_out=evidencia, verbose=False)
    assert spy.call_count == 0, "no hay casos: no hay nada que recuperar"
    assert salida.get("verdict") != "PASS"


def test_ningun_camino_devuelve_pass():
    """GATE EXHAUSTIVO: las 5 clases x {reintento exitoso, fallido} = 10 combinaciones."""
    escenarios = {
        "SERVICE_DOWN":     dict(health=_muerta(), nav_code=None),
        "ROUTE_ERROR":      dict(health=_viva(), nav_code="NAV_DEVIATION"),
        "SESSION_ERROR":    dict(health=_viva(), nav_code="NAV_SESSION_LOST"),
        "FUNCTIONAL_ERROR": dict(health=_viva(), nav_code=None),
        "UNRECOVERABLE":    dict(health=_viva(), nav_code="NAV_TIMEOUT"),
    }
    ofensoras = []
    for clase, kw in escenarios.items():
        for retry_status in ("pass", "fail"):
            out, _ = _recover(retry_status=retry_status, **kw)
            reporte = out.as_report()
            tax = rc._CLASS_TO_TAXONOMY.get(out.recovery_class, {})
            if tax.get("verdict") == "PASS" or reporte.get("verdict") == "PASS":
                ofensoras.append((clase, retry_status, out.recovery_class))
    assert ofensoras == [], (
        f"la recuperacion produjo un PASS en estas combinaciones: {ofensoras}"
    )


def test_el_presupuesto_agotado_no_baja_la_severidad():
    budget = rb.RecoveryBudget(10, 1, 1)
    budget.consume("esc1", "ROUTE_ERROR")
    out, _ = _recover(nav_code="NAV_DEVIATION", budget=budget)
    assert out.attempted is False
    assert out.final_reason == "presupuesto_del_caso_agotado"
    assert rc._CLASS_TO_TAXONOMY[out.recovery_class]["verdict"] == "BLOCKED"


def test_reintento_no_borra_el_fallo_original():
    out, _ = _recover(nav_code="NAV_DEVIATION", retry_status="fail")
    assert "boom" in out.as_report()["exception"]


def test_recuperacion_no_toca_los_criterios_funcionales():
    """GATE ESTRUCTURAL. La capa de recuperacion NO tiene permiso de tocar el
    veredicto funcional del 241."""
    prohibidas = ("criteria", "acceptance", "functional_verdict", "discrimination")
    ofensores = {}
    for nombre in _LOS_4_MODULOS:
        texto = (_TOOL_ROOT / nombre).read_text(encoding="utf-8").lower()
        hits = [p for p in prohibidas if p in texto]
        if hits:
            ofensores[nombre] = hits
    assert ofensores == {}, f"la capa de recuperacion toca el veredicto funcional: {ofensores}"


def test_recuperacion_no_escribe_en_el_veredicto_del_pipeline():
    ofensores = [n for n in _LOS_4_MODULOS
                 if "pipeline_verdict(" in (_TOOL_ROOT / n).read_text(encoding="utf-8")]
    assert ofensores == [], f"modulos que escriben el veredicto del pipeline: {ofensores}"


def test_clasificador_no_emite_pass():
    emiten = {c: t["verdict"] for c, t in rc._CLASS_TO_TAXONOMY.items()
              if t["verdict"] == "PASS"}
    assert emiten == {}, f"clases que emiten PASS: {emiten}"


def test_functional_error_mapea_a_fail_no_a_blocked():
    """Mandarlo a BLOCKED seria el ablandamiento INVERSO: convertir un bug del
    desarrollo en un problema de entorno."""
    assert rc._CLASS_TO_TAXONOMY["FUNCTIONAL_ERROR"]["verdict"] == "FAIL"
    assert rc._CLASS_TO_TAXONOMY["FUNCTIONAL_ERROR"]["owner"] == "developer"


def test_verdicts_del_mapeo_son_subconjunto_de_los_oficiales():
    ajenos = {c: t["verdict"] for c, t in rc._CLASS_TO_TAXONOMY.items()
              if t["verdict"] not in playwright_result_classifier.VALID_VERDICTS}
    assert ajenos == {}, f"verdicts inventados: {ajenos}"


def test_con_flag_off_los_veredictos_son_los_de_hoy(monkeypatch, tmp_path):
    """GATE DE INV-8: con la capacidad apagada, el comportamiento es el previo."""
    monkeypatch.setenv("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "false")
    spy = MagicMock()
    tests_dir = tmp_path / "uat"
    tests_dir.mkdir(parents=True)
    (tests_dir / "a.spec.ts").write_text("//", encoding="utf-8")
    evidencia = tmp_path / "evidence"
    evidencia.mkdir()
    runs = [_run_dict(status="fail")]
    with patch.object(utr, "_run_all_specs_once", return_value=(runs, 1, 0)), \
            patch.object(hr, "recover", spy):
        salida = utr.run(tests_dir=tests_dir, evidence_out=evidencia, verbose=False)
    assert spy.call_count == 0
    assert salida["runs"][0]["status"] == "fail"
    assert "recovery_report" not in salida["runs"][0]


def test_nav_wrong_screen_no_ablanda_el_veredicto():
    """v2/C2 — el codigo MAS on-point del pedido. Hay que probar LAS DOS cosas:
    que se recupera Y que recuperarse no lo ablanda."""
    out, spec = _recover(nav_code="NAV_WRONG_SCREEN", retry_status="fail")
    assert out.recovery_class == "ROUTE_ERROR"
    assert rc.is_recoverable("ROUTE_ERROR") is True
    assert spec.call_count == 1, "NAV_WRONG_SCREEN tiene que reintentarse"
    assert out.retried_result["status"] == "fail", (
        "el caso reintentado que vuelve a fallar sigue en FAIL"
    )
