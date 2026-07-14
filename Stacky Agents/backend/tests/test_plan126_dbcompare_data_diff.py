"""Plan 126 F2 — Diff de datos por PK (services/dbcompare_data.py).

Ver Stacky Agents/docs/126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md #F2.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest
from sqlalchemy import create_engine, text


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


def _seed_params(path, rows, extra_col=False, with_pk=True):
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as c:
        pk_clause = "ID INTEGER PRIMARY KEY" if with_pk else "ID INTEGER"
        extra = ", EXTRA TEXT" if extra_col else ""
        c.execute(text(f"CREATE TABLE PARAMS ({pk_clause}, NOMBRE TEXT, VALOR REAL{extra})"))
        for row in rows:
            if extra_col:
                c.execute(text("INSERT INTO PARAMS (ID, NOMBRE, VALOR, EXTRA) VALUES (:id,:n,:v,'x')"),
                          {"id": row[0], "n": row[1], "v": row[2]})
            else:
                c.execute(text("INSERT INTO PARAMS (ID, NOMBRE, VALOR) VALUES (:id,:n,:v)"),
                          {"id": row[0], "n": row[1], "v": row[2]})
        c.commit()
    return eng


@pytest.fixture
def two_envs(fake_keyring, tmp_path, monkeypatch):
    import services.dbcompare_data as data
    import services.dbcompare_registry as reg
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap

    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(runs, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(data, "data_dir", lambda: tmp_path, raising=False)

    reg.upsert_environment("test-src", "sqlite", "localhost", 0, str(tmp_path / "src.db"), "user")
    reg.upsert_environment("test-tgt", "sqlite", "localhost", 0, str(tmp_path / "tgt.db"), "user")
    reg.set_password("test-src", "unused")
    reg.set_password("test-tgt", "unused")
    return {"tmp_path": tmp_path}


def _wait_done(runs_mod, run_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    final = runs_mod.get_run(run_id)
    while time.monotonic() < deadline:
        final = runs_mod.get_run(run_id)
        if final and final["status"] in ("done", "error"):
            return final
        time.sleep(0.02)
    return final


def _wait_data_diff_done(run_id, timeout=5.0):
    import services.dbcompare_runs as runs

    deadline = time.monotonic() + timeout
    final = runs.get_run(run_id)
    while time.monotonic() < deadline:
        final = runs.get_run(run_id)
        dd = (final or {}).get("data_diff") or {}
        if dd.get("status") in ("done", "error"):
            return final
        time.sleep(0.02)
    return final


def _seed_two(tmp_path, src_rows, tgt_rows, src_extra=False, tgt_extra=False, src_pk=True):
    src_path = tmp_path / "src.db"
    tgt_path = tmp_path / "tgt.db"
    _seed_params(src_path, src_rows, extra_col=src_extra, with_pk=src_pk)
    _seed_params(tgt_path, tgt_rows, extra_col=tgt_extra)


def _take_both_snapshots():
    import services.dbcompare_snapshot as snap

    snap.take_snapshot("test-src")
    snap.take_snapshot("test-tgt")


# ---------------------------------------------------------------------------
# build_select — golden por dialecto (puro, sin DB)
# ---------------------------------------------------------------------------


def test_build_select_golden_por_dialecto():
    import services.dbcompare_data as data

    sql_sqlserver = data.build_select("main", "PARAMS", ["ID", "NOMBRE"], ["ID"], "sqlserver", 100)
    assert sql_sqlserver == 'SELECT TOP (101) [ID], [NOMBRE] FROM [main].[PARAMS] ORDER BY [ID]'

    sql_oracle = data.build_select("main", "PARAMS", ["ID", "NOMBRE"], ["ID"], "oracle", 100)
    assert sql_oracle == (
        'SELECT "ID", "NOMBRE" FROM (SELECT "ID", "NOMBRE" FROM "MAIN"."PARAMS" ORDER BY "ID") '
        'WHERE ROWNUM <= 101'
    )

    sql_sqlite = data.build_select("main", "PARAMS", ["ID", "NOMBRE"], ["ID"], "sqlite", 100)
    assert sql_sqlite == 'SELECT "ID", "NOMBRE" FROM "main"."PARAMS" ORDER BY "ID" LIMIT 101'


# ---------------------------------------------------------------------------
# diff_table_data — KPI-1 y casos de columnas/errores
# ---------------------------------------------------------------------------


def test_kpi1_exacto(two_envs):
    import services.dbcompare_data as data

    _seed_two(
        two_envs["tmp_path"],
        src_rows=[(1, "A", 1.5), (2, "B", 2.0), (3, "C", 3.0)],
        tgt_rows=[(1, "A", 1.5), (2, "B-mod", 2.0), (4, "D", 4.0)],
    )
    _take_both_snapshots()

    result = data.diff_table_data("test-src", "test-tgt", "main", "PARAMS")

    assert [r["ID"] for r in result["only_source"]] == ["3"]
    assert [r["ID"] for r in result["only_target"]] == ["4"]
    assert len(result["changed"]) == 1
    changed = result["changed"][0]
    assert changed["pk"] == {"ID": "2"}
    assert changed["cells"] == {"NOMBRE": {"source": "B", "target": "B-mod"}}
    assert result["truncated"] is False
    assert result["identical"] is False
    # column_types (addendum F2, necesario para F3 emit_data_scripts: el DataDiff
    # solo trae valores NORMALIZADOS/strings, sql_literal_from_normalized necesita
    # el tipo real de columna del snapshot para renderizar el literal correcto).
    assert result["column_types"]["ID"].startswith("INT")
    assert set(result["column_types"]) == set(result["columns"])


def test_truncated_con_cap(two_envs):
    import services.dbcompare_data as data

    _seed_two(
        two_envs["tmp_path"],
        src_rows=[(1, "A", 1.0), (2, "B", 2.0), (3, "C", 3.0)],
        tgt_rows=[(1, "A", 1.0), (2, "B", 2.0), (3, "C", 3.0)],
    )
    _take_both_snapshots()

    result = data.diff_table_data("test-src", "test-tgt", "main", "PARAMS", max_rows=2)
    assert result["truncated"] is True


def test_sin_pk_error_claro(two_envs):
    import services.dbcompare_data as data

    _seed_two(
        two_envs["tmp_path"],
        src_rows=[(1, "A", 1.0)],
        tgt_rows=[(1, "A", 1.0)],
        src_pk=False,
    )
    _take_both_snapshots()

    with pytest.raises(data.DbCompareDataError, match="no tiene PK"):
        data.diff_table_data("test-src", "test-tgt", "main", "PARAMS")


def test_columnas_interseccion_origen_destino(two_envs):
    """[FIX C3] columna EXTRA en el DESTINO -> columns_skipped, nunca en el SELECT."""
    import services.dbcompare_data as data

    _seed_two(
        two_envs["tmp_path"],
        src_rows=[(1, "A", 1.0)],
        tgt_rows=[(1, "A", 1.0)],
        tgt_extra=True,
    )
    _take_both_snapshots()

    result = data.diff_table_data("test-src", "test-tgt", "main", "PARAMS")
    assert "EXTRA" not in result["columns"]
    assert "EXTRA" in result["columns_skipped"]


def test_tabla_no_existe_en_destino_error_claro(two_envs):
    """[FIX C3] tabla presente en origen pero ausente en destino -> error claro, no crash."""
    import services.dbcompare_data as data
    import services.dbcompare_registry as reg
    import services.dbcompare_snapshot as snap

    src_path = two_envs["tmp_path"] / "src.db"
    tgt_path = two_envs["tmp_path"] / "tgt.db"
    _seed_params(src_path, [(1, "A", 1.0)])
    eng_empty = create_engine(f"sqlite:///{tgt_path}")
    with eng_empty.connect() as c:
        c.execute(text("CREATE TABLE OTRA (ID INTEGER PRIMARY KEY)"))
        c.commit()

    snap.take_snapshot("test-src")
    snap.take_snapshot("test-tgt")

    with pytest.raises(data.DbCompareDataError, match="no existe en 'test-tgt'"):
        data.diff_table_data("test-src", "test-tgt", "main", "PARAMS")


def test_kpi2_validador_siempre(two_envs, monkeypatch):
    import services.dbcompare_data as data

    _seed_two(
        two_envs["tmp_path"],
        src_rows=[(1, "A", 1.0)],
        tgt_rows=[(1, "A", 1.0)],
    )
    _take_both_snapshots()

    calls = {"n": 0}
    original = data.validate_select_only

    def _counting(sql):
        calls["n"] += 1
        return original(sql)

    monkeypatch.setattr(data, "validate_select_only", _counting)
    data.diff_table_data("test-src", "test-tgt", "main", "PARAMS")
    # 1 SELECT ejecutado por lado (source + target) == 2 llamadas al validador.
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# run_data_diff — threaded + lock + escritura en el archivo del run
# ---------------------------------------------------------------------------


def test_run_data_diff_thread_y_lock(two_envs):
    import services.dbcompare_data as data
    import services.dbcompare_runs as runs

    _seed_two(
        two_envs["tmp_path"],
        src_rows=[(1, "A", 1.0), (2, "B", 2.0)],
        tgt_rows=[(1, "A", 1.0), (2, "B-mod", 2.0)],
    )
    _take_both_snapshots()

    run = runs.create_run("test-src", "test-tgt", mode="cached")
    schema_run = _wait_done(runs, run["run_id"])
    assert schema_run["status"] == "done"

    data.run_data_diff(run["run_id"], [{"schema": "main", "table": "PARAMS"}])
    with pytest.raises(data.DbCompareDataError, match="ya hay"):
        data.run_data_diff(run["run_id"], [{"schema": "main", "table": "PARAMS"}])

    final = _wait_data_diff_done(run["run_id"])
    dd = final["data_diff"]
    assert dd["status"] == "done"
    assert "main.PARAMS" in dd["tables"]
    assert dd["tables"]["main.PARAMS"]["changed"]


def test_run_data_diff_mas_de_20_tablas(two_envs):
    import services.dbcompare_data as data

    tables = [{"schema": "main", "table": f"T{i}"} for i in range(21)]
    with pytest.raises(data.DbCompareDataError, match="20"):
        data.run_data_diff("cualquier_run_id", tables)
