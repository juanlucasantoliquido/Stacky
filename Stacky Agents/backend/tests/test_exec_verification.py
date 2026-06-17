"""Tests E0.1 — Motor de verificación ejecutable.

TDD: todos los tests se escriben antes de que el código esté completo.
Validan solo con mocks de subprocess (sin binarios reales).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Asegurar que el backend está en sys.path
_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_exec_verification_cache():
    """Limpia la caché del módulo entre tests."""
    from services import exec_verification as _ev
    _ev._CACHE.clear()
    yield
    _ev._CACHE.clear()


@pytest.fixture
def workspace(tmp_path):
    """Workspace temporal con estructura mínima."""
    return str(tmp_path)


@pytest.fixture
def mock_config_ev_enabled(monkeypatch):
    """Flag STACKY_EXEC_VERIFICATION_ENABLED=true, mode=annotate."""
    monkeypatch.setenv("STACKY_EXEC_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("STACKY_EXEC_VERIFICATION_MODE", "annotate")
    monkeypatch.setenv("STACKY_EXEC_VERIFICATION_TIMEOUT_S", "30")
    monkeypatch.setenv("STACKY_EXEC_VERIFICATION_BUDGET_S", "120")
    monkeypatch.setenv("STACKY_EXEC_VERIFICATION_PROJECTS", "")
    # Forzar reload de config
    from config import Config
    from unittest.mock import patch as _patch
    with _patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         _patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         _patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         _patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         _patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        yield


# ── 1. Flag OFF → byte-idéntico (no-op) ──────────────────────────────────────

def test_flag_off_returns_skipped(workspace):
    """Con flag OFF (default), verify devuelve passed=None y skipped_reason."""
    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", False):
        from services.exec_verification import verify
        report = verify(workspace=workspace, changed_files=["foo.py"])
    assert report.passed is None
    assert report.skipped_reason == "flag OFF"
    assert report.ran == []


def test_mode_off_returns_skipped(workspace):
    """Con mode=off, verify devuelve skipped aunque enabled=true."""
    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "off"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=workspace, changed_files=["foo.py"])
    assert report.passed is None
    assert report.skipped_reason == "flag OFF"


# ── 2. Sin changed_files → skipped ───────────────────────────────────────────

def test_no_changed_files_skipped(workspace):
    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=workspace, changed_files=[])
    assert report.passed is None
    assert "sin changed_files" in (report.skipped_reason or "")


# ── 3. JSON válido → passed ──────────────────────────────────────────────────

def test_json_valid_passes(tmp_path):
    json_file = tmp_path / "result.json"
    json_file.write_text('{"status": "ok"}')
    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(json_file)])
    assert "JsonYamlParser" in report.ran
    assert report.passed is True
    assert len(report.hard_failed) == 0


# ── 4. JSON inválido → HARD ──────────────────────────────────────────────────

def test_json_invalid_hard_fail(tmp_path):
    json_file = tmp_path / "bad.json"
    json_file.write_text('{invalid json')
    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(json_file)])
    assert report.passed is False
    hard_names = [r.name for r in report.hard_failed]
    assert "JsonYamlParser" in hard_names


# ── 5. Python válido compila → passed ───────────────────────────────────────

def test_py_compile_valid(tmp_path):
    py_file = tmp_path / "foo.py"
    py_file.write_text("def hello():\n    return 42\n")
    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(py_file)])
    assert "PyCompile" in report.ran
    assert not any(r.name == "PyCompile" for r in report.hard_failed)


# ── 6. Python con error de sintaxis → HARD ──────────────────────────────────

def test_py_compile_syntax_error(tmp_path):
    py_file = tmp_path / "bad.py"
    py_file.write_text("def broken(:\n    pass\n")
    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(py_file)])
    assert report.passed is False
    assert any(r.name == "PyCompile" for r in report.hard_failed)


# ── 7. Short-circuit ante primer HARD ────────────────────────────────────────

def test_short_circuit_on_first_hard(tmp_path):
    """Cuando JsonYamlParser falla (HARD), no se deben correr verificadores posteriores."""
    json_file = tmp_path / "bad.json"
    json_file.write_text('{bad}')

    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(json_file)])

    # Solo JsonYamlParser debe haber corrido (no llegó a PyCompile/TscCheck/etc.)
    assert "JsonYamlParser" in report.ran
    # PytestRunner no debe haber corrido (no hay .py en changed_files)
    assert "PytestRunner" not in report.ran
    assert report.passed is False


# ── 8. Could-not-verify no es fallo ──────────────────────────────────────────

def test_could_not_verify_is_not_failure(tmp_path):
    """TscCheck sin tsc disponible → could-not-verify, no HARD."""
    ts_file = tmp_path / "app.ts"
    ts_file.write_text("const x: number = 1;")
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text('{"compilerOptions": {}}')

    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""), \
         patch("subprocess.run", side_effect=FileNotFoundError("tsc not found")):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(ts_file)])

    assert "TscCheck" in report.could_not_verify
    # No debe estar en hard_failed
    assert not any(r.name == "TscCheck" for r in report.hard_failed)


# ── 9. Ningún verificador aplicable → passed=None ───────────────────────────

def test_no_applicable_verifiers(tmp_path):
    """Si el archivo no es .py/.json/.ts/etc., no se aplica ningún verificador."""
    readme = tmp_path / "README.txt"
    readme.write_text("hello")
    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(readme)])
    assert report.passed is None
    assert "ningún verificador aplicable" in (report.skipped_reason or "")


# ── 10. Caché por hash ────────────────────────────────────────────────────────

def test_cache_by_hash(tmp_path):
    """Segunda llamada idéntica usa caché (subprocess no se llama dos veces)."""
    py_file = tmp_path / "ok.py"
    py_file.write_text("x = 1\n")

    from config import Config
    call_count = [0]
    original_run = __import__("services.exec_verification", fromlist=["PyCompile"]).PyCompile.run

    def counting_run(self, workspace, changed_files, timeout_s):
        call_count[0] += 1
        return original_run(self, workspace, changed_files, timeout_s)

    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify, PyCompile
        with patch.object(PyCompile, "run", counting_run):
            report1 = verify(workspace=str(tmp_path), changed_files=[str(py_file)])
            report2 = verify(workspace=str(tmp_path), changed_files=[str(py_file)])

    assert call_count[0] == 1  # solo se ejecutó una vez
    assert report1.passed == report2.passed


# ── 11. Pytest falla → HARD; mock subprocess ─────────────────────────────────

def test_pytest_failure_is_hard(tmp_path):
    """PytestRunner con salida de test en rojo → HARD."""
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("def test_broken():\n    assert 1 == 2\n")

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "FAILED test_foo.py::test_broken - assert 1 == 2"
    mock_result.stderr = ""

    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""), \
         patch("subprocess.run", return_value=mock_result):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(test_file)])

    assert any(r.name == "PytestRunner" for r in report.hard_failed)
    assert report.passed is False


# ── 12. Pytest timeout → could-not-verify ────────────────────────────────────

def test_pytest_timeout_is_could_not_verify(tmp_path):
    import subprocess as _sp
    test_file = tmp_path / "test_slow.py"
    test_file.write_text("def test_slow():\n    import time; time.sleep(100)\n")

    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 1), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""), \
         patch("subprocess.run", side_effect=_sp.TimeoutExpired(cmd="pytest", timeout=1)):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(test_file)])

    assert "PytestRunner" in report.could_not_verify
    assert not any(r.name == "PytestRunner" for r in report.hard_failed)


# ── 13. Modo annotate no cambia status externo ───────────────────────────────

def test_annotate_mode_does_not_change_external_status(tmp_path):
    """to_metadata en modo annotate incluye mode='annotate'."""
    json_file = tmp_path / "bad.json"
    json_file.write_text('{bad')

    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(json_file)])

    metadata = report.to_metadata(mode="annotate")
    assert metadata["exec_verification"]["mode"] == "annotate"
    assert metadata["exec_verification"]["passed"] is False
    # La metadata lo registra pero no "bloquea" en modo annotate


# ── 14. to_metadata incluye todos los campos esperados ──────────────────────

def test_to_metadata_shape(tmp_path):
    py_file = tmp_path / "ok.py"
    py_file.write_text("x = 1\n")

    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "gate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(py_file)])

    md = report.to_metadata(mode="gate")
    ev = md["exec_verification"]
    assert "mode" in ev
    assert "ran" in ev
    assert "hard_failed" in ev
    assert "soft" in ev
    assert "passed" in ev
    assert "skipped_reason" in ev
    assert "duration_ms" in ev
    assert "fake_green" in ev


# ── 15. Proyecto no en allowlist → skipped ──────────────────────────────────

def test_project_allowlist_skips_if_not_in_list(tmp_path):
    py_file = tmp_path / "foo.py"
    py_file.write_text("x = 1\n")

    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", "other_project"):
        from services.exec_verification import verify
        # agent_type y runtime no coinciden con "other_project"
        report = verify(workspace=str(tmp_path), changed_files=[str(py_file)], agent_type="developer")
    assert report.passed is None
    assert "allowlist" in (report.skipped_reason or "")
