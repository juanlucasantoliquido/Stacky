"""Plan 257 F3 — `GET /api/diag/logs/noise`: las firmas que inundan el log.

El reporte sale de `get_throttle_filter().snapshot()`, que ya tiene los
contadores EN MEMORIA. Cero costo extra: no se re-parsea ningun archivo, y
`snapshot()` es READ-ONLY (no resetea: eso lo hace el flush de F1-ter).

Con la flag apagada o sin filtro instalado la respuesta es 200 con
`enabled: false` — un panel de diagnostico no debe romperse porque una flag
este apagada.

Correr POR ARCHIVO:
    .venv\\Scripts\\python.exe -m pytest tests/test_plan257_log_noise_api.py -v
"""
from __future__ import annotations

import logging
import os
import pathlib
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import services.local_file_logging as lfl  # noqa: E402


@pytest.fixture(autouse=True)
def _filtro_limpio():
    """El filtro es un singleton de proceso: sin reset, el orden de la suite
    decide que ve el endpoint."""
    lfl.reset_throttle_filter()
    yield
    lfl.reset_throttle_filter()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client (mismo patron que tests/test_plan256_quarantine_api.py)."""
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")

    tmp_env = tmp_path / ".env"
    tmp_env.write_text("", encoding="utf-8")
    monkeypatch.setattr("api.global_config._ENV_PATH", tmp_env)
    monkeypatch.setattr("api.harness_flags._ENV_PATH", tmp_env, raising=False)

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def _sembrar(*, ruidosa: int = 10, tranquila: int = 3):
    """Instala un filtro con firmas ya contadas, sin depender del root logger."""
    flt = lfl._ThrottleFilter(window_s=60.0, max_sigs=1000)
    lfl._throttle_filter = flt

    lg = logging.getLogger("test257.noise")
    lg.propagate = False
    lg.setLevel(logging.DEBUG)
    previos = list(lg.handlers)
    lg.handlers = []
    sink = logging.Handler()
    sink.setLevel(logging.DEBUG)
    sink.emit = lambda record: None          # type: ignore[method-assign]
    sink.addFilter(flt)
    lg.addHandler(sink)
    try:
        for _ in range(ruidosa):
            lg.warning("firma muy repetida del panel")
        for _ in range(tranquila):
            lg.warning("firma poco repetida del panel")
    finally:
        lg.handlers = previos
        lg.propagate = True
    return flt


def test_endpoint_devuelve_firmas_ordenadas_por_suppressed(client):
    _sembrar(ruidosa=10, tranquila=3)

    resp = client.get("/api/diag/logs/noise")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["enabled"] is True
    firmas = body["signatures"]
    assert len(firmas) == 2
    assert firmas[0]["suppressed"] == 9
    assert firmas[1]["suppressed"] == 2
    assert firmas[0]["level"] == "WARNING"
    assert firmas[0]["logger"] == "test257.noise"
    # El levelno queda INTACTO en la firma: la normalizacion de digitos se
    # aplica SOLO al tramo del mensaje (C3).
    assert "|30|" in firmas[0]["signature"]


def test_endpoint_vacio_cuando_no_hubo_throttle(client):
    lfl._throttle_filter = lfl._ThrottleFilter(window_s=60.0, max_sigs=1000)

    resp = client.get("/api/diag/logs/noise")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["enabled"] is True
    assert body["signatures"] == []


def test_endpoint_200_con_flag_off(client, monkeypatch):
    from config import config as cfg

    _sembrar()
    monkeypatch.setattr(cfg, "STACKY_LOG_THROTTLE_ENABLED", False, raising=False)

    resp = client.get("/api/diag/logs/noise")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["enabled"] is False
    assert body["signatures"] == []


def test_endpoint_declara_si_la_tarjeta_esta_habilitada(client, monkeypatch):
    """La flag de la tarjeta es EJE APARTE: apagarla no apaga la consulta ni el
    agrupado, solo le dice a la interfaz que no se dibuje."""
    from config import config as cfg

    _sembrar()
    assert client.get("/api/diag/logs/noise").get_json()["card_enabled"] is True

    monkeypatch.setattr(cfg, "STACKY_UI_LOG_NOISE_CARD_ENABLED", False, raising=False)
    body = client.get("/api/diag/logs/noise").get_json()
    assert body["card_enabled"] is False
    assert body["enabled"] is True          # el agrupado sigue vivo
    assert body["signatures"]               # y el dato sigue disponible


def test_endpoint_sin_filtro_instalado_responde_200(client):
    lfl._throttle_filter = None

    resp = client.get("/api/diag/logs/noise")
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is False


def test_endpoint_no_reparsea_archivos(client, monkeypatch):
    """C19 — criterio binario, no 'mockear el filesystem'."""
    _sembrar()

    def _boom(*a, **kw):
        raise AssertionError("el endpoint no debe tocar el disco")

    monkeypatch.setattr(pathlib.Path, "open", _boom)
    monkeypatch.setattr(pathlib.Path, "glob", _boom)

    resp = client.get("/api/diag/logs/noise")
    assert resp.status_code == 200
    assert resp.get_json()["signatures"]


def test_endpoint_no_resetea_contadores(client):
    _sembrar(ruidosa=10, tranquila=3)

    primero = client.get("/api/diag/logs/noise").get_json()["signatures"]
    segundo = client.get("/api/diag/logs/noise").get_json()["signatures"]

    assert [f["suppressed"] for f in primero] == [f["suppressed"] for f in segundo] == [9, 2]
