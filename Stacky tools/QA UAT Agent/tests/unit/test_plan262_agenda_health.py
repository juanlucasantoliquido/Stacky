"""Plan 262 F1 + F1.5 — agenda_health: la unica fuente de verdad de "responde AHORA".

13 casos. TODOS con urlopen mockeado: cero red real.

El caso 3 (401 es vivo) es el gate del defecto central: un naive `status == 200`
llamaria caida a un 401/403/302-a-login. El caso 12 es el gate de F1.5: la
implementacion de UNA sola muestra devuelve alive=False ante un flap.
"""
from __future__ import annotations

import urllib.error
from unittest.mock import patch

import pytest

import agenda_health
import environment_preflight


class _FakeResp:
    """Respuesta HTTP minima con protocolo de context manager."""

    def __init__(self, code: int):
        self._code = code

    def getcode(self) -> int:
        return self._code

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://x/", code=code, msg="forced", hdrs=None, fp=None
    )


# ── Alive codes ───────────────────────────────────────────────────────────────

def test_200_es_vivo():
    with patch("urllib.request.urlopen", return_value=_FakeResp(200)):
        p = agenda_health.probe_url("http://x/AgendaWeb/")
    assert p.alive is True
    assert p.status == 200
    assert p.error == ""


def test_302_es_vivo():
    """Una redireccion a login NO es una caida."""
    with patch("urllib.request.urlopen", side_effect=_http_error(302)):
        p = agenda_health.probe_url("http://x/AgendaWeb/")
    assert p.alive is True
    assert p.status == 302


def test_401_es_vivo():
    """Un 401 PRUEBA que el proceso sirve HTTP. Es el defecto central del plan."""
    with patch("urllib.request.urlopen", side_effect=_http_error(401)):
        p = agenda_health.probe_url("http://x/AgendaWeb/")
    assert p.alive is True
    assert p.status == 401


def test_403_es_vivo():
    with patch("urllib.request.urlopen", side_effect=_http_error(403)):
        p = agenda_health.probe_url("http://x/AgendaWeb/")
    assert p.alive is True
    assert p.status == 403


def test_400_es_vivo():
    """Caso host-binding documentado en environment_preflight.py:59-61."""
    with patch("urllib.request.urlopen", side_effect=_http_error(400)):
        p = agenda_health.probe_url("http://x/AgendaWeb/")
    assert p.alive is True
    assert p.status == 400


def test_500_no_es_vivo():
    with patch("urllib.request.urlopen", side_effect=_http_error(500)):
        p = agenda_health.probe_url("http://x/AgendaWeb/")
    assert p.alive is False
    assert p.status == 500
    assert "500" in p.error


# ── No lanza nunca ────────────────────────────────────────────────────────────

def test_connection_refused_no_es_vivo():
    err = urllib.error.URLError("Connection refused")
    with patch("urllib.request.urlopen", side_effect=err):
        p = agenda_health.probe_url("http://x/AgendaWeb/")
    assert p.alive is False
    assert p.status is None
    assert "URLError" in p.error


def test_excepcion_inesperada_no_lanza():
    """Una excepcion no prevista devuelve alive=False; NUNCA propaga."""
    with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
        p = agenda_health.probe_url("http://x/AgendaWeb/")
    assert p.alive is False
    assert "RuntimeError" in p.error
    assert "boom" in p.error


def test_timeout_cero_se_clampea():
    """timeout <= 0 seria un probe que nunca puede dar vivo. Se clampea a >= 0.5."""
    with patch("urllib.request.urlopen", return_value=_FakeResp(200)) as m:
        agenda_health.probe_url("http://x/AgendaWeb/", timeout_s=0)
    assert m.call_args.kwargs["timeout"] >= 0.5


# ── Contratos cruzados ────────────────────────────────────────────────────────

def test_alive_codes_son_los_mismos_que_el_preflight():
    """Igualdad de VALOR. La identidad `is` se exige recien en F9."""
    assert agenda_health.ALIVE_STATUS_CODES == environment_preflight._ALIVE_STATUS_CODES


def test_probe_agenda_usa_la_base_url_no_la_ruta(monkeypatch):
    """INV-5: SIEMPRE contra la base estable, nunca contra la ruta que fallo."""
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://x/AgendaWeb/")
    with patch("urllib.request.urlopen", return_value=_FakeResp(200)) as m:
        agenda_health.probe_agenda()
    req = m.call_args.args[0]
    assert req.full_url == "http://x/AgendaWeb/"
    assert ".aspx" not in req.full_url


# ── F1.5: SERVICE_DOWN exige DOS muestras ─────────────────────────────────────

def test_un_solo_probe_muerto_no_da_service_down_confirmado(monkeypatch):
    """GATE DE F1.5: muerto -> vivo es un FLAP (reciclado de AppPool), no una caida.

    La implementacion de UNA sola muestra (la del v1) devuelve alive=False y
    autoriza abrir un proceso en la maquina del operador por un hipo de 3 s.
    """
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://x/AgendaWeb/")
    seq = [urllib.error.URLError("refused"), _FakeResp(200)]

    def _side(*a, **k):
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    with patch("urllib.request.urlopen", side_effect=_side), \
            patch("time.sleep") as sleep_mock:
        p = agenda_health.probe_agenda_confirmed()

    assert p.alive is True
    assert p.source == "http_probe_flapped"
    assert p.samples == 2
    assert sleep_mock.called, "debe pausar entre las dos muestras"


def test_dos_probes_muertos_dan_service_down_confirmado(monkeypatch):
    """Dos muertos consecutivos SI sostienen SERVICE_DOWN. Y la pausa nunca es negativa."""
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://x/AgendaWeb/")
    err = urllib.error.URLError("refused")
    with patch("urllib.request.urlopen", side_effect=err), \
            patch("time.sleep") as sleep_mock:
        p = agenda_health.probe_agenda_confirmed(confirm_pause_s=-5)

    assert p.alive is False
    assert p.source == "http_probe_confirmed"
    assert p.samples == 2
    negativos = [c.args[0] for c in sleep_mock.call_args_list if c.args and c.args[0] < 0]
    assert negativos == [], f"time.sleep recibio valores negativos: {negativos}"
