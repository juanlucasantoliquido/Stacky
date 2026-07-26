"""Plan 176 F6 — Tablas de parámetro y claves naturales.

Salda dos molestias reales: volver a tildar las mismas tablas en cada corrida, y
que una tabla sin PK sea "no comparable" aunque el operador conozca su clave.
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

from services import dbcompare_table_prefs as P  # noqa: E402


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_prefs_path", lambda: tmp_path / "table_prefs.json")
    return tmp_path


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def test_sin_archivo_devuelve_vacio(almacen):
    assert P.load_prefs() == {"version": P.PREFS_VERSION, "tables": {}}


def test_set_pref_persiste_clave_natural(almacen):
    P.set_pref("dbo", "RCONTROLES", natural_key=["CODIGO", "TIPO"])

    assert P.natural_key_for("dbo", "RCONTROLES") == ["CODIGO", "TIPO"]
    assert not list(almacen.glob("*.tmp")), "quedó un temporal sin renombrar"


def test_set_pref_es_parcial(almacen):
    """Tocar el flag de parámetro no puede borrar la clave que ya estaba."""
    P.set_pref("dbo", "T", natural_key=["ID"])
    P.set_pref("dbo", "T", param_table=True)

    assert P.natural_key_for("dbo", "T") == ["ID"]
    assert P.is_param_table("dbo", "T") is True


def test_natural_key_none_explicito_borra(almacen):
    P.set_pref("dbo", "T", natural_key=["ID"])
    P.set_pref("dbo", "T", natural_key=None)

    assert P.natural_key_for("dbo", "T") is None


def test_rechaza_nombres_de_columna_invalidos(almacen):
    """Lo que entra acá termina en un SELECT: no puede ser una expresión."""
    for malo in (["ID; DROP TABLE X"], ["col con espacio"], ["a" * 200], [""], []):
        with pytest.raises(ValueError):
            P.set_pref("dbo", "T", natural_key=malo)


def test_rechaza_columnas_repetidas(almacen):
    with pytest.raises(ValueError):
        P.set_pref("dbo", "T", natural_key=["ID", "ID"])


def test_acepta_nombres_con_guion_bajo_y_signos_de_oracle(almacen):
    P.set_pref("dbo", "T", natural_key=["COD_1", "X$Y", "A#B"])

    assert P.natural_key_for("dbo", "T") == ["COD_1", "X$Y", "A#B"]


def test_param_tables_ordenada(almacen):
    P.set_pref("dbo", "Z", param_table=True)
    P.set_pref("dbo", "A", param_table=True)
    P.set_pref("dbo", "M", param_table=False)

    assert P.param_tables() == ["dbo.A", "dbo.Z"]


def test_archivo_corrupto_no_rompe(almacen):
    (almacen / "table_prefs.json").write_text("no soy json", encoding="utf-8")

    assert P.load_prefs()["tables"] == {}
    assert P.natural_key_for("dbo", "T") is None


def test_documento_serializado(almacen):
    P.set_pref("dbo", "T", natural_key=["ID"], param_table=True)

    doc = json.loads((almacen / "table_prefs.json").read_text(encoding="utf-8"))

    assert doc["version"] == P.PREFS_VERSION
    assert doc["tables"]["dbo.T"]["updated_at"]


# ---------------------------------------------------------------------------
# Integración con el diff de datos
# ---------------------------------------------------------------------------

def _snapshot(alias: str, columnas: list, pk: list) -> dict:
    return {
        "alias": alias,
        "engine": "sqlite",
        "schemas": {"main": {"tables": {"SINPK": {
            "columns": [{"name": c, "type": "varchar"} for c in columnas],
            "primary_key": {"columns": pk},
            "indexes": [], "foreign_keys": [], "unique_constraints": [],
            "check_constraints": [],
        }}, "views": {}, "sequences": []}},
    }


def _engines_sqlite(tmp_path):
    """Bases sqlite reales: `diff_table_data` acepta `engines=` justamente para
    no tener que mockear su interior."""
    import sqlite3

    from sqlalchemy import create_engine

    motores = []
    for lado in ("src", "dst"):
        archivo = tmp_path / f"{lado}.sqlite"
        con = sqlite3.connect(archivo)
        con.execute("CREATE TABLE SINPK (CODIGO TEXT, VALOR TEXT, ID TEXT)")
        con.commit()
        con.close()
        motores.append(create_engine(f"sqlite:///{archivo}"))
    return tuple(motores)


@pytest.fixture
def datos_mockeados(monkeypatch, tmp_path):
    from services import dbcompare_data, dbcompare_snapshot

    monkeypatch.setattr(dbcompare_snapshot, "latest_snapshot",
                        lambda alias: _snapshot(alias, ["CODIGO", "VALOR"], []))
    dbcompare_data._engines_test = _engines_sqlite(tmp_path)
    return dbcompare_data


def test_tabla_sin_pk_con_clave_natural_es_comparable(datos_mockeados):
    resultado = datos_mockeados.diff_table_data(
        "src", "dst", "main", "SINPK", key_cols=["CODIGO"],
        engines=datos_mockeados._engines_test)

    assert resultado["pk_cols"] == ["CODIGO"]
    assert resultado["key_source"] == "natural", \
        "pk_cols conserva su semántica congelada; key_source dice de dónde salió"


def test_tabla_sin_pk_sin_clave_sigue_rechazada(datos_mockeados):
    with pytest.raises(datos_mockeados.DbCompareDataError, match="no tiene PK"):
        datos_mockeados.diff_table_data("src", "dst", "main", "SINPK",
                                        engines=datos_mockeados._engines_test)


def test_clave_natural_con_columna_inexistente_falla_claro(datos_mockeados):
    with pytest.raises(datos_mockeados.DbCompareDataError, match="no existen"):
        datos_mockeados.diff_table_data(
            "src", "dst", "main", "SINPK", key_cols=["NO_EXISTE"],
            engines=datos_mockeados._engines_test)


def test_tabla_con_pk_reporta_key_source_pk(monkeypatch, tmp_path):
    from services import dbcompare_data, dbcompare_snapshot

    monkeypatch.setattr(dbcompare_snapshot, "latest_snapshot",
                        lambda alias: _snapshot(alias, ["ID", "VALOR"], ["ID"]))

    resultado = dbcompare_data.diff_table_data(
        "src", "dst", "main", "SINPK", engines=_engines_sqlite(tmp_path))

    assert resultado["key_source"] == "pk" and resultado["pk_cols"] == ["ID"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setattr(P, "_prefs_path", lambda: tmp_path / "table_prefs.json")

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


def test_403_si_flag_off(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED", False,
                        raising=False)

    assert client.get("/api/db-compare/table-prefs").status_code == 403
    assert client.put("/api/db-compare/table-prefs", json={}).status_code == 403


def test_get_devuelve_el_documento(client):
    body = client.get("/api/db-compare/table-prefs").get_json()

    assert body["ok"] is True and body["tables"] == {}


def test_put_guarda_y_get_lo_devuelve(client):
    r = client.put("/api/db-compare/table-prefs", json={
        "schema": "dbo", "table": "RCONTROLES",
        "natural_key": ["CODIGO"], "param_table": True})

    assert r.status_code == 200
    leido = client.get("/api/db-compare/table-prefs").get_json()
    assert leido["tables"]["dbo.RCONTROLES"]["natural_key"] == ["CODIGO"]
    assert leido["tables"]["dbo.RCONTROLES"]["param_table"] is True


def test_put_sin_schema_o_table_400(client):
    assert client.put("/api/db-compare/table-prefs",
                      json={"table": "T"}).status_code == 400


def test_put_clave_invalida_400(client):
    r = client.put("/api/db-compare/table-prefs", json={
        "schema": "dbo", "table": "T", "natural_key": ["mal; DROP"]})

    assert r.status_code == 400 and r.get_json()["error"] == "natural_key_invalida"


def test_put_parcial_no_pisa_lo_otro(client):
    client.put("/api/db-compare/table-prefs", json={
        "schema": "dbo", "table": "T", "natural_key": ["ID"]})
    client.put("/api/db-compare/table-prefs", json={
        "schema": "dbo", "table": "T", "param_table": True})

    entrada = client.get("/api/db-compare/table-prefs").get_json()["tables"]["dbo.T"]
    assert entrada["natural_key"] == ["ID"] and entrada["param_table"] is True
