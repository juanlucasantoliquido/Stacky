"""Plan 295 F6 — un fallo de la API de GitLab deja de salir como 500 "unexpected".

POR QUÉ. `TrackerApiError` NO es hermana de `AdoApiError`: deriva de una rama
separada (`TrackerError(RuntimeError)` -> `TrackerApiError`, tracker_provider.py:46,
52-57). Por eso la lista de `except` de los dos endpoints de sync SE VEÍA completa y
no lo estaba: un PAT de GitLab vencido caía en `except Exception` y el operador
recibía `HTTP 500 {"error":"unexpected"}` -- un bug del backend donde hay una
credencial que renovar. El equivalente ADO recibe 502 + copy accionable desde el
plan 148 (`_ado_sync_error_response`).

AISLAMIENTO: base SQLite fresca por archivo Y `STACKY_DATA_DIR` en tmp_path. Aislar
`DATABASE_URL` NO aisla `data_dir()`, y el breaker de F7 escribe
`integration_breaker.json` ahí: sin esto el test deja archivos reales en la carpeta
del operador y le contamina el estado de degradación.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'plan295.db'}")
    monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STACKY_SYNC_MIN_INTERVAL_SEC", "0")

    import api.tickets as tickets_api

    tickets_api._last_sync_ts_by_project.clear()
    tickets_api._sync_in_progress_by_project.clear()

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _lanzar(monkeypatch, exc):
    """Inyecta la excepción en el ÚNICO punto que los dos endpoints comparten."""
    import api.tickets as tickets_api

    def _boom(*a, **kw):
        raise exc

    monkeypatch.setattr(tickets_api, "_sync_via_provider_or_ado", _boom)


def _api_error(status, kind="unknown", mensaje="HTTP 401 en /api/v4/issues"):
    """El texto de la excepción NO nombra a GitLab A PROPÓSITO.

    Con un mensaje que lo nombrara, el caso 4 pasaría EN FALSO antes del cambio:
    el `except Exception` de hoy devuelve `str(e)` como `message`, así que
    "gitlab in message" se cumpliría por el texto de la excepción y no por el copy
    accionable que esta fase agrega."""
    from services.tracker_provider import TrackerApiError

    return TrackerApiError(status, mensaje, kind=kind)


# ------------------------------------------------------------------ casos ---
def test_1_sync_v2_pat_vencido_da_502(cliente, monkeypatch):
    _lanzar(monkeypatch, _api_error(401, "auth"))
    resp = cliente.post("/api/tickets/sync-v2")
    assert resp.status_code == 502, resp.get_data(as_text=True)


def test_2_el_cuerpo_dice_gitlab_api(cliente, monkeypatch):
    _lanzar(monkeypatch, _api_error(401, "auth"))
    assert cliente.post("/api/tickets/sync-v2").get_json()["error"] == "gitlab_api"


def test_3_el_cuerpo_trae_el_kind(cliente, monkeypatch):
    _lanzar(monkeypatch, _api_error(401, "auth"))
    assert cliente.post("/api/tickets/sync-v2").get_json()["kind"] == "auth"


def test_4_el_mensaje_nombra_gitlab(cliente, monkeypatch):
    _lanzar(monkeypatch, _api_error(401, "auth"))
    data = cliente.post("/api/tickets/sync-v2").get_json()
    assert "gitlab" in data["message"].lower()


def test_5_la_respuesta_entera_no_dice_unexpected(cliente, monkeypatch):
    """Se mira el PAYLOAD COMPLETO, no sólo `message`: hoy la palabra vive en el
    campo `error`, así que un assert sobre `message` solo pasaría en falso antes
    del cambio y el gate no discriminaría nada."""
    import json as _json

    _lanzar(monkeypatch, _api_error(401, "auth"))
    data = cliente.post("/api/tickets/sync-v2").get_json()
    assert "unexpected" not in _json.dumps(data).lower(), data


def test_6_los_siete_kind_producen_siete_mensajes_distintos():
    """[v2, C12] Siete, no seis: `unknown` es el default de TrackerApiError.__init__
    y lo que _kind_for_status devuelve para 400/409/422."""
    from api.tickets import _COPY_GITLAB_POR_KIND

    kinds = ("auth", "not_found", "rate_limited", "server", "tls", "network", "unknown")
    for k in kinds:
        assert k in _COPY_GITLAB_POR_KIND, f"falta el copy de kind={k!r}"
    assert len({_COPY_GITLAB_POR_KIND[k] for k in kinds}) == 7


def test_7_un_kind_fuera_del_mapa_cae_en_el_fallback_y_sigue_dando_502(cliente, monkeypatch):
    from api.tickets import _COPY_GITLAB_FALLBACK

    _lanzar(monkeypatch, _api_error(418, "marciano"))
    resp = cliente.post("/api/tickets/sync-v2")
    data = resp.get_json()
    assert resp.status_code == 502
    assert data["kind"] == "marciano"
    assert data["message"] == _COPY_GITLAB_FALLBACK


def test_8_el_otro_endpoint_post_sync_tambien_da_502(cliente, monkeypatch):
    _lanzar(monkeypatch, _api_error(401, "auth"))
    resp = cliente.post("/api/tickets/sync")
    assert resp.status_code == 502, resp.get_data(as_text=True)
    assert resp.get_json()["error"] == "gitlab_api"


def test_9_ado_api_error_sigue_yendo_por_el_camino_ado(cliente, monkeypatch):
    """NO-REGRESIÓN: pasa ANTES y DESPUÉS de esta fase. Prueba que F6 le quitó una
    clase de fallo al `except Exception`, no que le movió el camino al hermano."""
    from services.ado_client import AdoApiError

    _lanzar(monkeypatch, AdoApiError("PAT vencido"))
    data = cliente.post("/api/tickets/sync-v2").get_json()
    assert data["error"] in ("ado_api", "ado_auth_invalid"), data


def test_10_el_status_upstream_llega_al_cuerpo(cliente, monkeypatch):
    """`.status`, NO `.status_code`: AdoApiError usa el segundo nombre y confundirlos
    haría que el handler lea None siempre."""
    _lanzar(monkeypatch, _api_error(401, "auth"))
    assert cliente.post("/api/tickets/sync-v2").get_json()["gitlab_status_code"] == 401


def test_11_un_422_real_produce_kind_unknown_y_copy_ACCIONABLE(cliente, monkeypatch):
    """[v2, C12] Impide que la séptima entrada del mapa se agregue de adorno: el
    caso 7 pasaría igual con `unknown` fuera del mapa porque usa 'marciano'. Este
    llama a `_kind_for_status(422)` de VERDAD, así que si mañana el cliente cambia
    la clasificación de 422, el test lo dice."""
    from api.tickets import _COPY_GITLAB_FALLBACK
    from services.gitlab_client import _kind_for_status

    kind_422 = _kind_for_status(422)
    _lanzar(monkeypatch, _api_error(422, kind_422))
    data = cliente.post("/api/tickets/sync-v2").get_json()
    assert data["kind"] == "unknown", f"_kind_for_status(422) = {kind_422!r}"
    assert data["message"] != _COPY_GITLAB_FALLBACK
    assert "gitlab" in data["message"].lower()
