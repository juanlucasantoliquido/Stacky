"""Plan 182 F1 — Emisor v2: pieza `data_merge` (upsert set-based por dialecto)
+ `data_update` con guard anti-no-op NULL-safe, detrás del kwarg keyword-only
`data_merge_mode` (default False ⇒ byte-idéntico a main / Plan 126).

Ver Stacky Agents/docs/182_PLAN_SCRIPTS_DE_DATOS_V2_MERGE_IDEMPOTENTE_*.md #F1
y la hoja de ruta 184 §2.5 (kwarg `data_merge_mode`, composable con 176).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dbcompare_scripts as scripts  # noqa: E402
from services import dbcompare_sqlvalues as sqlvalues  # noqa: E402

TS = "20260714_120000"


def _dd(**ov):
    base = {
        "version": 1,
        "schema": "dbo",
        "table": "PARAMS",
        "pk_cols": ["ID"],
        "columns": ["ID", "NOMBRE", "VALOR"],
        "column_types": {"ID": "INT", "NOMBRE": "VARCHAR(50)", "VALOR": "INT"},
        "columns_skipped": [],
        "only_source": [
            {"ID": "1", "NOMBRE": "A", "VALOR": "10"},
            {"ID": "3", "NOMBRE": "C", "VALOR": "30"},
        ],
        "only_target": [],
        "changed": [],
        "row_counts": {"source": 2, "target": 0},
        "truncated": False,
        "identical": False,
    }
    base.update(ov)
    return base


def _piece(pieces, action):
    return next(p for p in pieces if p["action"] == action)


def _body(piece):
    """SQL de la pieza sin las líneas de comentario (prefijos §4.6/§4.7 y
    filas con bytes truncados)."""
    return "\n".join(l for l in piece["sql"].splitlines() if not l.startswith("--"))


# ---------------------------------------------------------------------------
# KPI-2 / KPI-3 — goldens por dialecto
# ---------------------------------------------------------------------------

GOLDEN_SQLSERVER = (
    "MERGE INTO [dbo].[PARAMS] AS T\n"
    "USING (VALUES\n"
    "  (1, 'A', 10),\n"
    "  (3, 'C', 30)\n"
    ") AS S ([ID], [NOMBRE], [VALOR])\n"
    "ON (T.[ID] = S.[ID])\n"
    "WHEN MATCHED AND EXISTS (SELECT S.[NOMBRE], S.[VALOR] EXCEPT SELECT T.[NOMBRE], T.[VALOR])\n"
    "  THEN UPDATE SET T.[NOMBRE] = S.[NOMBRE], T.[VALOR] = S.[VALOR]\n"
    "WHEN NOT MATCHED BY TARGET\n"
    "  THEN INSERT ([ID], [NOMBRE], [VALOR]) VALUES (S.[ID], S.[NOMBRE], S.[VALOR]);"
)

GOLDEN_ORACLE = (
    'MERGE INTO "DBO"."PARAMS" T\n'
    "USING (\n"
    '  SELECT 1 AS "ID", \'A\' AS "NOMBRE", 10 AS "VALOR" FROM dual\n'
    "  UNION ALL\n"
    "  SELECT 3, 'C', 30 FROM dual\n"
    ") S\n"
    'ON (T."ID" = S."ID")\n'
    'WHEN MATCHED THEN UPDATE SET T."NOMBRE" = S."NOMBRE", T."VALOR" = S."VALOR"\n'
    '  WHERE DECODE(T."NOMBRE", S."NOMBRE", 1, 0) = 0 OR DECODE(T."VALOR", S."VALOR", 1, 0) = 0\n'
    'WHEN NOT MATCHED THEN INSERT ("ID", "NOMBRE", "VALOR") VALUES (S."ID", S."NOMBRE", S."VALOR");'
)

GOLDEN_SQLITE = (
    'INSERT INTO "main"."PARAMS" ("ID", "NOMBRE", "VALOR") VALUES (1, \'A\', 10) '
    'ON CONFLICT("ID") DO UPDATE SET "NOMBRE" = excluded."NOMBRE", "VALOR" = excluded."VALOR" '
    'WHERE "PARAMS"."NOMBRE" IS NOT excluded."NOMBRE" OR "PARAMS"."VALOR" IS NOT excluded."VALOR";\n'
    'INSERT INTO "main"."PARAMS" ("ID", "NOMBRE", "VALOR") VALUES (3, \'C\', 30) '
    'ON CONFLICT("ID") DO UPDATE SET "NOMBRE" = excluded."NOMBRE", "VALOR" = excluded."VALOR" '
    'WHERE "PARAMS"."NOMBRE" IS NOT excluded."NOMBRE" OR "PARAMS"."VALOR" IS NOT excluded."VALOR";'
)


def test_golden_merge_sqlserver():
    pieces = scripts.emit_data_scripts(_dd(), "sqlserver", TS, "TEST", data_merge_mode=True)
    merge = _piece(pieces, "data_merge")
    assert merge["destructive"] is False
    assert merge["modifies_table"] is True
    assert merge["object_type"] == "table"
    assert _body(merge) == GOLDEN_SQLSERVER
    # ya NO existe la pieza data_insert cuando merge está activo
    assert not any(p["action"] == "data_insert" for p in pieces)


def test_golden_merge_oracle():
    pieces = scripts.emit_data_scripts(_dd(), "oracle", TS, "TEST", data_merge_mode=True)
    assert _body(_piece(pieces, "data_merge")) == GOLDEN_ORACLE


def test_golden_merge_sqlite_una_linea():
    pieces = scripts.emit_data_scripts(_dd(schema="main"), "sqlite", TS, "TEST", data_merge_mode=True)
    merge = _piece(pieces, "data_merge")
    assert _body(merge) == GOLDEN_SQLITE
    # límite C3: cada statement (línea no-comentario) es UNA línea física.
    for line in _body(merge).splitlines():
        assert "\n" not in line
        assert line.startswith("INSERT INTO ") and line.endswith(";")


def test_golden_pk_compuesta():
    dd = _dd(
        pk_cols=["C1", "C2"],
        columns=["C1", "C2", "V"],
        column_types={"C1": "INT", "C2": "INT", "V": "INT"},
        only_source=[{"C1": "1", "C2": "2", "V": "9"}],
    )
    ss = _body(_piece(scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST", data_merge_mode=True), "data_merge"))
    assert "ON (T.[C1] = S.[C1] AND T.[C2] = S.[C2])" in ss
    sq = _body(_piece(scripts.emit_data_scripts(dict(dd, schema="main"), "sqlite", TS, "TEST", data_merge_mode=True), "data_merge"))
    assert 'ON CONFLICT("C1", "C2")' in sq


def test_merge_columna_todo_null_castea():
    dd = _dd(only_source=[
        {"ID": "1", "NOMBRE": "A", "VALOR": None},
        {"ID": "3", "NOMBRE": "C", "VALOR": None},
    ])
    ss = _body(_piece(scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST", data_merge_mode=True), "data_merge"))
    assert "(1, 'A', CAST(NULL AS INT))" in ss  # primera fila: CAST
    assert "(3, 'C', NULL)" in ss  # filas siguientes: NULL pelado
    orc = _body(_piece(scripts.emit_data_scripts(dd, "oracle", TS, "TEST", data_merge_mode=True), "data_merge"))
    assert 'CAST(NULL AS INT) AS "VALOR"' in orc


def test_update_guard_por_dialecto():
    dd = _dd(only_source=[], changed=[{"pk": {"ID": "2"}, "cells": {"NOMBRE": {"source": "B", "target": "B-mod"}}}])
    ss = _body(_piece(scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST", data_merge_mode=True), "data_update"))
    assert ss == "UPDATE [dbo].[PARAMS] SET [NOMBRE] = 'B-mod' WHERE [ID] = 2 AND EXISTS (SELECT 'B-mod' EXCEPT SELECT [NOMBRE]);"
    orc = _body(_piece(scripts.emit_data_scripts(dd, "oracle", TS, "TEST", data_merge_mode=True), "data_update"))
    assert orc == 'UPDATE "DBO"."PARAMS" SET "NOMBRE" = \'B-mod\' WHERE "ID" = 2 AND DECODE("NOMBRE", \'B-mod\', 1, 0) = 0;'
    sq = _body(_piece(scripts.emit_data_scripts(dd, "sqlite", TS, "TEST", data_merge_mode=True), "data_update"))
    assert sq == 'UPDATE "dbo"."PARAMS" SET "NOMBRE" = \'B-mod\' WHERE "ID" = 2 AND "NOMBRE" IS NOT \'B-mod\';'


def test_jamas_by_source_delete():
    dd = _dd(only_target=[{"ID": "4", "NOMBRE": "D", "VALOR": "4"}],
             changed=[{"pk": {"ID": "2"}, "cells": {"NOMBRE": {"source": "B", "target": "B-mod"}}}])
    for dialect in ("sqlserver", "oracle", "sqlite"):
        schema = "main" if dialect == "sqlite" else "dbo"
        on = scripts.emit_data_scripts(dict(dd, schema=schema), dialect, TS, "TEST", data_merge_mode=True)
        off = scripts.emit_data_scripts(dict(dd, schema=schema), dialect, TS, "TEST", data_merge_mode=False)
        for p in on:
            assert "NOT MATCHED BY SOURCE" not in p["sql"]
        # el statement DELETE es EXACTAMENTE el de main (§4.5): idéntico salvo el
        # comentario §4.7 de re-ejecutabilidad que ON antepone a toda pieza data_*.
        assert _body(_piece(on, "data_delete")) == _body(_piece(off, "data_delete"))
        assert _body(_piece(off, "data_delete")).startswith("DELETE FROM ")


def test_default_false_byte_identico():
    dd = _dd(changed=[{"pk": {"ID": "2"}, "cells": {"NOMBRE": {"source": "B", "target": "B-mod"}}}],
             only_target=[{"ID": "4", "NOMBRE": "D", "VALOR": "4"}])
    default = scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST")
    explicit = scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST", data_merge_mode=False)
    assert default == explicit
    # con OFF sale data_insert (v1), nunca data_merge
    assert any(p["action"] == "data_insert" for p in default)
    assert not any(p["action"] == "data_merge" for p in default)


def test_tabla_solo_pk_sin_when_matched():
    dd = _dd(pk_cols=["ID"], columns=["ID"], column_types={"ID": "INT"},
             only_source=[{"ID": "1"}, {"ID": "3"}])
    ss = _body(_piece(scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST", data_merge_mode=True), "data_merge"))
    assert "WHEN MATCHED" not in ss
    assert ss.endswith("THEN INSERT ([ID]) VALUES (S.[ID]);")
    orc = _body(_piece(scripts.emit_data_scripts(dd, "oracle", TS, "TEST", data_merge_mode=True), "data_merge"))
    assert "WHEN MATCHED" not in orc
    sq = _body(_piece(scripts.emit_data_scripts(dict(dd, schema="main"), "sqlite", TS, "TEST", data_merge_mode=True), "data_merge"))
    assert "DO NOTHING;" in sq
    assert "DO UPDATE" not in sq


def test_only_source_vacio_sin_pieza_merge():
    dd = _dd(only_source=[], changed=[{"pk": {"ID": "2"}, "cells": {"NOMBRE": {"source": "B", "target": "B-mod"}}}])
    pieces = scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST", data_merge_mode=True)
    assert not any(p["action"] == "data_merge" for p in pieces)
    assert any(p["action"] == "data_update" for p in pieces)


def test_bytes_truncados_fila_fuera_del_values():
    dd = _dd(
        columns=["ID", "DATA"],
        pk_cols=["ID"],
        column_types={"ID": "INT", "DATA": "VARBINARY(MAX)"},
        only_source=[
            {"ID": "1", "DATA": "0x01"},
            {"ID": "9", "DATA": "0x000102030405060708090A0B0C0D0E0F...(20 bytes)"},
        ],
    )
    merge = _piece(scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST", data_merge_mode=True), "data_merge")
    assert "-- BYTES TRUNCADOS" in merge["sql"]
    # la fila buena entra al VALUES; la truncada NO
    assert "(1, 0x01)" in merge["sql"]
    assert "(9," not in merge["sql"]


def test_truncated_prefija_advertencia():
    on_trunc = scripts.emit_data_scripts(_dd(truncated=True), "sqlserver", TS, "TEST", data_merge_mode=True)
    merge = _piece(on_trunc, "data_merge")
    assert merge["sql"].splitlines()[0] == scripts._DATA_TRUNCATION_WARNING
    on_full = scripts.emit_data_scripts(_dd(truncated=False), "sqlserver", TS, "TEST", data_merge_mode=True)
    assert scripts._DATA_TRUNCATION_WARNING not in _piece(on_full, "data_merge")["sql"]


def test_advertencia_reejecutabilidad():
    dd = _dd(changed=[{"pk": {"ID": "2"}, "cells": {"NOMBRE": {"source": "B", "target": "B-mod"}}}],
             only_target=[{"ID": "4", "NOMBRE": "D", "VALOR": "4"}])
    on = scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST", data_merge_mode=True)
    for p in on:
        assert scripts._DATA_REEXEC_NOTICE in p["sql"], p["action"]
    off = scripts.emit_data_scripts(dd, "sqlserver", TS, "TEST", data_merge_mode=False)
    for p in off:
        assert scripts._DATA_REEXEC_NOTICE not in p["sql"]
