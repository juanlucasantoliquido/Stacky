"""Plan 262 F7.2 — EL CALL SITE. Que recover() se ejecute DE VERDAD.

9 casos. El caso 1 ES el bloqueante C3 convertido en test: toda la F7 del v1
—18 casos, todos verdes— era compatible con recover() sin un solo llamador,
porque sus tests mockeaban run_single_spec. Sin call site, el plan entregaba
0% del pedido con 100% de los tests en verde.

Se testea llamando a uat_test_runner.run con _run_all_specs_once MOCKEADO para
devolver un `runs` fabricado, y hot_recovery.recover ESPIADO.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import hot_recovery as hr
import uat_test_runner as utr

_TOOL_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch, tmp_path):
    monkeypatch.delenv("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", raising=False)
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")


def _caso(status="fail", scenario_id="esc1", reason="BOOM"):
    return {"scenario_id": scenario_id, "spec_file": str(_TOOL_ROOT / "x.spec.ts"),
            "status": status, "reason": reason, "duration_ms": 1,
            "artifacts": {}, "raw_stdout": "", "raw_stderr": "detalle"}


def _outcome(attempted=True, succeeded=False, retried=None,
             clase="ROUTE_ERROR"):
    verdict = MagicMock()
    verdict.health = None
    verdict.route_allowed = False
    verdict.evidence = "evidencia"
    return hr.RecoveryOutcome(
        attempted=attempted, succeeded=succeeded, recovery_class=clase,
        actions=("probe",), verdict=verdict, attempts=1,
        final_reason="" if succeeded else "motivo", route_used="FrmMala.aspx",
        retried_result=retried, exception_text="RuntimeError: boom",
    )


def _correr(runs, tmp_path, recover_mock=None, budget_mock=None):
    """Llama al runner REAL con el subproceso de specs mockeado."""
    tests_dir = tmp_path / "uat"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "esc1.spec.ts").write_text("//", encoding="utf-8")
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)

    ctx = [
        patch.object(utr, "_run_all_specs_once", return_value=(runs, 1, 0)),
        patch.object(hr, "recover", recover_mock or MagicMock(return_value=_outcome())),
    ]
    if budget_mock is not None:
        ctx.append(patch.object(hr, "build_budget_for_run", budget_mock))
    for c in ctx:
        c.start()
    try:
        return utr.run(tests_dir=tests_dir, evidence_out=evidence, verbose=False)
    finally:
        for c in reversed(ctx):
            c.stop()


def test_recover_se_llama_para_un_caso_fail(tmp_path):
    """EL GATE DE C3. Sin el bloque de F7.2 esto es 0 llamadas."""
    spy = MagicMock(return_value=_outcome())
    _correr([_caso(status="fail")], tmp_path, recover_mock=spy)
    assert spy.call_count == 1, (
        f"recover() recibio {spy.call_count} llamadas: la capa de recuperacion "
        "esta construida y probada pero NO se ejecuta nunca"
    )


def test_recover_no_se_llama_para_un_caso_pass(tmp_path):
    """Un pass no se toca JAMAS: 'mejorar' un caso verde es INV-1 al reves."""
    spy = MagicMock(return_value=_outcome())
    _correr([_caso(status="pass")], tmp_path, recover_mock=spy)
    assert spy.call_count == 0


def test_recover_se_llama_una_vez_por_caso_recuperable(tmp_path):
    spy = MagicMock(return_value=_outcome())
    runs = [_caso(status="pass", scenario_id="a"),
            _caso(status="fail", scenario_id="b"),
            _caso(status="blocked", scenario_id="c")]
    _correr(runs, tmp_path, recover_mock=spy)
    assert spy.call_count == 2
    ids = sorted(c.kwargs["case_id"] for c in spy.call_args_list)
    assert ids == ["b", "c"]


def test_el_presupuesto_se_construye_una_sola_vez(tmp_path):
    """Un 2 o un 3 aca es el bucle infinito latente: el presupuesto se reiniciaria."""
    import recovery_budget as rb
    budget_spy = MagicMock(return_value=rb.RecoveryBudget(6, 1, 1))
    spy = MagicMock(return_value=_outcome())
    runs = [_caso(status="fail", scenario_id=f"e{i}") for i in range(3)]
    _correr(runs, tmp_path, recover_mock=spy, budget_mock=budget_spy)
    assert budget_spy.call_count == 1, (
        f"el presupuesto se construyo {budget_spy.call_count} veces"
    )


def test_reintento_exitoso_reemplaza_el_caso_en_runs(tmp_path):
    reintentado = _caso(status="pass")
    spy = MagicMock(return_value=_outcome(attempted=True, succeeded=True,
                                          retried=reintentado))
    out = _correr([_caso(status="fail")], tmp_path, recover_mock=spy)
    assert out["runs"][0]["status"] == "pass"
    assert out.get("pass_count", 1) >= 1


def test_reintento_fallido_no_pisa_el_resultado_original(tmp_path):
    spy = MagicMock(return_value=_outcome(attempted=True, succeeded=False))
    out = _correr([_caso(status="fail", reason="ORIGINAL")], tmp_path, recover_mock=spy)
    assert out["runs"][0]["status"] == "fail"
    assert out["runs"][0]["reason"] == "ORIGINAL"


def test_recovery_report_presente_incluso_sin_intento(tmp_path):
    """FUNCTIONAL_ERROR: 'app viva, ruta legal, no se reintenta' es informacion
    que hoy no existe en ninguna parte."""
    spy = MagicMock(return_value=_outcome(attempted=False, succeeded=False,
                                          clase="FUNCTIONAL_ERROR"))
    out = _correr([_caso(status="fail")], tmp_path, recover_mock=spy)
    assert "recovery_report" in out["runs"][0]
    assert out["runs"][0]["recovery_report"]["recovery_class"] == "FUNCTIONAL_ERROR"


def test_flag_off_no_llama_a_recover_y_runs_queda_intacto(tmp_path, monkeypatch):
    """GATE DE INV-8: con la flag apagada, el comportamiento es el de hoy."""
    monkeypatch.setenv("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "false")
    spy = MagicMock(return_value=_outcome())
    out = _correr([_caso(status="fail")], tmp_path, recover_mock=spy)
    assert spy.call_count == 0
    assert "recovery_report" not in out["runs"][0]


def test_excepcion_en_la_capa_de_recuperacion_no_rompe_el_run(tmp_path):
    """El try/except que envuelve el bloque ES el fallback."""
    spy = MagicMock(side_effect=RuntimeError("la capa exploto"))
    out = _correr([_caso(status="fail")], tmp_path, recover_mock=spy)
    assert out is not None
    assert out["runs"][0]["status"] == "fail"
