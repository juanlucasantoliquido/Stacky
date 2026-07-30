"""Plan 262 F9 — una sola DEFINICION de "app viva"; las tres copias delegan.

11 casos. El caso 1 es el defecto contado y su mensaje NOMBRA los archivos, en vez
de colapsar N ofensores a un fallo mudo. El caso 10 atrapa el ciclo de imports, que
es el modo de fallo mas probable de esta fase.
"""
from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import agenda_health
import agenda_web_launcher
import environment_preflight
import smoke_path_checker

_TOOL_ROOT = Path(__file__).resolve().parents[2]
_LITERAL = "frozenset({200, 301, 302, 400, 401, 403})"


def _modulos_raiz():
    return sorted(p for p in _TOOL_ROOT.glob("*.py"))


def test_una_sola_definicion_del_frozenset():
    """Tres modulos opinaban sobre lo mismo con codigo distinto, y ya derivaron."""
    offenders = sorted(
        p.name for p in _modulos_raiz()
        if _LITERAL in p.read_text(encoding="utf-8", errors="ignore")
        and p.name != "agenda_health.py"
    )
    assert offenders == [], f"copias de los alive codes en: {offenders}"


def test_preflight_usa_el_alias():
    assert environment_preflight._ALIVE_STATUS_CODES is agenda_health.ALIVE_STATUS_CODES


def test_smoke_usa_el_alias():
    assert smoke_path_checker._ALIVE_STATUS_CODES is agenda_health.ALIVE_STATUS_CODES


def test_launcher_responds_delega():
    with patch.object(agenda_health, "probe_url") as probe:
        probe.return_value = agenda_health.HealthProbe(
            True, 200, "http://x/", 1, "", "http_probe", 1)
        assert agenda_web_launcher._responds("http://x/") is True
        probe.return_value = agenda_health.HealthProbe(
            False, None, "http://x/", 1, "err", "http_probe", 1)
        assert agenda_web_launcher._responds("http://x/") is False
    assert probe.called


def test_launcher_no_tiene_fallback_hardcodeado():
    texto = (_TOOL_ROOT / "agenda_web_launcher.py").read_text(encoding="utf-8")
    assert "frozenset({200" not in texto


def test_smoke_no_hardcodea_la_base_url():
    texto = (_TOOL_ROOT / "smoke_path_checker.py").read_text(encoding="utf-8")
    assert "localhost:35017" not in texto


def test_preflight_logger_tiene_el_prefijo_de_la_casa():
    assert environment_preflight.logger.name == "stacky.qa_uat.environment_preflight"


def test_run_environment_preflight_sigue_devolviendo_app_not_running(monkeypatch):
    """Contrato consumido por qa_uat_pipeline.py:404. No puede cambiar.

    Las credenciales se chequean ANTES del probe (environment_preflight.py:145-157),
    asi que sin ellas la respuesta seria MISSING_CREDENTIALS y este test no estaria
    probando el camino que dice probar.
    """
    import urllib.error
    monkeypatch.setenv("AGENDA_WEB_USER", "usuario_de_prueba")
    monkeypatch.setenv("AGENDA_WEB_PASS", "clave_de_prueba")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        resultado = environment_preflight.run_environment_preflight()
    assert resultado.reason == "APP_NOT_RUNNING", (
        f"el contrato del preflight cambio: devolvio {resultado.reason}"
    )


def test_run_smoke_path_conserva_su_contrato():
    """v2/C13 — las 4 claves, nombradas. HealthProbe NO tiene ok ni label: hace
    falta un adaptador explicito, no una sustitucion."""
    with patch.object(agenda_health, "probe_url") as probe:
        probe.return_value = agenda_health.HealthProbe(
            True, 200, "http://x/", 1, "", "http_probe", 1)
        salida = smoke_path_checker._check_http("http://x/", "etiqueta")
    assert set(salida) == {"ok", "label", "status", "error"}
    assert salida["label"] == "etiqueta"

    # El falso amigo: _check_auth_file tiene forma DISTINTA y no se unifica.
    auth = smoke_path_checker._check_auth_file()
    assert set(auth) >= {"ok", "label"}
    assert "message" in auth


def test_sin_ciclo_de_imports():
    """El modo de fallo mas probable de esta fase. Se prueba en LOS DOS ordenes."""
    for primero, segundo in (("agenda_health", "environment_preflight"),
                             ("environment_preflight", "agenda_health")):
        codigo = (
            "import sys; sys.path.insert(0, r'%s');"
            "import importlib;"
            "importlib.import_module('%s'); importlib.import_module('%s');"
            "print('OK')" % (_TOOL_ROOT, primero, segundo)
        )
        r = subprocess.run([sys.executable, "-c", codigo], capture_output=True,
                           text=True, timeout=60)
        assert r.returncode == 0, (
            f"ciclo de imports con orden {primero} -> {segundo}: {r.stderr[-500:]}"
        )


def test_las_implementaciones_de_probe_http_son_las_dos_declaradas():
    """v2/C6 — el gate HONESTO de INV-4. Congela en DOS los probes de
    disponibilidad de AgendaWeb, cada uno con su motivo escrito:
      - environment_preflight._http_get: fail-fast, UNA vez, ANTES del navegador.
      - agenda_health.probe_url: en caliente, repetible, DURANTE la corrida.
    Una TERCERA rompe el test.

    El discriminante es "usa urlopen Y consulta los alive codes". Contar todo
    urlopen seria falso: en la raiz hay 5 modulos mas que hablan HTTP con otros
    sistemas (el lector de tickets, la huella de despliegue, el cliente de
    modelos), y ninguno es un probe de disponibilidad de AgendaWeb.
    """
    probes = sorted(
        p.name for p in _modulos_raiz()
        if "urlopen" in (t := p.read_text(encoding="utf-8", errors="ignore"))
        and "ALIVE_STATUS_CODES" in t
    )
    esperados = ["agenda_health.py", "environment_preflight.py"]
    extras = sorted(set(probes) - set(esperados))
    faltantes = sorted(set(esperados) - set(probes))
    assert extras == [], f"probes HTTP no declarados en: {extras}"
    assert faltantes == [], f"probes declarados que desaparecieron: {faltantes}"
