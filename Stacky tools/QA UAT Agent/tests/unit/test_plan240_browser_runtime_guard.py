"""Tests del guard de runtime de navegador — Plan 240 F0 (+ C12)."""
from pathlib import Path

import pytest

import browser_runtime_guard as guard
from browser_runtime_guard import (
    _CONTRACT_KEYS,
    _detect_shadowing,
    _headless_shell_path,
    check_browser_runtime,
)


def test_guard_ok_en_este_entorno():
    res = check_browser_runtime()
    assert res["ok"] is True
    assert res["binding_ok"] is True
    assert res["browser_ok"] is True
    assert res["code"] == ""


def test_detecta_shadowing_del_directorio_del_tool():
    """El tool tiene un directorio playwright/ (specs TS) sin __init__.py."""
    shadow = _detect_shadowing()
    assert shadow, "deberia detectar el directorio playwright/ del tool"
    assert shadow.replace("\\", "/").endswith("playwright")


def test_guard_sin_binding_no_lanza_y_da_remediacion(monkeypatch):
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *a, **kw):
        if name.startswith("playwright"):
            raise ImportError("No module named 'playwright.sync_api'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", fake_import)
    res = check_browser_runtime()
    assert res["ok"] is False
    assert res["binding_ok"] is False
    assert res["code"] in ("BROWSER_RUNTIME_MISSING", "PLAYWRIGHT_SHADOWED_BY_TOOL_DIR")
    assert "pip install" in res["remediation"]
    assert "ImportError" in res["detail"]


def test_keys_del_contrato_siempre_presentes(monkeypatch):
    ok_res = check_browser_runtime()
    assert set(_CONTRACT_KEYS) <= set(ok_res)

    def boom(name, *a, **kw):
        if name.startswith("playwright"):
            raise ImportError("nope")
        return __import__(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", boom)
    bad_res = check_browser_runtime()
    assert set(_CONTRACT_KEYS) <= set(bad_res)


@pytest.mark.parametrize(
    "headed,expected_tail",
    [
        (r"C:\x\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
         r"chromium_headless_shell-1228\chrome-headless-shell-win64\chrome-headless-shell.exe"),
    ],
)
def test_headless_shell_path_derivada(headed, expected_tail):
    out = _headless_shell_path(headed)
    assert out is not None
    assert out.endswith(expected_tail)


def test_headless_shell_path_sin_patron_es_none():
    assert _headless_shell_path(r"C:\otro\layout\chrome.exe") is None
    assert _headless_shell_path("") is None


def test_browser_ok_falso_si_falta_el_headless_shell(monkeypatch):
    """C12: executable_path existe pero el headless shell NO => browser_ok False."""
    real_is_file = Path.is_file
    real_exe = None

    res_probe = check_browser_runtime()
    real_exe = res_probe["executable_path"]
    shell = res_probe["headless_shell_path"]
    assert real_exe and shell, "entorno sin las rutas esperadas"

    def fake_is_file(self):
        if str(self) == str(shell):
            return False
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    res = check_browser_runtime()
    assert res["browser_ok"] is False
    assert res["code"] == "BROWSER_RUNTIME_MISSING"
    assert "playwright install" in res["remediation"]
