"""test_plan241_diagnostics.py — Plan 241 F6.

Ningun fallo se reporta con una causa que no es. Cada diagnostico falso costo
tiempo real de depuracion en la corrida del Plan 240.
"""
import inspect
import json

import pytest

import uat_test_runner
from uat_test_runner import _classify_and_emit_runner_summary
from browser_runtime_guard import check_node_browser_drift


# ── 1. NO_TESTS_FOUND que en realidad es un crash del globalSetup ────────────

_REAL_GLOBAL_SETUP_CRASH = """
Running 3 tests using 1 worker

Error: browserType.launch: Executable doesn't exist at C:\\Users\\x\\AppData\\Local\\ms-playwright\\chromium_headless_shell-1217\\chrome-headless-shell-win64\\chrome-headless-shell.exe
╔═════════════════════════════════════════════════════════════════════════╗
║ Looks like Playwright Test or Playwright was just installed or updated. ║
╚═════════════════════════════════════════════════════════════════════════╝
    at globalSetup (playwright/global.setup.ts:41:22)
"""


def _summary_with_stdout(tmp_path, stdout: str, total: int = 0) -> dict:
    (tmp_path / "playwright_output.txt").write_text(stdout, encoding="utf-8")
    return _classify_and_emit_runner_summary(
        runs=[], total=total, pass_count=0, fail_count=0, blocked_count=0,
        duration_ms=1234, json_report_path=str(tmp_path / "nope.json"),
        junit_report_path=str(tmp_path / "nope.xml"),
        exec_log_path=str(tmp_path / "execution.jsonl"),
        exec_log=None, evidence_out=tmp_path,
    )


def test_global_setup_failed_no_dice_no_tests_found(tmp_path):
    s = _summary_with_stdout(tmp_path, _REAL_GLOBAL_SETUP_CRASH)
    assert s["reason"] == "GLOBAL_SETUP_FAILED"
    assert s["category"] == "ENV"
    assert s["verdict"] == "BLOCKED"          # 0 tests JAMAS es PASS
    assert "chromium_headless_shell-1217" in s.get("detail", "")


def test_total_cero_sin_globalsetup_sigue_siendo_no_tests_found(tmp_path):
    """La regla 'total=0 ALWAYS maps to BLOCKED PIP NO_TESTS_FOUND' sigue vigente:
    lo unico que cambia es la CAUSA reportada cuando SI hubo crash de globalSetup."""
    s = _summary_with_stdout(tmp_path, "No tests found.\n")
    assert s["reason"] == "NO_TESTS_FOUND"
    assert s["category"] == "PIP"
    assert s["verdict"] == "BLOCKED"


def test_classifier_no_fue_modificado():
    """(C3) playwright_result_classifier conserva su regla: 0 tests nunca es PASS."""
    import playwright_result_classifier as prc
    src = inspect.getsource(prc)
    assert "NO_TESTS_FOUND" in src
    assert "GLOBAL_SETUP_FAILED" not in src, (
        "el fix va en el runner, NO en el clasificador (C3)")


# ── 2. NameError: name '_run_id' is not defined ──────────────────────────────

def test_run_pipeline_stages_recibe_run_id():
    """El call site de data_readiness_check usaba `_run_id`, que NO existe en el
    scope de _run_pipeline_stages (se define en run(), otra funcion)."""
    import qa_uat_pipeline
    sig = inspect.signature(qa_uat_pipeline._run_pipeline_stages)
    assert "run_id" in sig.parameters, "run_id debe ser parametro explicito"
    src = inspect.getsource(qa_uat_pipeline._run_pipeline_stages)
    assert '"_run_id" in dir()' not in src, (
        'el hack `_run_id if "_run_id" in dir() else ...` siempre caia al else')


def test_call_sites_pasan_run_id():
    import qa_uat_pipeline
    src = inspect.getsource(qa_uat_pipeline)
    assert src.count("_run_pipeline_stages(") >= 3      # 2 llamadas + la def
    assert "run_id=_run_id" in src


# ── 3. Deriva de versiones Node <-> Python ───────────────────────────────────

def test_drift_detectado_con_las_dos_remediaciones(tmp_path):
    res = check_node_browser_drift(node_version="1.59.1", python_version="1.61.0")
    assert res["code"] == "BROWSER_VERSION_DRIFT"
    assert res["ok"] is False
    assert res["node_version"] == "1.59.1"
    assert res["python_version"] == "1.61.0"
    rem = " ".join(res["remediation"])
    assert "npm" in rem.lower()
    assert "pip" in rem.lower() or "playwright install" in rem.lower()


def test_sin_drift_ok(tmp_path):
    res = check_node_browser_drift(node_version="1.61.0", python_version="1.61.0")
    assert res["ok"] is True
    assert res["code"] == ""


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
