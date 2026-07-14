"""Plan 126 F1 — Normalizacion de valores y literales SQL por dialecto para el
Comparador de BD (paridad de datos, serie 122-126).

Fuente unica de verdad reusada por:
- services/dbcompare_data.py (F2, diff de filas por PK) via normalize_value.
- services/dbcompare_scripts.py (F3, scripts DML de paridad) via sql_literal.

Ver Stacky Agents/docs/126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md #F1.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

_BYTES_PREVIEW_LEN = 16


class SqlLiteralError(ValueError):
    """Un valor no puede renderizarse como literal SQL valido para el dialecto pedido."""


def _format_number(v: float | Decimal) -> str:
    """Repr canonico de un float/Decimal: format(v, "f") con strip de ceros a
    la derecha y del "." final ("1.500"->"1.5", "2.0"->"2")."""
    s = format(v, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def normalize_value(v: Any) -> str | None:
    """Representacion canonica de v para comparar filas sin falsos positivos
    por representacion (ver Plan 126 F1: reglas EXACTAS por tipo)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (float, Decimal)):
        return _format_number(v)
    if isinstance(v, datetime):
        return v.isoformat().replace("T", " ")
    if isinstance(v, (date, time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        raw = bytes(v)
        hex_preview = raw[:_BYTES_PREVIEW_LEN].hex().upper()
        if len(raw) > _BYTES_PREVIEW_LEN:
            return f"0x{hex_preview}...({len(raw)} bytes)"
        return f"0x{hex_preview}"
    if isinstance(v, str):
        return v
    return str(v)


def sql_literal(v: Any, dialect: str) -> str:
    """Literal SQL de v para `dialect` ("sqlserver" | "oracle" | "sqlite").

    Los scripts DML del F3 son ARTEFACTOS (nunca se ejecutan desde Stacky);
    esta funcion nunca ejecuta SQL, solo renderiza texto.
    """
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (float, Decimal)):
        return _format_number(v)
    if isinstance(v, str):
        if dialect == "oracle" and "\x00" in v:
            raise SqlLiteralError(
                f"el valor contiene chr(0) (NUL); Oracle no admite NUL en "
                f"literales de texto: {v!r}"
            )
        return "'" + v.replace("'", "''") + "'"
    if isinstance(v, datetime):
        if dialect == "sqlserver":
            return f"CONVERT(DATETIME2, '{v.strftime('%Y-%m-%dT%H:%M:%S.%f')}', 126)"
        if dialect == "oracle":
            return (
                f"TO_TIMESTAMP('{v.strftime('%Y-%m-%d %H:%M:%S.%f')}', "
                f"'YYYY-MM-DD HH24:MI:SS.FF6')"
            )
        if dialect == "sqlite":
            return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
        raise SqlLiteralError(f"dialecto desconocido: {dialect!r}")
    if isinstance(v, date):
        iso = v.isoformat()
        if dialect == "sqlserver":
            return f"CONVERT(DATE, '{iso}', 23)"
        if dialect == "oracle":
            return f"TO_DATE('{iso}','YYYY-MM-DD')"
        if dialect == "sqlite":
            return f"'{iso}'"
        raise SqlLiteralError(f"dialecto desconocido: {dialect!r}")
    if isinstance(v, (bytes, bytearray)):
        hex_full = bytes(v).hex().upper()
        if dialect == "sqlserver":
            return f"0x{hex_full}"
        if dialect == "oracle":
            return f"HEXTORAW('{hex_full}')"
        if dialect == "sqlite":
            return f"X'{hex_full}'"
        raise SqlLiteralError(f"dialecto desconocido: {dialect!r}")
    return str(v)
