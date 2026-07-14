"""Tests F2 (Plan 125) — emitters SQL Server: golden caracter a caracter (KPI-2)."""
from __future__ import annotations

import pytest

from services import dbcompare_scripts as scripts
from tests._plan125_fixtures import make_col, make_schema_obj, make_table, make_view

DIALECT = "sqlserver"
TS = "20260714_120000"


def _item(kind, schema="dbo", name="CLIENTES", object_type="table", detail=None):
    return {"kind": kind, "object_type": object_type, "schema": schema, "name": name, "detail": detail or {}}


def _empty_schema_obj():
    return make_schema_obj("DEV", "dbo")


def test_table_added_con_pk_index_y_fk():
    source = make_schema_obj(
        "DEV",
        "dbo",
        tables={
            "CLIENTES": make_table(
                columns=[
                    make_col("ID", "INT", nullable=False),
                    make_col("NOMBRE", "VARCHAR(50)", nullable=True),
                ],
                pk_columns=["ID"],
                pk_name="PK_CLIENTES",
                foreign_keys=[
                    {
                        "name": "FK_CLIENTES_PAIS",
                        "columns": ["PAIS_ID"],
                        "referred_schema": "dbo",
                        "referred_table": "PAISES",
                        "referred_columns": ["ID"],
                    }
                ],
                indexes=[{"name": "IX_NOMBRE", "columns": ["NOMBRE"], "unique": False}],
            )
        },
    )
    item = _item("table_added")

    pieces = scripts.emit_parity(item, source, _empty_schema_obj(), DIALECT, TS)

    assert len(pieces) == 3
    create_piece, index_piece, fk_piece = pieces
    assert create_piece["sql"] == (
        "CREATE TABLE [dbo].[CLIENTES] (\n"
        "    [ID] INT NOT NULL,\n"
        "    [NOMBRE] VARCHAR(50) NULL,\n"
        "    CONSTRAINT [PK_CLIENTES] PRIMARY KEY ([ID])\n"
        ");"
    )
    assert create_piece["destructive"] is False
    assert create_piece["modifies_table"] is False
    assert index_piece["sql"] == "CREATE INDEX [IX_NOMBRE] ON [dbo].[CLIENTES] ([NOMBRE]);"
    assert fk_piece["sql"] == (
        "ALTER TABLE [dbo].[CLIENTES] ADD CONSTRAINT [FK_CLIENTES_PAIS] "
        "FOREIGN KEY ([PAIS_ID]) REFERENCES [dbo].[PAISES] ([ID]);"
    )


def test_table_removed():
    item = _item("table_removed")
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert len(pieces) == 1
    assert pieces[0]["sql"] == "DROP TABLE [dbo].[CLIENTES];"
    assert pieces[0]["destructive"] is True
    assert pieces[0]["modifies_table"] is True


def test_column_added_con_default():
    detail = {"column": "EMAIL", "source": make_col("EMAIL", "VARCHAR(100)", nullable=True)}
    item = _item("column_added", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "ALTER TABLE [dbo].[CLIENTES] ADD [EMAIL] VARCHAR(100) NULL;"
    assert pieces[0]["destructive"] is False
    assert pieces[0]["modifies_table"] is True


def test_column_added_notnull_sin_default_comenta():
    detail = {"column": "DNI", "source": make_col("DNI", "INT", nullable=False, default=None)}
    item = _item("column_added", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == (
        "ALTER TABLE [dbo].[CLIENTES] ADD [DNI] INT NULL;\n"
        "-- AJUSTAR: en el origen esta columna es NOT NULL sin default; "
        "completá los datos y endurecé después."
    )


def test_column_removed():
    item = _item("column_removed", detail={"column": "OBSOLETA"})
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "ALTER TABLE [dbo].[CLIENTES] DROP COLUMN [OBSOLETA];"
    assert pieces[0]["destructive"] is True
    assert pieces[0]["modifies_table"] is True


def test_column_type_changed():
    detail = {
        "column": "MONTO",
        "source": make_col("MONTO", "DECIMAL(18,2)", nullable=False),
        "target": make_col("MONTO", "DECIMAL(10,2)", nullable=False),
    }
    item = _item("column_type_changed", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "ALTER TABLE [dbo].[CLIENTES] ALTER COLUMN [MONTO] DECIMAL(18,2) NOT NULL;"
    assert pieces[0]["destructive"] is True


@pytest.mark.parametrize("kind,expected_destructive", [("column_nullable_relaxed", False), ("column_nullable_tightened", True)])
def test_column_nullable(kind, expected_destructive):
    detail = {
        "column": "APELLIDO",
        "source": make_col("APELLIDO", "VARCHAR(80)", nullable=(kind == "column_nullable_relaxed")),
        "target": make_col("APELLIDO", "VARCHAR(80)", nullable=(kind != "column_nullable_relaxed")),
    }
    item = _item(kind, detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    nullability = "NULL" if kind == "column_nullable_relaxed" else "NOT NULL"
    assert pieces[0]["sql"] == f"ALTER TABLE [dbo].[CLIENTES] ALTER COLUMN [APELLIDO] VARCHAR(80) {nullability};"
    assert pieces[0]["destructive"] is expected_destructive


def test_column_default_changed_bloque_literal():
    detail = {
        "column": "ESTADO",
        "source": make_col("ESTADO", "INT", default="1"),
        "target": make_col("ESTADO", "INT", default="0"),
    }
    item = _item("column_default_changed", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == (
        "DECLARE @df sysname;\n"
        "SELECT @df = dc.name FROM sys.default_constraints dc\n"
        "JOIN sys.columns c ON c.default_object_id = dc.object_id\n"
        "WHERE dc.parent_object_id = OBJECT_ID(N'dbo.CLIENTES') AND c.name = N'ESTADO';\n"
        "IF @df IS NOT NULL EXEC(N'ALTER TABLE [dbo].[CLIENTES] DROP CONSTRAINT [' + @df + N']');\n"
        "ALTER TABLE [dbo].[CLIENTES] ADD CONSTRAINT [DF_CLIENTES_ESTADO] DEFAULT 1 FOR [ESTADO];"
    )
    assert pieces[0]["destructive"] is False
    assert pieces[0]["modifies_table"] is True


def test_pk_changed():
    detail = {
        "source": {"name": "PK_CLIENTES", "columns": ["ID", "SUCURSAL_ID"]},
        "target": {"name": "PK_CLIENTES_OLD", "columns": ["ID"]},
    }
    item = _item("pk_changed", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == (
        "ALTER TABLE [dbo].[CLIENTES] DROP CONSTRAINT [PK_CLIENTES_OLD];\n"
        "ALTER TABLE [dbo].[CLIENTES] ADD CONSTRAINT [PK_CLIENTES] PRIMARY KEY ([ID], [SUCURSAL_ID]);"
    )
    assert pieces[0]["destructive"] is True


def test_fk_added():
    detail = {
        "name": "FK_CLIENTES_PAIS",
        "columns": ["PAIS_ID"],
        "referred_schema": "dbo",
        "referred_table": "PAISES",
        "referred_columns": ["ID"],
    }
    item = _item("fk_added", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == (
        "ALTER TABLE [dbo].[CLIENTES] ADD CONSTRAINT [FK_CLIENTES_PAIS] "
        "FOREIGN KEY ([PAIS_ID]) REFERENCES [dbo].[PAISES] ([ID]);"
    )
    assert pieces[0]["destructive"] is False


def test_unique_added():
    detail = {"name": "UQ_CLIENTES_DOC", "columns": ["DOCUMENTO"]}
    item = _item("unique_added", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "ALTER TABLE [dbo].[CLIENTES] ADD CONSTRAINT [UQ_CLIENTES_DOC] UNIQUE ([DOCUMENTO]);"


def test_check_added():
    detail = {"name": "CK_CLIENTES_EDAD", "sqltext": "EDAD >= 0"}
    item = _item("check_added", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "ALTER TABLE [dbo].[CLIENTES] ADD CONSTRAINT [CK_CLIENTES_EDAD] CHECK (EDAD >= 0);"


@pytest.mark.parametrize(
    "kind,constraint_name,expected_destructive",
    [
        ("fk_removed", "FK_CLIENTES_PAIS", False),
        ("check_removed", "CK_CLIENTES_EDAD", False),
        ("unique_removed", "UQ_CLIENTES_DOC", True),
    ],
)
def test_drop_constraint_kinds(kind, constraint_name, expected_destructive):
    item = _item(kind, detail={"name": constraint_name})
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == f"ALTER TABLE [dbo].[CLIENTES] DROP CONSTRAINT [{constraint_name}];"
    assert pieces[0]["destructive"] is expected_destructive


def test_index_added():
    detail = {"name": "IX_CLIENTES_DOC", "columns": ["DOCUMENTO"], "unique": False}
    item = _item("index_added", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "CREATE INDEX [IX_CLIENTES_DOC] ON [dbo].[CLIENTES] ([DOCUMENTO]);"
    assert pieces[0]["destructive"] is False
    assert pieces[0]["modifies_table"] is False


def test_index_added_unique():
    detail = {"name": "UX_CLIENTES_DOC", "columns": ["DOCUMENTO"], "unique": True}
    item = _item("index_added", detail=detail)
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "CREATE UNIQUE INDEX [UX_CLIENTES_DOC] ON [dbo].[CLIENTES] ([DOCUMENTO]);"


def test_index_removed():
    item = _item("index_removed", detail={"name": "IX_CLIENTES_DOC"})
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "DROP INDEX [IX_CLIENTES_DOC] ON [dbo].[CLIENTES];"
    assert pieces[0]["destructive"] is False
    assert pieces[0]["modifies_table"] is True


def test_view_added():
    source = make_schema_obj("DEV", "dbo", views={"V_CLIENTES": make_view(definition="SELECT * FROM CLIENTES")})
    item = _item("view_added", name="V_CLIENTES", object_type="view")
    pieces = scripts.emit_parity(item, source, _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "CREATE OR ALTER VIEW [dbo].[V_CLIENTES] AS\nSELECT * FROM CLIENTES"
    assert pieces[0]["destructive"] is False
    assert pieces[0]["modifies_table"] is False


def test_view_sin_definicion_todo_comentado():
    source = make_schema_obj("DEV", "dbo", views={"V_CLIENTES": make_view(definition=None)})
    item = _item("view_added", name="V_CLIENTES", object_type="view")
    pieces = scripts.emit_parity(item, source, _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == (
        "-- DEFINICIÓN NO CAPTURADA EN SNAPSHOT; completar a mano\n"
        "-- CREATE OR ALTER VIEW [dbo].[V_CLIENTES] AS ..."
    )


def test_view_removed():
    item = _item("view_removed", name="V_VIEJA", object_type="view")
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "DROP VIEW [dbo].[V_VIEJA];"


def test_sequence_added():
    item = _item("sequence_added", name="SEQ_CLIENTES", object_type="sequence")
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "CREATE SEQUENCE [dbo].[SEQ_CLIENTES] START WITH 1; -- START WITH no capturado en snapshot v1"


def test_sequence_removed():
    item = _item("sequence_removed", name="SEQ_VIEJA", object_type="sequence")
    pieces = scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    assert pieces[0]["sql"] == "DROP SEQUENCE [dbo].[SEQ_VIEJA];"


def test_kind_desconocido_lanza():
    item = _item("fk_changed")
    with pytest.raises(ValueError):
        scripts.emit_parity(item, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)


# ---------------------------------------------------------------------------
# emit_resguardo
# ---------------------------------------------------------------------------


def test_backup_incluye_verificacion_counts():
    piece = {
        "action": "table_removed",
        "object_type": "table",
        "schema": "dbo",
        "name": "CLIENTES",
        "sql": "DROP TABLE [dbo].[CLIENTES];",
        "destructive": True,
        "modifies_table": True,
    }
    resguardos = scripts.emit_resguardo(piece, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    backup = next(r for r in resguardos if r["action"] == "table_backup")
    assert "SELECT * INTO [dbo].[CLIENTES_BAK_20260714_120000] FROM [dbo].[CLIENTES];" in backup["sql"]
    assert "THROW 50001" in backup["sql"]
    assert "BACKUP INCOMPLETO" in backup["sql"]


def test_backup_dedupe_por_tabla():
    piece_a = {
        "action": "column_removed", "object_type": "table", "schema": "dbo", "name": "CLIENTES",
        "sql": "x", "destructive": True, "modifies_table": True,
    }
    piece_b = {
        "action": "pk_changed", "object_type": "table", "schema": "dbo", "name": "CLIENTES",
        "sql": "y", "destructive": True, "modifies_table": True,
    }
    collected = scripts.collect_resguardos([piece_a, piece_b], _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS)
    backups = [r for r in collected if r["action"] == "table_backup"]
    assert len(backups) == 1


def test_rollback_table_removed_reconstruye_desde_target():
    target = make_schema_obj(
        "TEST",
        "dbo",
        tables={"VIEJA": make_table(columns=[make_col("ID", "INT", nullable=False)], pk_columns=["ID"], pk_name="PK_VIEJA")},
    )
    piece = {
        "action": "table_removed", "object_type": "table", "schema": "dbo", "name": "VIEJA",
        "sql": "DROP TABLE [dbo].[VIEJA];", "destructive": True, "modifies_table": True,
        "_detail": {},
    }
    resguardos = scripts.emit_resguardo(piece, _empty_schema_obj(), target, DIALECT, TS)
    rollback = next(r for r in resguardos if r["action"].startswith("rollback_"))
    assert "CREATE TABLE [dbo].[VIEJA] (" in rollback["sql"]
    assert "Los DATOS se restauran desde la tabla de backup pareada." in rollback["sql"]


def test_rollback_index_removed_reconstruye_desde_target():
    target = make_schema_obj(
        "TEST",
        "dbo",
        tables={"CLIENTES": make_table(columns=[], indexes=[{"name": "IX_DOC", "columns": ["DOCUMENTO"], "unique": False}])},
    )
    piece = {
        "action": "index_removed", "object_type": "table", "schema": "dbo", "name": "CLIENTES",
        "sql": "x", "destructive": False, "modifies_table": True,
        "_detail": {"name": "IX_DOC"},
    }
    resguardos = scripts.emit_resguardo(piece, _empty_schema_obj(), target, DIALECT, TS)
    rollback = next(r for r in resguardos if r["action"].startswith("rollback_"))
    assert rollback["sql"].endswith("CREATE INDEX [IX_DOC] ON [dbo].[CLIENTES] ([DOCUMENTO]);")


def test_additive_piezas_sin_resguardo():
    piece = {
        "action": "table_added", "object_type": "table", "schema": "dbo", "name": "NUEVA",
        "sql": "x", "destructive": False, "modifies_table": False,
    }
    assert scripts.emit_resguardo(piece, _empty_schema_obj(), _empty_schema_obj(), DIALECT, TS) == []
