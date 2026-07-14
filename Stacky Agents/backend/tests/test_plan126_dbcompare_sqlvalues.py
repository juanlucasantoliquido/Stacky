"""Plan 126 F1 — Tests PRIMERO de services/dbcompare_sqlvalues.py.

Golden tests literales por regla (ver Stacky Agents/docs/
126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md #F1). normalize_value
normaliza valores para comparar filas sin falsos positivos; sql_literal
renderiza literales SQL por dialecto para los scripts DML del F3.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.dbcompare_sqlvalues import SqlLiteralError, normalize_value, sql_literal  # noqa: E402


# ---------------------------------------------------------------------------
# normalize_value
# ---------------------------------------------------------------------------


def test_normalize_none():
    assert normalize_value(None) is None


def test_normalize_bool():
    assert normalize_value(True) == "1"
    assert normalize_value(False) == "0"


def test_normalize_int():
    assert normalize_value(42) == "42"
    assert normalize_value(-7) == "-7"


def test_normalize_float_strips_trailing_zeros():
    assert normalize_value(2.0) == "2"
    assert normalize_value(1.5) == "1.5"


def test_normalize_decimal_strips_trailing_zeros():
    assert normalize_value(Decimal("1.500")) == "1.5"
    assert normalize_value(Decimal("2.0")) == "2"
    assert normalize_value(Decimal("3")) == "3"


def test_normalize_datetime_space_not_t():
    dt = datetime(2024, 1, 15, 10, 30, 45, 123456)
    assert normalize_value(dt) == "2024-01-15 10:30:45.123456"


def test_normalize_date():
    assert normalize_value(date(2024, 1, 15)) == "2024-01-15"


def test_normalize_bytes_short_no_suffix():
    assert normalize_value(bytes(range(16))) == "0x000102030405060708090A0B0C0D0E0F"


def test_normalize_bytes_largos_trunca_con_sufijo():
    b20 = bytes(range(20))
    assert normalize_value(b20) == "0x000102030405060708090A0B0C0D0E0F...(20 bytes)"


def test_normalize_str_sin_trim():
    assert normalize_value("  hola  ") == "  hola  "


def test_normalize_otro_fallback_str():
    class Weird:
        def __str__(self):
            return "weird!"

    assert normalize_value(Weird()) == "weird!"


# ---------------------------------------------------------------------------
# sql_literal
# ---------------------------------------------------------------------------


def test_sql_literal_none_todos_los_dialectos():
    assert sql_literal(None, "sqlserver") == "NULL"
    assert sql_literal(None, "oracle") == "NULL"
    assert sql_literal(None, "sqlite") == "NULL"


def test_sql_literal_bool():
    assert sql_literal(True, "sqlserver") == "1"
    assert sql_literal(False, "oracle") == "0"


def test_sql_literal_int_float_decimal_sin_comillas():
    assert sql_literal(42, "sqlserver") == "42"
    assert sql_literal(2.0, "oracle") == "2"
    assert sql_literal(Decimal("1.500"), "sqlite") == "1.5"


def test_sql_literal_str_comilla_doblada():
    assert sql_literal("O'Brien", "sqlserver") == "'O''Brien'"


def test_sql_literal_str_null_char_oracle_error_explicito():
    with pytest.raises(SqlLiteralError):
        sql_literal("mal\x00o", "oracle")


def test_sql_literal_str_null_char_permitido_fuera_de_oracle():
    assert sql_literal("a\x00b", "sqlserver") == "'a\x00b'"


def test_sql_literal_datetime_golden_por_dialecto():
    dt = datetime(2024, 1, 15, 10, 30, 45, 123456)
    assert sql_literal(dt, "sqlserver") == "CONVERT(DATETIME2, '2024-01-15T10:30:45.123456', 126)"
    assert sql_literal(dt, "oracle") == "TO_TIMESTAMP('2024-01-15 10:30:45.123456', 'YYYY-MM-DD HH24:MI:SS.FF6')"
    assert sql_literal(dt, "sqlite") == "'2024-01-15 10:30:45'"


def test_sql_literal_datetime_microsegundos_cero_completa_ceros():
    dt = datetime(2024, 1, 15, 0, 0, 0)
    assert sql_literal(dt, "sqlserver") == "CONVERT(DATETIME2, '2024-01-15T00:00:00.000000', 126)"


def test_sql_literal_date_golden_por_dialecto():
    d = date(2024, 1, 15)
    assert sql_literal(d, "sqlserver") == "CONVERT(DATE, '2024-01-15', 23)"
    assert sql_literal(d, "oracle") == "TO_DATE('2024-01-15','YYYY-MM-DD')"
    assert sql_literal(d, "sqlite") == "'2024-01-15'"


def test_sql_literal_bytes_golden_por_dialecto_sin_truncar():
    b20 = bytes(range(20))
    hex_full = b20.hex().upper()
    assert sql_literal(b20, "sqlserver") == f"0x{hex_full}"
    assert sql_literal(b20, "oracle") == f"HEXTORAW('{hex_full}')"
    assert sql_literal(b20, "sqlite") == f"X'{hex_full}'"
