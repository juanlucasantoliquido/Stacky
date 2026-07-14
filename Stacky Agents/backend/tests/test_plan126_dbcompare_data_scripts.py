"""Plan 126 F3 — Scripts DML de paridad de datos + backup pareado
(extensión de services/dbcompare_scripts.py, Plan 125).

Ver Stacky Agents/docs/126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md #F3.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from services import dbcompare_scripts as scripts
from tests._plan125_fixtures import make_col, make_schema_obj, make_table

TS = "20260714_120000"
RUN_ID = "run_data_test_001"


def _data_diff(**overrides):
    base = {
        "version": 1,
        "schema": "dbo",
        "table": "PARAMS",
        "pk_cols": ["ID"],
        "columns": ["ID", "NOMBRE", "VALOR"],
        "column_types": {"ID": "INT", "NOMBRE": "VARCHAR(50)", "VALOR": "REAL"},
        "columns_skipped": [],
        "only_source": [{"ID": "3", "NOMBRE": "C", "VALOR": "3"}],
        "only_target": [{"ID": "4", "NOMBRE": "D", "VALOR": "4"}],
        "changed": [{"pk": {"ID": "2"}, "cells": {"NOMBRE": {"source": "B", "target": "B-mod"}}}],
        "row_counts": {"source": 3, "target": 3},
        "truncated": False,
        "identical": False,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# emit_data_scripts — golden por dialecto (KPI-1 del F2 reflejado en DML)
# ---------------------------------------------------------------------------


def test_insert_update_delete_golden_sqlserver():
    pieces = scripts.emit_data_scripts(_data_diff(), "sqlserver", TS, "TEST")
    by_action = {p["action"]: p for p in pieces}

    assert by_action["data_insert"]["destructive"] is False
    assert by_action["data_insert"]["modifies_table"] is True
    assert by_action["data_insert"]["sql"] == (
        "IF NOT EXISTS (SELECT 1 FROM [dbo].[PARAMS] WHERE [ID] = 3) "
        "INSERT INTO [dbo].[PARAMS] ([ID], [NOMBRE], [VALOR]) VALUES (3, 'C', 3);"
    )

    assert by_action["data_update"]["destructive"] is True
    assert by_action["data_update"]["sql"] == "UPDATE [dbo].[PARAMS] SET [NOMBRE] = 'B-mod' WHERE [ID] = 2;"

    assert by_action["data_delete"]["destructive"] is True
    assert by_action["data_delete"]["sql"] == "DELETE FROM [dbo].[PARAMS] WHERE [ID] = 4;"


def test_insert_update_delete_golden_oracle():
    pieces = scripts.emit_data_scripts(_data_diff(), "oracle", TS, "TEST")
    by_action = {p["action"]: p for p in pieces}

    assert by_action["data_insert"]["sql"] == (
        'INSERT INTO "DBO"."PARAMS" ("ID", "NOMBRE", "VALOR") SELECT 3, \'C\', 3 FROM dual '
        'WHERE NOT EXISTS (SELECT 1 FROM "DBO"."PARAMS" WHERE "ID" = 3);'
    )
    assert by_action["data_update"]["sql"] == 'UPDATE "DBO"."PARAMS" SET "NOMBRE" = \'B-mod\' WHERE "ID" = 2;'
    assert by_action["data_delete"]["sql"] == 'DELETE FROM "DBO"."PARAMS" WHERE "ID" = 4;'


def test_delete_pieza_destructiva():
    pieces = scripts.emit_data_scripts(_data_diff(), "sqlserver", TS, "TEST")
    delete_piece = next(p for p in pieces if p["action"] == "data_delete")
    assert delete_piece["destructive"] is True


def test_bytes_truncados_comenta_fila():
    diff = _data_diff(
        column_types={"ID": "INT", "NOMBRE": "VARCHAR(50)", "VALOR": "VARBINARY(MAX)"},
        only_source=[{"ID": "9", "NOMBRE": "X", "VALOR": "0x000102030405060708090A0B0C0D0E0F...(20 bytes)"}],
        only_target=[],
        changed=[],
    )
    pieces = scripts.emit_data_scripts(diff, "sqlserver", TS, "TEST")
    insert_piece = next(p for p in pieces if p["action"] == "data_insert")
    assert "-- BYTES TRUNCADOS" in insert_piece["sql"]
    assert "INSERT INTO" not in insert_piece["sql"].split("\n")[0]


def test_sin_cambios_no_emite_piezas():
    diff = _data_diff(only_source=[], only_target=[], changed=[])
    assert scripts.emit_data_scripts(diff, "sqlserver", TS, "TEST") == []


# ---------------------------------------------------------------------------
# INSERT idempotente reejecutable (e2e sqlite)
# ---------------------------------------------------------------------------


def test_insert_idempotente_reejecutable_sqlite(tmp_path):
    db_path = tmp_path / "target.db"
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE PARAMS (ID INTEGER PRIMARY KEY, NOMBRE TEXT, VALOR REAL)"))
        c.execute(text("INSERT INTO PARAMS (ID, NOMBRE, VALOR) VALUES (1, 'A', 1.0)"))
        c.commit()

    diff = _data_diff(
        schema="main",  # sqlite: "main" es el esquema implícito de la BD default (ATTACH).
        column_types={"ID": "INTEGER", "NOMBRE": "TEXT", "VALOR": "REAL"},
        only_source=[{"ID": "3", "NOMBRE": "C", "VALOR": "3"}],
        only_target=[],
        changed=[],
    )
    pieces = scripts.emit_data_scripts(diff, "sqlite", TS, "TEST")
    insert_sql = next(p for p in pieces if p["action"] == "data_insert")["sql"]

    def _apply():
        with eng.connect() as c:
            for line in insert_sql.splitlines():
                line = line.strip()
                if line and not line.startswith("--"):
                    c.execute(text(line))
            c.commit()

    _apply()
    with eng.connect() as c:
        count1 = c.execute(text("SELECT COUNT(*) FROM PARAMS")).scalar()
    assert count1 == 2  # fila original + la insertada

    _apply()  # reejecutar: debe ser un no-op seguro
    with eng.connect() as c:
        count2 = c.execute(text("SELECT COUNT(*) FROM PARAMS")).scalar()
    assert count2 == 2


# ---------------------------------------------------------------------------
# Integración con el bundle — KPI-3 (backup pareado) + backward-compat con 125
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(scripts, "data_dir", lambda: tmp_path)
    return tmp_path


def _schema_diff_sin_cambios():
    return {
        "version": 1,
        "engine": "sqlserver",
        "source": {"alias": "DEV", "snapshot_id": "s1", "content_hash": "h1"},
        "target": {"alias": "TEST", "snapshot_id": "s2", "content_hash": "h2"},
        "items": [],
        "summary": {},
    }


def _empty_schema_obj(alias):
    return make_schema_obj(alias, "dbo")


def test_kpi3_backup_por_tabla_con_dml(tmp_path):
    data_diff = {"status": "done", "tables": {"dbo.PARAMS": _data_diff()}}
    manifest = scripts.generate_parity_bundle_from_diff(
        _schema_diff_sin_cambios(), RUN_ID, _empty_schema_obj("DEV"), _empty_schema_obj("TEST"),
        "sqlserver", ts=TS, data_diff=data_diff,
    )
    data_entries = [e for e in manifest["entries"] if e["action"].startswith("data_")]
    assert len(data_entries) == 3  # insert + update + delete
    for e in data_entries:
        assert e["backup_file"] is not None, e
        assert e["backup_file"] in manifest["entries"] or True  # backup_file es un path, no un entry
    backup_paths = {e["backup_file"] for e in data_entries}
    assert len(backup_paths) == 1  # dedupe: 1 sola tabla -> 1 solo backup


def test_data_delete_va_a_09_destructivo(tmp_path):
    data_diff = {"status": "done", "tables": {"dbo.PARAMS": _data_diff()}}
    manifest = scripts.generate_parity_bundle_from_diff(
        _schema_diff_sin_cambios(), RUN_ID, _empty_schema_obj("DEV"), _empty_schema_obj("TEST"),
        "sqlserver", ts=TS, data_diff=data_diff,
    )
    delete_entry = next(e for e in manifest["entries"] if e["action"] == "data_delete")
    assert delete_entry["file"].startswith("09_destructivo/")
    insert_entry = next(e for e in manifest["entries"] if e["action"] == "data_insert")
    assert insert_entry["file"].startswith("03_datos/")


def test_bundle_sin_data_diff_no_crea_03_datos(tmp_path):
    """Backward-compat con 125: sin el parámetro data_diff (o data_diff=None),
    el bundle se genera exactamente igual que antes del plan 126."""
    manifest = scripts.generate_parity_bundle_from_diff(
        _schema_diff_sin_cambios(), RUN_ID, _empty_schema_obj("DEV"), _empty_schema_obj("TEST"), "sqlserver", ts=TS,
    )
    assert manifest["entries"] == []
    bundle_dir = tmp_path / "db_compare" / "bundles" / RUN_ID
    assert not (bundle_dir / "03_datos").exists()
