"""Plan 176 F6 — Endpoints de preferencias de tabla (parámetro + clave natural).

Ver Stacky Agents/docs/176_PLAN_DB_COMPARE_TRIAGE_CURADO_GATES_READONLY_Y_VERIFICACION_DE_CIERRE.md §F6.

Las preferencias son GLOBALES, no por corrida: marcar RCONTROLES como tabla de
parámetro vale para todas las comparaciones. Por eso el roundtrip GET/PUT es lo
que hay que probar, y que una clave natural inválida se rechace ANTES de quedar
guardada — una clave con una columna que no existe produce un diff de datos que
parece correcto y no lo es.
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

_URL = "/api/db-compare/table-prefs"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    import runtime_paths
    from services import dbcompare_table_prefs

    datos = tmp_path / "data"
    (datos / "db_compare").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: datos)
    monkeypatch.setattr(dbcompare_table_prefs, "data_dir", lambda: datos, raising=False)

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        c._datos = datos
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def _flag(monkeypatch, valor: bool):
    import config as config_mod

    monkeypatch.setattr(config_mod.config, "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED",
                        valor, raising=False)


# ---------------------------------------------------------------------------
# Gate de acceso
# ---------------------------------------------------------------------------

def test_403_con_la_flag_apagada(client, monkeypatch):
    _flag(monkeypatch, False)

    assert client.get(_URL).status_code == 403
    assert client.put(_URL, json={"schema": "main", "table": "RCONTROLES"}).status_code == 403


def test_el_403_dice_que_flag_prender(client, monkeypatch):
    # Un 403 mudo manda al operador a leer código; el nombre de la flag no.
    _flag(monkeypatch, False)

    cuerpo = client.get(_URL).get_json()

    assert "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED" in str(cuerpo)


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------

def test_get_arranca_vacio(client, monkeypatch):
    _flag(monkeypatch, True)

    cuerpo = client.get(_URL).get_json()

    assert cuerpo["ok"] is True
    assert cuerpo["tables"] == {}


def test_put_y_get_devuelven_lo_guardado(client, monkeypatch):
    _flag(monkeypatch, True)

    puesto = client.put(_URL, json={
        "schema": "main", "table": "RCONTROLES",
        "param_table": True, "natural_key": ["MODULO", "CODIGO"],
    })

    assert puesto.status_code == 200, puesto.get_json()

    leido = client.get(_URL).get_json()
    pref = leido["tables"]["main.RCONTROLES"]
    assert pref["param_table"] is True
    assert pref["natural_key"] == ["MODULO", "CODIGO"]


def test_actualizacion_parcial_no_pisa_lo_otro(client, monkeypatch):
    # Tocar solo el flag de parámetro no puede borrar la clave natural que el
    # operador definió a mano hace tres semanas.
    _flag(monkeypatch, True)
    client.put(_URL, json={"schema": "main", "table": "RCONTROLES",
                           "param_table": True, "natural_key": ["MODULO"]})

    client.put(_URL, json={"schema": "main", "table": "RCONTROLES", "param_table": False})

    pref = client.get(_URL).get_json()["tables"]["main.RCONTROLES"]
    assert pref["param_table"] is False
    assert pref["natural_key"] == ["MODULO"]


def test_natural_key_null_borra_la_clave(client, monkeypatch):
    # Mandar null es la única forma de borrarla: omitir el campo la conserva.
    _flag(monkeypatch, True)
    client.put(_URL, json={"schema": "main", "table": "RCONTROLES",
                           "natural_key": ["MODULO"]})

    client.put(_URL, json={"schema": "main", "table": "RCONTROLES", "natural_key": None})

    pref = client.get(_URL).get_json()["tables"]["main.RCONTROLES"]
    assert not pref.get("natural_key")


# ---------------------------------------------------------------------------
# Rechazos
# ---------------------------------------------------------------------------

def test_400_con_clave_natural_invalida(client, monkeypatch):
    # Un nombre con `;` es inyección disfrazada de nombre de columna.
    _flag(monkeypatch, True)

    resp = client.put(_URL, json={"schema": "main", "table": "RCONTROLES",
                                  "natural_key": ["MODULO; DROP TABLE x"]})

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "natural_key_invalida"


def test_la_clave_invalida_no_queda_guardada(client, monkeypatch):
    # Rechazar y guardar igual sería peor que no validar: el operador cree que
    # falló y la clave rota queda activa.
    _flag(monkeypatch, True)

    client.put(_URL, json={"schema": "main", "table": "RCONTROLES",
                           "natural_key": ["MODULO; DROP TABLE x"]})

    assert client.get(_URL).get_json()["tables"] == {}


def test_400_sin_schema_o_tabla(client, monkeypatch):
    _flag(monkeypatch, True)

    assert client.put(_URL, json={"table": "RCONTROLES"}).status_code == 400
    assert client.put(_URL, json={"schema": "main"}).status_code == 400
