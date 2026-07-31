"""tests/test_plan276_capability_envelope.py — Plan 276 F6.

CORRECCIÓN DE LA EVIDENCIA (verificada, no asumida): la UI llama
`POST /api/tickets/sync-v2`, NO `/sync`. `sync-v2` tenía un `except Exception`
genérico que devolvía 500 `{"ok": false, "error": "unexpected"}`, y como
`CapabilityUnavailable` ES una `Exception`, quedaba atrapada ahí. Por eso el
handler de `app.py` que traduce la carencia a 200 + `available:false` NUNCA se
ejecutaba para `sync-v2`: solo `/sync` la trataba explícitamente.

Resultado para el operador: un 500 MUDO que escondía una carencia DECLARADA.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import config as config_module  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # P2-6: DATABASE_URL ANTES de create_app() o `create_all` corre contra la BD
    # REAL del operador (181 MB).
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'p276env.db').as_posix()}")
    monkeypatch.setenv("STACKY_SKIP_STARTUP_SYNC", "1")
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def sin_rate_limit():
    """`sync-v2` tiene rate-limit y guard de concurrencia POR PROYECTO, con estado
    a nivel de módulo. Sin limpiarlo, el segundo test del archivo recibe un 429 y
    los asserts fallan por un motivo que no tiene nada que ver con lo que prueban."""
    import api.tickets as t

    t._last_sync_ts_by_project.clear()
    t._sync_in_progress_by_project.clear()
    yield
    t._last_sync_ts_by_project.clear()
    t._sync_in_progress_by_project.clear()


def _sync_v2(client):
    return client.post("/api/tickets/sync-v2", json={})


def test_sync_v2_con_carencia_da_200_available_false_y_ok_false(client, monkeypatch):
    """EL GATE CONTRA EL DEFECTO: hoy esto es un 500 'unexpected'."""
    monkeypatch.setattr(config_module.config, "STACKY_CAPABILITY_DEGRADATION_ENABLED", True)
    from services.tracker_provider import CapabilityUnavailable

    def _carencia(**kw):
        raise CapabilityUnavailable(
            "tracker.sync.full", "jira",
            reason="el sync de ítems de este tracker todavía no está implementado",
            workaround="usá un proyecto Azure DevOps o GitLab.",
        )

    monkeypatch.setattr("api.tickets._sync_via_provider_or_ado", _carencia)
    resp = _sync_v2(client)

    assert resp.status_code == 200, f"sigue siendo un 500 mudo: {resp.get_data(as_text=True)}"
    body = resp.get_json()
    assert body["available"] is False
    assert body["ok"] is False, f"`ok` contradice a `available`: {body}"
    assert body["capability"] == "tracker.sync.full"
    assert body["workaround"]


def test_sync_v2_con_carencia_no_loguea_fallo_inesperado(client, monkeypatch, caplog):
    """Una carencia declarada NO es un fallo inesperado: si aparece ese texto en el
    log, la excepción volvió a caer en el `except Exception` genérico."""
    monkeypatch.setattr(config_module.config, "STACKY_CAPABILITY_DEGRADATION_ENABLED", True)
    from services.tracker_provider import CapabilityUnavailable

    def _carencia(**kw):
        raise CapabilityUnavailable("tracker.sync.full", "jira", reason="r", workaround="w")

    monkeypatch.setattr("api.tickets._sync_via_provider_or_ado", _carencia)
    with caplog.at_level("ERROR"):
        _sync_v2(client)
    assert not any("fallo inesperado" in r.getMessage() for r in caplog.records), (
        f"la carencia cayó en el except genérico: {[r.getMessage() for r in caplog.records]}"
    )


def test_sync_v2_con_excepcion_cualquiera_sigue_siendo_500(client, monkeypatch):
    """No se rompió el manejo genérico: un error de verdad sigue dando 500."""
    def _explota(**kw):
        raise RuntimeError("algo se rompió de verdad")

    monkeypatch.setattr("api.tickets._sync_via_provider_or_ado", _explota)
    resp = _sync_v2(client)
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "unexpected"


def test_el_envelope_pone_ok_false_cuando_available_es_false():
    """Unitario del envelope, sin HTTP: `api/errors.py` ponía `ok:true`."""
    from api.errors import capability_unavailable_envelope
    from services.tracker_provider import CapabilityUnavailable

    payload = capability_unavailable_envelope(
        CapabilityUnavailable("tracker.sync.full", "jira", reason="r", workaround="w")
    )
    assert payload["available"] is False
    assert payload["ok"] is False
    assert payload["message"]


def test_con_la_degradacion_apagada_sigue_el_camino_legacy(client, monkeypatch):
    """Rollback por flag: vuelve la forma HTTP legacy (500)."""
    monkeypatch.setattr(config_module.config, "STACKY_CAPABILITY_DEGRADATION_ENABLED", False)
    from services.tracker_provider import CapabilityUnavailable

    def _carencia(**kw):
        raise CapabilityUnavailable("tracker.sync.full", "jira", reason="r", workaround="w")

    monkeypatch.setattr("api.tickets._sync_via_provider_or_ado", _carencia)
    resp = _sync_v2(client)
    assert resp.status_code == 500, resp.get_data(as_text=True)


def test_tracker_config_error_da_400_config_y_nombra_el_switch(client, monkeypatch):
    """v2/C1 — sin handler propio, el TrackerConfigError enriquecido de F5.3 caía en
    el `except Exception` y salía como 500 'unexpected': el MISMO defecto mudo que
    esta fase vino a matar, con otra excepción."""
    from services.tracker_provider import TrackerConfigError

    def _sin_switch(**kw):
        raise TrackerConfigError(
            "El proyecto usa el tracker 'gitlab' pero no se pudo construir su cliente: "
            "GitLab deshabilitado (STACKY_GITLAB_ENABLED=false). Si dice "
            "STACKY_GITLAB_ENABLED=false, encendé 'STACKY_GITLAB_ENABLED' en "
            "Configuración global -> GitLab."
        )

    monkeypatch.setattr("api.tickets._sync_via_provider_or_ado", _sin_switch)
    resp = _sync_v2(client)

    assert resp.status_code == 400, f"esperaba 400, no un 500 mudo: {resp.get_data(as_text=True)}"
    body = resp.get_json()
    assert body["ok"] is False
    assert body["error"] == "config"
    assert "STACKY_GITLAB_ENABLED" in body["message"], (
        f"el mensaje no nombra el switch: {body['message']}"
    )
