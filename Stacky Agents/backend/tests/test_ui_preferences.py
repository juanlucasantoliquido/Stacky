"""Plan 173 F1 — Store clave-valor de preferencias de UI (vistas guardadas).

Ver Stacky Agents/docs/173_PLAN_VISTAS_GUARDADAS_PRESETS_DE_FILTROS_Y_PREFERENCIAS_DE_TABLA.md §F1.

La clave viaja en la URL, así que la validación NO es cosmética: sin ella,
`../../algo` escribiría fuera del sub-objeto `ui` y podría pisar preferencias
que este endpoint no debería tocar.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_URL = "/api/preferences/ui"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    import api.preferences as prefs
    import config as config_mod

    monkeypatch.setattr(prefs, "_PREFS_FILE", tmp_path / "preferences.json")
    monkeypatch.setattr(config_mod.config, "STACKY_UI_SAVED_VIEWS_ENABLED", True, raising=False)

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        c._archivo = tmp_path / "preferences.json"
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------

def test_clave_nunca_escrita_devuelve_null_y_no_404(client):
    # 200 con value null deja al frontend distinguir "no hay preferencia" sin
    # tener que manejar un error para el caso más normal del mundo.
    resp = client.get(f"{_URL}/history.views")

    assert resp.status_code == 200
    assert resp.get_json() == {"key": "history.views", "value": None}


def test_roundtrip(client):
    puesto = client.put(f"{_URL}/history.views", json={"value": [{"name": "Míos"}]})

    assert puesto.status_code == 200, puesto.get_json()
    assert client.get(f"{_URL}/history.views").get_json()["value"] == [{"name": "Míos"}]


def test_claves_distintas_no_se_pisan(client):
    client.put(f"{_URL}/history.views", json={"value": 1})
    client.put(f"{_URL}/logs.views", json={"value": 2})

    assert client.get(f"{_URL}/history.views").get_json()["value"] == 1
    assert client.get(f"{_URL}/logs.views").get_json()["value"] == 2


def test_sobrescribir_reemplaza(client):
    client.put(f"{_URL}/history.views", json={"value": [1, 2]})
    client.put(f"{_URL}/history.views", json={"value": [3]})

    assert client.get(f"{_URL}/history.views").get_json()["value"] == [3]


def test_value_null_es_un_valor_valido(client):
    # Borrar la preferencia es setearla en null, no un 400.
    client.put(f"{_URL}/history.views", json={"value": [1]})

    resp = client.put(f"{_URL}/history.views", json={"value": None})

    assert resp.status_code == 200
    assert client.get(f"{_URL}/history.views").get_json()["value"] is None


# ---------------------------------------------------------------------------
# Rechazos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("clave", ["../x", "a/b", "", "ñ", "a" * 129, "con espacio"])
def test_una_clave_invalida_nunca_escribe(client, clave):
    """Lo que importa no es el código, es que NO se escriba nada.

    Algunas de estas ni llegan al handler: el router de Flask las rechaza antes
    (405/404 según la forma). Da igual — asertar el código exacto ataría el test
    a un detalle del ruteo. Lo que se fija es el invariante: el archivo queda
    intacto y `ui` no gana una clave que nadie pidió.
    """
    assert client.get(f"{_URL}/{clave}").status_code >= 400
    assert client.put(f"{_URL}/{clave}", json={"value": 1}).status_code >= 400

    doc = json.loads(client._archivo.read_text(encoding="utf-8")) if client._archivo.exists() else {}
    assert doc.get("ui", {}) == {}


def test_la_clave_larga_o_rara_da_400_en_el_handler(client):
    # Estas sí llegan al handler, así que acá el código SÍ es parte del contrato.
    for clave in ["a" * 129, "ñ", "con espacio"]:
        assert client.put(f"{_URL}/{clave}", json={"value": 1}).status_code == 400


def test_body_sin_value_es_400(client):
    resp = client.put(f"{_URL}/history.views", json={})

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "value_required"


def test_valor_gigante_es_413(client):
    # 64 KB es holgado para un preset: lo que pase de ahí no es una preferencia,
    # es alguien usando el archivo de config como base de datos.
    resp = client.put(f"{_URL}/history.views", json={"value": "x" * 70_000})

    assert resp.status_code == 413
    assert resp.get_json()["error"] == "value_too_large"


def test_el_valor_rechazado_no_queda_guardado(client):
    client.put(f"{_URL}/history.views", json={"value": "ok"})

    client.put(f"{_URL}/history.views", json={"value": "x" * 70_000})

    assert client.get(f"{_URL}/history.views").get_json()["value"] == "ok"


def test_404_con_la_flag_apagada(client, monkeypatch):
    import config as config_mod

    monkeypatch.setattr(config_mod.config, "STACKY_UI_SAVED_VIEWS_ENABLED", False, raising=False)

    assert client.get(f"{_URL}/history.views").status_code == 404
    assert client.put(f"{_URL}/history.views", json={"value": 1}).status_code == 404


# ---------------------------------------------------------------------------
# Convivencia con lo que ya había
# ---------------------------------------------------------------------------

def test_no_pisa_las_preferencias_viejas(client):
    client.put("/api/preferences", json={"pinnedAgents": ["a"]})

    client.put(f"{_URL}/history.views", json={"value": [1]})

    assert client.get("/api/preferences").get_json()["pinnedAgents"] == ["a"]


def test_el_put_legacy_no_puede_pisar_el_sub_objeto_ui(client):
    # El endpoint viejo filtra por allowlist: "ui" no está, así que no entra.
    client.put(f"{_URL}/history.views", json={"value": [1]})

    client.put("/api/preferences", json={"ui": {"history.views": "pisado"}})

    assert client.get(f"{_URL}/history.views").get_json()["value"] == [1]


def test_un_archivo_corrupto_no_rompe_el_store(client):
    client._archivo.write_text("{ esto no es json", encoding="utf-8")

    resp = client.get(f"{_URL}/history.views")

    assert resp.status_code == 200
    assert resp.get_json()["value"] is None


def test_lo_guardado_queda_bajo_la_clave_ui(client):
    client.put(f"{_URL}/history.views", json={"value": [1]})

    doc = json.loads(client._archivo.read_text(encoding="utf-8"))

    assert doc["ui"]["history.views"] == [1]
