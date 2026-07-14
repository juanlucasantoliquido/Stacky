"""Plan 126 F1 — Normalizacion de valores y literales SQL por dialecto para el
Comparador de BD (paridad de datos, serie 122-126).

Fuente unica de verdad reusada por:
- services/dbcompare_data.py (F2, diff de filas por PK) via normalize_value.
- services/dbcompare_scripts.py (F3, scripts DML de paridad) via sql_literal.

Ver Stacky Agents/docs/126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md #F1.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

_BYTES_PREVIEW_LEN = 16
_TRUNCATED_MARK = "...("

# Clasificación GRUESA del `type` de columna del snapshot (str(col["type"]).upper(),
# ver services/dbcompare_snapshot.py:_reflect_table) para sql_literal_from_normalized.
_NUMERIC_TYPE_RE = re.compile(r"INT|DEC|NUMERIC|FLOAT|REAL|DOUBLE|MONEY|BIT|BOOL")
_DATETIME_TYPE_RE = re.compile(r"DATE|TIME")
_BINARY_TYPE_RE = re.compile(r"BINARY|BLOB|IMAGE|RAW|BYTEA")


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


def sql_literal_from_normalized(normalized: str | None, col_type: str, dialect: str) -> str:
    """Complemento de `sql_literal`: renderiza un literal SQL a partir de un
    valor YA NORMALIZADO por `normalize_value` (siempre str o None) + el tipo
    de columna real del snapshot (`col_type`, p.ej. "INTEGER", "DATETIME2",
    "VARCHAR(50)").

    Necesario porque `sql_literal` despacha por `isinstance(v, ...)` sobre
    valores Python CRUDOS: un valor ya normalizado es siempre `str`, así que
    pasárselo a `sql_literal` directo caería SIEMPRE en la rama de texto
    citado — incorrecto para columnas numéricas o de fecha/hora. Usado por
    F3 (`emit_data_scripts`) para los scripts DML de paridad de datos.
    """
    if normalized is None:
        return "NULL"

    col_type = col_type or ""

    if _BINARY_TYPE_RE.search(col_type):
        if _TRUNCATED_MARK in normalized:
            raise SqlLiteralError(
                f"bytes truncados por normalize_value (>16), no reconstruibles a "
                f"literal completo: {normalized!r}"
            )
        hexpart = normalized[2:] if normalized.startswith("0x") else normalized
        if dialect == "sqlserver":
            return f"0x{hexpart}"
        if dialect == "oracle":
            return f"HEXTORAW('{hexpart}')"
        if dialect == "sqlite":
            return f"X'{hexpart}'"
        raise SqlLiteralError(f"dialecto desconocido: {dialect!r}")

    if _DATETIME_TYPE_RE.search(col_type):
        if " " in normalized:  # datetime: "YYYY-MM-DD HH:MM:SS[.ffffff]"
            date_part, time_part = normalized.split(" ", 1)
            if "." not in time_part:
                time_part += ".000000"
            if dialect == "sqlserver":
                return f"CONVERT(DATETIME2, '{date_part}T{time_part}', 126)"
            if dialect == "oracle":
                return f"TO_TIMESTAMP('{date_part} {time_part}', 'YYYY-MM-DD HH24:MI:SS.FF6')"
            if dialect == "sqlite":
                return f"'{date_part} {time_part.split('.')[0]}'"
            raise SqlLiteralError(f"dialecto desconocido: {dialect!r}")
        # date: "YYYY-MM-DD"
        if dialect == "sqlserver":
            return f"CONVERT(DATE, '{normalized}', 23)"
        if dialect == "oracle":
            return f"TO_DATE('{normalized}','YYYY-MM-DD')"
        if dialect == "sqlite":
            return f"'{normalized}'"
        raise SqlLiteralError(f"dialecto desconocido: {dialect!r}")

    if _NUMERIC_TYPE_RE.search(col_type):
        return normalized  # ya viene canónico (sin comillas) de normalize_value.

    # Texto (y cualquier tipo no reconocido: fallback seguro = string citado).
    return "'" + normalized.replace("'", "''") + "'"
