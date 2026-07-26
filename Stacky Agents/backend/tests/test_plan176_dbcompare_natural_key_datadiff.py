"""Plan 176 F6 — La clave natural declarada tiene que LLEGAR al diff de datos.

Ver Stacky Agents/docs/176_PLAN_DB_COMPARE_TRIAGE_CURADO_GATES_READONLY_Y_VERIFICACION_DE_CIERRE.md §F6.
**Bloqueante (KPI-3 y KPI-5).**

Guardar la preferencia y no consultarla es el falso verde perfecto: la pantalla
muestra la clave definida, el operador cree que RCONTROLES ya se compara, y la
tabla sigue apareciendo "sin PK, no comparable". Por eso acá NO se testea el
almacén (eso es table_prefs_api) sino el CAMINO COMPLETO: preferencia →
candidatas → diff real con filas.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def _sembrar(archivo: Path, filas: list[tuple]):
    """Tabla SIN primary key — el caso que hoy queda afuera del diff de datos."""
    con = sqlite3.connect(archivo)
    con.execute("CREATE TABLE RCONTROLES (MODULO TEXT, CODIGO TEXT, VALOR TEXT)")
    con.executemany("INSERT INTO RCONTROLES VALUES (?, ?, ?)", filas)
    con.commit()
    con.close()


@pytest.fixture
def fake_keyring(monkeypatch):
    import services.dbcompare_registry as reg

    store: dict = {}

    class _FakeKeyring:
        @staticmethod
        def set_password(service, alias, password):
            store[(service, alias)] = password

        @staticmethod
        def get_password(service, alias):
            return store.get((service, alias))

        @staticmethod
        def delete_password(service, alias):
            store.pop((service, alias), None)

    monkeypatch.setattr(reg, "keyring", _FakeKeyring())
    return store


@pytest.fixture
def entorno(fake_keyring, tmp_path, monkeypatch):
    """Par sqlite `test-*` con una fila de más en el origen."""
    from sqlalchemy import create_engine

    import services.dbcompare_data as data
    import services.dbcompare_engine as engine_mod
    import services.dbcompare_registry as reg
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap
    import services.dbcompare_table_prefs as prefs

    for mod in (reg, snap, runs, prefs):
        monkeypatch.setattr(mod, "data_dir", lambda: tmp_path, raising=False)

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _sembrar(db_a, [("GEN", "1", "si"), ("GEN", "2", "no")])
    _sembrar(db_b, [("GEN", "1", "si")])  # falta la fila 2 ⇒ only_source

    reg.upsert_environment("test-a", "sqlite", "localhost", 0, str(db_a), "user")
    reg.upsert_environment("test-b", "sqlite", "localhost", 0, str(db_b), "user")
    reg.set_password("test-a", "unused")
    reg.set_password("test-b", "unused")

    eng_a = create_engine(f"sqlite:///{db_a}")
    eng_b = create_engine(f"sqlite:///{db_b}")

    def _open(alias, **kw):
        return eng_a if alias == "test-a" else eng_b

    monkeypatch.setattr(engine_mod, "open_engine", _open)
    monkeypatch.setattr(data, "open_engine", _open, raising=False)

    snap.take_snapshot("test-a", engine=eng_a)
    snap.take_snapshot("test-b", engine=eng_b)
    return {"eng_a": eng_a, "eng_b": eng_b, "tmp_path": tmp_path}


# ---------------------------------------------------------------------------
# El motor: la clave natural produce un diff REAL
# ---------------------------------------------------------------------------

def test_sin_pk_y_sin_clave_natural_no_es_comparable(entorno):
    # Punto de partida: hoy esta tabla queda afuera.
    from services import dbcompare_data

    with pytest.raises(dbcompare_data.DbCompareDataError, match="no tiene PK"):
        dbcompare_data.diff_table_data(
            "test-a", "test-b", "main", "RCONTROLES",
            engines=(entorno["eng_a"], entorno["eng_b"]),
        )


def test_con_clave_natural_produce_el_diff_correcto(entorno):
    from services import dbcompare_data

    res = dbcompare_data.diff_table_data(
        "test-a", "test-b", "main", "RCONTROLES",
        engines=(entorno["eng_a"], entorno["eng_b"]),
        key_cols=["MODULO", "CODIGO"],
    )

    assert res["key_source"] == "natural"
    # Aserción discriminante: no alcanza con que no explote, tiene que ENCONTRAR
    # la fila que falta en destino.
    assert len(res["only_source"]) == 1
    assert not res["only_target"]


def test_clave_con_columna_inexistente_es_error(entorno):
    # Una clave sobre una columna que no existe daría un diff que parece correcto
    # y no lo es: mejor romper fuerte.
    from services import dbcompare_data

    with pytest.raises(dbcompare_data.DbCompareDataError, match="no existen"):
        dbcompare_data.diff_table_data(
            "test-a", "test-b", "main", "RCONTROLES",
            engines=(entorno["eng_a"], entorno["eng_b"]),
            key_cols=["COLUMNA_FANTASMA"],
        )


# ---------------------------------------------------------------------------
# El cableado: la preferencia guardada tiene que LLEGAR
# ---------------------------------------------------------------------------

def _flags(monkeypatch, *, prefs_on: bool):
    import config as config_mod

    monkeypatch.setattr(config_mod.config, "STACKY_DB_COMPARE_ENABLED", True, raising=False)
    monkeypatch.setattr(config_mod.config, "STACKY_DB_COMPARE_DATA_DIFF_ENABLED", True, raising=False)
    monkeypatch.setattr(config_mod.config, "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED",
                        prefs_on, raising=False)


@pytest.fixture
def client(entorno, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: entorno["tmp_path"])

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


def _run_done(entorno):
    import services.dbcompare_runs as runs

    run = runs.create_run("test-a", "test-b", mode="cached")
    limite = time.monotonic() + 5
    while time.monotonic() < limite:
        actual = runs.get_run(run["run_id"])
        if actual and actual["status"] in ("done", "error"):
            assert actual["status"] == "done", actual
            return run["run_id"]
        time.sleep(0.05)
    raise AssertionError("la corrida no terminó")


def test_candidata_sin_pk_pasa_a_comparable_con_la_clave_declarada(client, entorno, monkeypatch):
    """El test que hace que esto no sea un adorno."""
    from services import dbcompare_table_prefs

    _flags(monkeypatch, prefs_on=True)
    run_id = _run_done(entorno)
    dbcompare_table_prefs.set_pref("main", "RCONTROLES", natural_key=["MODULO", "CODIGO"])

    resp = client.get(f"/api/db-compare/runs/{run_id}/data-candidates")

    assert resp.status_code == 200, resp.get_json()
    cand = next(c for c in resp.get_json()["candidates"] if c["table"] == "RCONTROLES")
    assert cand["comparable"] is True
    assert cand["key_source"] == "natural"
    assert cand["key_cols"] == ["MODULO", "CODIGO"]
    assert cand["has_pk"] is False  # sigue sin PK: la clave es del operador, no del motor


def test_clave_invalida_marca_la_candidata_con_su_razon(client, entorno, monkeypatch):
    from services import dbcompare_table_prefs

    _flags(monkeypatch, prefs_on=True)
    run_id = _run_done(entorno)
    dbcompare_table_prefs.set_pref("main", "RCONTROLES", natural_key=["COLUMNA_FANTASMA"])

    resp = client.get(f"/api/db-compare/runs/{run_id}/data-candidates")

    cand = next(c for c in resp.get_json()["candidates"] if c["table"] == "RCONTROLES")
    assert cand["comparable"] is False
    assert cand["reason"] == "natural_key_invalid"


def test_tabla_de_parametro_viaja_a_la_candidata(client, entorno, monkeypatch):
    from services import dbcompare_table_prefs

    _flags(monkeypatch, prefs_on=True)
    run_id = _run_done(entorno)
    dbcompare_table_prefs.set_pref("main", "RCONTROLES", param_table=True)

    resp = client.get(f"/api/db-compare/runs/{run_id}/data-candidates")

    cand = next(c for c in resp.get_json()["candidates"] if c["table"] == "RCONTROLES")
    assert cand["param_table"] is True


def test_el_diff_de_datos_usa_la_clave_declarada(client, entorno, monkeypatch):
    """Sin esto, la candidata diría comparable y el diff seguiría fallando."""
    import services.dbcompare_runs as runs
    from services import dbcompare_table_prefs

    _flags(monkeypatch, prefs_on=True)
    run_id = _run_done(entorno)
    dbcompare_table_prefs.set_pref("main", "RCONTROLES", natural_key=["MODULO", "CODIGO"])

    resp = client.post(f"/api/db-compare/runs/{run_id}/data-diff",
                       json={"tables": [{"schema": "main", "table": "RCONTROLES"}]})
    assert resp.status_code == 202, resp.get_json()

    limite = time.monotonic() + 5
    tabla = None
    while time.monotonic() < limite:
        actual = runs.get_run(run_id)
        dd = (actual or {}).get("data_diff") or {}
        if dd.get("status") in ("done", "error"):
            tabla = dd["tables"]["main.RCONTROLES"]
            break
        time.sleep(0.05)

    assert tabla is not None, "el diff de datos no terminó"
    assert "error" not in tabla, tabla
    assert tabla["key_source"] == "natural"
    assert len(tabla["only_source"]) == 1


# ---------------------------------------------------------------------------
# Flag OFF ⇒ EXACTAMENTE como main
# ---------------------------------------------------------------------------

def test_flag_off_deja_la_respuesta_identica_a_main(client, entorno, monkeypatch):
    from services import dbcompare_table_prefs

    _flags(monkeypatch, prefs_on=False)
    run_id = _run_done(entorno)
    # Preferencia guardada pero flag apagada: no debe influir en NADA.
    dbcompare_table_prefs.set_pref("main", "RCONTROLES", natural_key=["MODULO", "CODIGO"],
                                   param_table=True)

    cand = next(c for c in client.get(f"/api/db-compare/runs/{run_id}/data-candidates")
                .get_json()["candidates"] if c["table"] == "RCONTROLES")

    assert cand["comparable"] is False
    assert "key_source" not in cand
    assert "param_table" not in cand
    assert "key_cols" not in cand


def test_flag_off_las_claves_de_la_candidata_son_las_de_siempre(client, entorno, monkeypatch):
    # Contrato exacto de main: ni una clave de más.
    _flags(monkeypatch, prefs_on=False)
    run_id = _run_done(entorno)

    cand = client.get(f"/api/db-compare/runs/{run_id}/data-candidates").get_json()["candidates"][0]

    assert set(cand) == {
        "schema", "table", "has_pk", "estimated_columns", "comparable", "reason",
        "row_count_source", "row_count_target",
    }
