"""Tests F1 (Plan 125): helpers de identificadores y nombres de backup."""
from __future__ import annotations

from services import dbcompare_sqlnames as sqlnames


def test_quote_sqlserver_escapa_corchete():
    assert sqlnames.quote_ident("ab]c", "sqlserver") == "[ab]]c]"


def test_quote_oracle_upper_y_comillas():
    assert sqlnames.quote_ident('a"b', "oracle") == '"A""B"'


def test_quote_sqlite_no_upper():
    assert sqlnames.quote_ident('a"b', "sqlite") == '"a""b"'


def test_qualified_concatena_schema_y_nombre():
    assert sqlnames.qualified("dbo", "CLIENTES", "sqlserver") == "[dbo].[CLIENTES]"
    assert sqlnames.qualified("HR", "employees", "oracle") == '"HR"."EMPLOYEES"'


def test_backup_name_corto_golden():
    got = sqlnames.backup_table_name("CLIENTES", "20260712_140000", 128)
    assert got == "CLIENTES_BAK_20260712_140000"


def test_backup_name_truncado_golden():
    table = "CLIENTES_HISTORICO_TRANSACCIONES_DETALLE"
    assert len(table) == 40
    got = sqlnames.backup_table_name(table, "20260712_140000", 30)
    assert got == "CLIENTES_HISTORI_BAK62470A0712"
    assert len(got) <= 30


def test_backup_name_determinista():
    table = "CLIENTES_HISTORICO_TRANSACCIONES_DETALLE"
    a = sqlnames.backup_table_name(table, "20260712_140000", 30)
    b = sqlnames.backup_table_name(table, "20260712_140000", 30)
    assert a == b


def test_script_filename_slug():
    got = sqlnames.script_filename(201, "column_added", "dbo", "CLIENTES")
    assert got == "201_column_added_dbo_CLIENTES.sql"


def test_script_filename_slug_caracteres_no_permitidos():
    got = sqlnames.script_filename(1, "table_backup", "dbo", "IX/CLIENTES DOC")
    assert got == "001_table_backup_dbo_IX_CLIENTES_DOC.sql"
