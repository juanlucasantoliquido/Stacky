"""Plan 200 R1 — La incidencia conoce TODAS sus ejecuciones, no solo la primera.

El análisis y el dev-resolutor eran dos ejecuciones sueltas: la incidencia solo
guardaba el `execution_id` del análisis, así que la mitad de lo que el agente
respondió no tenía cómo llegar a la pantalla.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import runtime_paths  # noqa: E402
from services import incident_store  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield tmp_path


def _incidencia(texto: str = "la pantalla se rompe") -> dict:
    return incident_store.create_incident(texto, files=[])


def test_add_execution_idempotente():
    inc = _incidencia()

    incident_store.add_execution(inc["id"], 101, kind="analysis")
    incident_store.add_execution(inc["id"], 101, kind="analysis")

    guardada = incident_store.get_incident(inc["id"])
    assert len(guardada["executions"]) == 1


def test_add_execution_dos_kinds():
    inc = _incidencia()
    incident_store.update_incident(inc["id"], execution_id=101)

    incident_store.add_execution(inc["id"], 101, kind="analysis")
    incident_store.add_execution(inc["id"], 202, kind="dev_resolver")

    guardada = incident_store.get_incident(inc["id"])
    assert [(e["execution_id"], e["kind"]) for e in guardada["executions"]] == \
        [(101, "analysis"), (202, "dev_resolver")]
    assert guardada["execution_id"] == 101, "el campo legacy no se toca"


def test_add_execution_incidente_inexistente():
    with pytest.raises(ValueError):
        incident_store.add_execution("no-existe", 1, kind="analysis")


def test_find_by_tracker_id():
    inc = _incidencia()
    incident_store.update_incident(inc["id"], tracker_id=4242)

    encontrada = incident_store.find_by_tracker_id(4242)

    assert encontrada is not None and encontrada["id"] == inc["id"]


def test_find_by_tracker_id_compara_como_texto():
    """El ticket trae int y el ledger puede tener str: no puede fallar por eso."""
    inc = _incidencia()
    incident_store.update_incident(inc["id"], tracker_id="4242")

    assert incident_store.find_by_tracker_id(4242) is not None


def test_find_by_tracker_id_sin_match_devuelve_none():
    _incidencia()

    assert incident_store.find_by_tracker_id(999999) is None
    assert incident_store.find_by_tracker_id(None) is None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

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


def test_console_endpoint_lista_executions(client):
    inc = _incidencia()
    incident_store.add_execution(inc["id"], 101, kind="analysis")
    incident_store.add_execution(inc["id"], 202, kind="dev_resolver")

    body = client.get(f"/api/incidents/{inc['id']}/console").get_json()

    assert body["ok"] is True
    assert [e["kind"] for e in body["executions"]] == ["analysis", "dev_resolver"]


def test_console_backcompat_solo_legacy(client):
    """Una incidencia previa al 200 no puede quedarse sin consola."""
    inc = _incidencia()
    incident_store.update_incident(inc["id"], execution_id=77)

    body = client.get(f"/api/incidents/{inc['id']}/console").get_json()

    assert body["executions"] == [
        {"execution_id": 77, "kind": "analysis", "linked_at": None}]
    assert body["primary_execution_id"] == 77


def test_console_sin_ejecuciones_devuelve_lista_vacia(client):
    inc = _incidencia()

    body = client.get(f"/api/incidents/{inc['id']}/console").get_json()

    assert body["ok"] is True and body["executions"] == []


def test_console_404_flag_off(client, monkeypatch):
    from config import config as cfg

    inc = _incidencia()
    monkeypatch.setattr(cfg, "STACKY_INCIDENT_CONSOLE_ENABLED", False, raising=False)

    r = client.get(f"/api/incidents/{inc['id']}/console")

    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_console_404_incidente_inexistente(client):
    assert client.get("/api/incidents/no-existe/console").status_code == 404
