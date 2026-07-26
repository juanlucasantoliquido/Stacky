"""Plan 176 F4 — Endpoints de gates y ejecución read-only contra sqlite.

La garantía de solo-lectura es el guard `validate_select_only` corriendo GATE POR
GATE, no una propiedad del motor. Hay un test bloqueante que lo verifica.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_RUN = "run_plan176_gates"
_BASE = f"/api/db-compare/runs/{_RUN}/gates"


def _run_doc(status: str = "done") -> dict:
    return {
        "run_id": _RUN,
        "status": status,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "source_alias": "test-src",
        "target_alias": "test-dst",
        "engine": "sqlite",
        "diff": {"version": 1, "engine": "sqlite", "items": [{
            "object_type": "table", "schema": "main", "name": "CLIENTES",
            "action": "changed", "severity": "danger",
            "changes": [{"kind": "column_nullable_tightened", "severity": "danger",
                         "detail": {"column": "RUT"}}],
        }]},
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    import runtime_paths
    from services import dbcompare_gates, dbcompare_runs

    datos = tmp_path / "data"
    (datos / "db_compare" / "runs").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: datos)
    monkeypatch.setattr(dbcompare_runs, "data_dir", lambda: datos, raising=False)
    monkeypatch.setattr(dbcompare_gates, "_gates_dir",
                        lambda: datos / "db_compare" / "gates")

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


def _sembrar_run(client, status: str = "done") -> None:
    destino = client._datos / "db_compare" / "runs" / f"{_RUN}.json"
    destino.write_text(json.dumps(_run_doc(status), ensure_ascii=False), encoding="utf-8")


def _sembrar_sqlite(tmp_path, con_nulls: bool):
    """Base sqlite real con o sin NULLs en la columna que el diff endurece."""
    import sqlite3

    archivo = tmp_path / "destino.sqlite"
    con = sqlite3.connect(archivo)
    con.execute("CREATE TABLE CLIENTES (ID INTEGER, RUT TEXT)")
    con.execute("INSERT INTO CLIENTES VALUES (1, '11.111.111-1')")
    if con_nulls:
        con.execute("INSERT INTO CLIENTES VALUES (2, NULL)")
    con.commit()
    con.close()
    return archivo


def _enganchar_engine(monkeypatch, archivo):
    from sqlalchemy import create_engine

    from services import dbcompare_engine

    monkeypatch.setattr(dbcompare_engine, "open_engine",
                        lambda alias, **kw: create_engine(f"sqlite:///{archivo}"))


# ---------------------------------------------------------------------------
# Gates de acceso
# ---------------------------------------------------------------------------

def test_gates_403_si_flag_off(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DB_COMPARE_GATES_ENABLED", False, raising=False)
    _sembrar_run(client)

    assert client.get(_BASE).status_code == 403
    assert client.post(f"{_BASE}/evaluate", json={}).status_code == 403
    assert client.get(f"{_BASE}/export.sql").status_code == 403


def test_get_gates_404_run_inexistente(client):
    assert client.get("/api/db-compare/runs/no_existe/gates").status_code == 404


def test_get_gates_409_run_no_done(client):
    _sembrar_run(client, status="running")

    assert client.get(_BASE).status_code == 409
    assert client.post(f"{_BASE}/evaluate", json={}).status_code == 409


def test_get_gates_lista_las_derivadas(client):
    _sembrar_run(client)

    body = client.get(_BASE).get_json()

    assert body["ok"] is True
    assert len(body["gates"]) == 1
    assert body["gates"][0]["kind"] == "null_count"
    assert body["results"] == {}


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

def test_evaluate_pasa_por_validate_select_only(client, monkeypatch, tmp_path):
    """BLOQUEANTE: la garantía de solo-lectura es ESTE guard, gate por gate."""
    from services import dbcompare_gates
    from services.db_query import validate_select_only as real

    llamadas: list = []

    def _espia(sql):
        llamadas.append(sql)
        return real(sql)

    monkeypatch.setattr("services.db_query.validate_select_only", _espia)
    _enganchar_engine(monkeypatch, _sembrar_sqlite(tmp_path, con_nulls=False))
    _sembrar_run(client)

    client.post(f"{_BASE}/evaluate", json={})

    assert len(llamadas) == 1, "cada gate tiene que pasar por el guard antes de correr"
    assert "SELECT COUNT(*)" in llamadas[0]


def test_gate_que_no_pasa_el_guard_no_se_ejecuta(client, monkeypatch, tmp_path):
    from services import db_query, dbcompare_gates

    monkeypatch.setattr(db_query, "validate_select_only",
                        lambda sql: db_query.QueryValidation(ok=False, errors=["no"]))

    def _explota(*a, **kw):
        raise AssertionError("no se puede abrir el motor si el guard rechazó")

    from services import dbcompare_engine
    monkeypatch.setattr(dbcompare_engine, "open_engine", _explota)
    _sembrar_run(client)

    body = client.post(f"{_BASE}/evaluate", json={}).get_json()

    resultado = list(body["results"].values())[0]
    assert resultado["status"] == "error"
    assert "solo-lectura" in resultado["detail"]


def test_evaluate_null_count_fail_con_nulls(client, monkeypatch, tmp_path):
    _enganchar_engine(monkeypatch, _sembrar_sqlite(tmp_path, con_nulls=True))
    _sembrar_run(client)

    body = client.post(f"{_BASE}/evaluate", json={}).get_json()

    resultado = list(body["results"].values())[0]
    assert resultado["status"] == "fail"
    assert resultado["value"] == 1
    assert "impiden aplicar" in resultado["detail"]


def test_evaluate_pass_sin_nulls(client, monkeypatch, tmp_path):
    _enganchar_engine(monkeypatch, _sembrar_sqlite(tmp_path, con_nulls=False))
    _sembrar_run(client)

    body = client.post(f"{_BASE}/evaluate", json={}).get_json()

    resultado = list(body["results"].values())[0]
    assert resultado["status"] == "pass" and resultado["value"] == 0


def test_resultados_persisten_y_get_los_devuelve(client, monkeypatch, tmp_path):
    _enganchar_engine(monkeypatch, _sembrar_sqlite(tmp_path, con_nulls=True))
    _sembrar_run(client)
    client.post(f"{_BASE}/evaluate", json={})

    body = client.get(_BASE).get_json()

    assert list(body["results"].values())[0]["status"] == "fail"


def test_error_de_conexion_no_tumba_la_evaluacion(client, monkeypatch, tmp_path):
    from services import dbcompare_engine

    def _falla(*a, **kw):
        raise RuntimeError("no se pudo conectar a la base")

    monkeypatch.setattr(dbcompare_engine, "open_engine", _falla)
    _sembrar_run(client)

    body = client.post(f"{_BASE}/evaluate", json={}).get_json()

    assert list(body["results"].values())[0]["status"] == "error"


def test_cap_de_gates_devuelve_400(client, monkeypatch, tmp_path):
    from services import dbcompare_gates

    monkeypatch.setattr(dbcompare_gates, "_MAX_GATES_PER_EVAL", 0)
    _sembrar_run(client)

    r = client.post(f"{_BASE}/evaluate", json={})

    assert r.status_code == 400
    assert "too_many_gates" in r.get_json()["error"]


def test_gate_ids_filtra(client, monkeypatch, tmp_path):
    _enganchar_engine(monkeypatch, _sembrar_sqlite(tmp_path, con_nulls=False))
    _sembrar_run(client)

    body = client.post(f"{_BASE}/evaluate", json={"gate_ids": ["no_existe"]}).get_json()

    assert body["results"] == {}, "pedir una gate inexistente no ejecuta nada"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_sql_descargable(client):
    _sembrar_run(client)

    r = client.get(f"{_BASE}/export.sql")

    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    cuerpo = r.get_data(as_text=True)
    assert "-- GATE g001_null_count" in cuerpo and "-- esperado: 0" in cuerpo
