"""Plan 262 F6 — UN solo nombre canonico para la cota de reintentos de navegacion.

9 casos. EL GATE es el caso 2: la "limpieza obvia" —hacer canonica a
max_nav_retries, cuyo default es 1— pasa los casos 1, 4 y 5 y FALLA el 2, porque
bajaria los reintentos efectivos de 3 a 1 en silencio. Esa regresion disfrazada de
limpieza es exactamente lo que este gate existe para atrapar.

El caso 5 NO testea un helper suelto: llama a _run_all_specs_once con Popen
mockeado y lee el env REAL que recibiria el subproceso. Sin eso, un helper correcto
y jamas invocado pasaria igual.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import uat_test_runner as utr

_TOOL_ROOT = Path(__file__).resolve().parents[2]
_RUNNER_PY = _TOOL_ROOT / "uat_test_runner.py"
_TS = _TOOL_ROOT / "playwright" / "helpers" / "navigation_executor.ts"

_CANON = "QA_NAV_RETRIES"
_ALIAS = "QA_UAT_MAX_NAVIGATION_RETRIES"


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    monkeypatch.delenv(_CANON, raising=False)
    monkeypatch.delenv(_ALIAS, raising=False)


def _env_aplicado() -> dict:
    """Reproduce el env del subproceso: base os.environ + las dos keys canonicas."""
    env = {**os.environ}
    return utr._apply_nav_retry_env(env)


def test_variable_muerta_eliminada():
    """max_nav_retries se asignaba y NUNCA se usaba (1 hit en el archivo)."""
    texto = _RUNNER_PY.read_text(encoding="utf-8")
    hits = [
        f"{i}: {ln.strip()}"
        for i, ln in enumerate(texto.splitlines(), start=1)
        if "max_nav_retries" in ln
    ]
    assert hits == [], f"la variable muerta sigue viva: {hits}"


def test_default_efectivo_sigue_siendo_3():
    """GATE ANTI-REGRESION. El efectivo de hoy es 3 (uat_test_runner.py:343)."""
    env = _env_aplicado()
    assert env[_CANON] == "3", (
        f"el default efectivo bajo a {env[_CANON]!r}: es una regresion silenciosa "
        "de comportamiento disfrazada de limpieza"
    )


def test_qa_nav_retries_explicito_gana(monkeypatch):
    monkeypatch.setenv(_CANON, "5")
    env = _env_aplicado()
    assert env[_CANON] == "5"
    assert env[_ALIAS] == "5"


def test_alias_solo_tambien_funciona(monkeypatch):
    """Antes: el alias se leia a una variable muerta y se exportaba '3'."""
    monkeypatch.setenv(_ALIAS, "2")
    env = _env_aplicado()
    assert env[_CANON] == "2"
    assert env[_ALIAS] == "2"


def test_ambas_keys_se_exportan_con_el_mismo_valor(monkeypatch):
    """Se llama al RUNNER de verdad con Popen mockeado: prueba el call site real."""
    combos = [
        ({}, "3"),
        ({_CANON: "4"}, "4"),
        ({_ALIAS: "6"}, "6"),
        ({_CANON: "7", _ALIAS: "9"}, "7"),   # el canonico gana sobre el alias
    ]
    for entorno, esperado in combos:
        for k in (_CANON, _ALIAS):
            monkeypatch.delenv(k, raising=False)
        for k, v in entorno.items():
            monkeypatch.setenv(k, v)

        capturado = {}

        def _fake_popen(*a, **kw):
            capturado.update(kw.get("env") or {})
            raise subprocess.TimeoutExpired(cmd="npx", timeout=1)

        with patch.object(subprocess, "Popen", side_effect=_fake_popen), \
                patch.object(utr, "_write_playwright_config", MagicMock(), create=True):
            try:
                utr._run_all_specs_once(
                    spec_files=[_TOOL_ROOT / "playwright" / "uat" / "x.spec.ts"],
                    evidence_out=_TOOL_ROOT / "evidence" / "_plan262_tmp",
                    ticket_id=1, headed=False, timeout_ms=1000,
                    max_total_s=1, verbose=False,
                )
            except Exception:                       # noqa: BLE001
                pass

        assert capturado, f"Popen no recibio env para {entorno}"
        assert capturado.get(_CANON) == esperado, (entorno, capturado.get(_CANON))
        assert capturado.get(_CANON) == capturado.get(_ALIAS), (
            f"asimetria muda entre las dos keys para {entorno}: "
            f"{capturado.get(_CANON)!r} vs {capturado.get(_ALIAS)!r}"
        )


def test_valor_no_numerico_cae_al_default_sin_lanzar(monkeypatch):
    monkeypatch.setenv(_CANON, "abc")
    env = _env_aplicado()
    assert env[_CANON] == "3"
    assert env[_ALIAS] == "3"


def test_cero_se_respeta(monkeypatch):
    """Desactivar los reintentos es una eleccion legitima."""
    monkeypatch.setenv(_CANON, "0")
    env = _env_aplicado()
    assert env[_CANON] == "0"
    assert env[_ALIAS] == "0"


def test_el_ts_lee_las_dos_keys():
    """Gate de deriva, anclado por CONTENIDO (un ancla a :377 se rompe sola)."""
    texto = _TS.read_text(encoding="utf-8")
    lineas = [ln for ln in texto.splitlines() if f"process.env.{_ALIAS}" in ln]
    assert lineas, f"no se encontro ninguna linea que lea process.env.{_ALIAS} en el TS"
    assert any(_CANON in ln for ln in lineas), (
        f"la linea que lee {_ALIAS} ya no menciona {_CANON}: el TS derivo y ahora "
        f"puede resolver un numero distinto del que Python cree. Lineas: {lineas}"
    )


def test_qa_nav_retries_llega_por_flag(monkeypatch):
    """v2/C9 — la perilla existe y es configurable, con clampeo a sus bounds."""
    import recovery_config as rc
    assert rc.DEFAULTS[_CANON] == "3"
    assert rc.nav_retries() == 3
    monkeypatch.setenv(_CANON, "7")
    assert rc.nav_retries() == 7
    monkeypatch.setenv(_CANON, "99")
    assert rc.nav_retries() == 10
