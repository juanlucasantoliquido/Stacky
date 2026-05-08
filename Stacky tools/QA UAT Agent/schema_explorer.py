"""
schema_explorer.py — Descubrimiento y caché del esquema de base de datos RSPACIFICO.

PROBLEMA RESUELTO
-----------------
`data_resolver.py` tenía FIELD_HINTS estáticos con nombres de columna INCORRECTOS
(ej: `IDLOTE` en vez de `LOCOD`, `CLRIESGOSIS` en vez de `CLRIESGOENT`).
Esto causaba que las queries SQL fallaran silenciosamente y el pipeline reportara
datos como "unresolved" cuando en realidad existían en BD.

SOLUCIÓN
--------
Descubrir el esquema real via `INFORMATION_SCHEMA.COLUMNS` (SELECT-only),
cachearlo en `cache/db_schema.json`, y exponer una API de consulta para que
`precondition_parser.py` y `sql_builder.py` construyan queries con nombres reales.

ARQUITECTURA
------------
  schema_explorer.py
    └─ get_schema()            → dict con todas las tablas/columnas del cache
    └─ get_tables()            → list[str] de tablas disponibles
    └─ get_columns(table)      → list[str] de columnas de esa tabla
    └─ find_column(pattern)    → list[(table, column)] — búsqueda fuzzy
    └─ refresh(connection)     → actualiza cache desde BD
    └─ get_tables_for_guard()  → frozenset para sql_query_guard

CACHE
-----
  cache/db_schema.json:
    {
      "refreshed_at": "2026-05-08T...",
      "tables": {
        "RLOTE": ["LOCOD", "LODESCRIP", "LOESTADO", ...],
        "ROBLG": ["OGLOTE", "OGCORREDOR", "OGCODCLI", ...],
        "RCLIE": ["CLCOD", "CLRIESGOENT", "CLNOMBRE", ...],
        ...
      }
    }

VARIABLES DE ENTORNO
--------------------
  RS_QA_DB_USER   — DB username (default: RSPACIFICOREAD)
  RS_QA_DB_PASS   — DB password
  RS_QA_DB_SERVER — DB server hostname (default: aisbddev02.cloud.ais-int.net)
  RS_QA_DB_NAME   — DB name (default: RSPACIFICO)

NOTAS DE SEGURIDAD
------------------
- Solo usa INFORMATION_SCHEMA.COLUMNS (SELECT, read-only, no DML).
- Credenciales SOLO desde env vars, nunca hardcodeadas.
- El cache es local en disco — no contiene datos de clientes, solo metadata.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.schema_explorer")

_TOOL_VERSION = "1.0.0"

# ── Configuración ──────────────────────────────────────────────────────────────

_CACHE_PATH = Path(__file__).resolve().parent / "cache" / "db_schema.json"
_CACHE_TTL_HOURS = 24  # re-descubrir si el cache tiene más de 24h

_DB_SERVER_DEFAULT = "aisbddev02.cloud.ais-int.net"
_DB_USER_DEFAULT   = "RSPACIFICOREAD"
_DB_NAME_DEFAULT   = "RSPACIFICO"

# Tablas a excluir del schema explorer (tablas de sistema/auditoria)
_EXCLUDED_TABLE_PREFIXES = ("sys", "MS_", "dt_")

# SQL para descubrir columnas de todas las tablas del usuario
_SCHEMA_QUERY = """
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_CATALOG = DB_NAME()
  AND TABLE_SCHEMA = 'dbo'
ORDER BY TABLE_NAME, ORDINAL_POSITION
"""

# Prefijo de tablas RSPACIFICO (R + 4+ chars)
# Filtro heurístico para quedarse solo con tablas del dominio
_DOMAIN_TABLE_RE = None  # None = sin filtro, acepta todas

# ── API pública ───────────────────────────────────────────────────────────────

# Schema cargado en memoria (lazy)
_SCHEMA_CACHE: Optional[dict] = None


def get_schema(
    force_refresh: bool = False,
    connection=None,
) -> dict:
    """
    Retorna el esquema cacheado. Dict con:
      {
        "refreshed_at": ISO str,
        "tables": { "TABLA": ["COL1", "COL2", ...], ... }
      }

    Si el cache no existe o tiene más de TTL horas, intenta refrescar.
    Si no hay conexión disponible, retorna el cache viejo (o schema vacío).
    """
    global _SCHEMA_CACHE

    # 1. Usar cache en memoria si disponible y no se fuerza refresh
    if _SCHEMA_CACHE is not None and not force_refresh:
        return _SCHEMA_CACHE

    # 2. Leer cache de disco si existe y no expiró
    if not force_refresh and _CACHE_PATH.exists():
        try:
            raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if _is_cache_fresh(raw):
                _SCHEMA_CACHE = raw
                logger.debug("schema_explorer: loaded from disk cache (%d tables)", len(raw.get("tables", {})))
                return _SCHEMA_CACHE
            else:
                logger.info("schema_explorer: cache expired — will refresh")
        except Exception as exc:
            logger.warning("schema_explorer: could not read cache: %s", exc)

    # 3. Intentar refresh desde BD si hay conexión
    if connection is not None:
        try:
            refreshed = _refresh_from_db(connection)
            _SCHEMA_CACHE = refreshed
            _write_cache(refreshed)
            return _SCHEMA_CACHE
        except Exception as exc:
            logger.warning("schema_explorer: refresh failed: %s — using stale/empty schema", exc)

    # 4. Intentar conectar con env vars
    if os.environ.get("RS_QA_DB_PASS"):
        try:
            conn = _connect()
            refreshed = _refresh_from_db(conn)
            conn.close()
            _SCHEMA_CACHE = refreshed
            _write_cache(refreshed)
            return _SCHEMA_CACHE
        except Exception as exc:
            logger.warning("schema_explorer: auto-connect failed: %s", exc)

    # 5. Retornar cache viejo si existe (aunque esté expirado), o schema vacío
    if _CACHE_PATH.exists():
        try:
            raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            _SCHEMA_CACHE = raw
            logger.warning(
                "schema_explorer: using stale cache (%s) — no DB connection available",
                raw.get("refreshed_at", "unknown"),
            )
            return _SCHEMA_CACHE
        except Exception:
            pass

    logger.warning("schema_explorer: no schema available — using empty schema")
    empty: dict = {"refreshed_at": None, "tables": {}}
    _SCHEMA_CACHE = empty
    return empty


def get_tables(connection=None) -> list[str]:
    """Retorna lista de nombres de tablas conocidas."""
    schema = get_schema(connection=connection)
    return sorted(schema.get("tables", {}).keys())


def get_columns(table: str, connection=None) -> list[str]:
    """Retorna lista de columnas de una tabla. Vacío si la tabla no existe."""
    schema = get_schema(connection=connection)
    return list(schema.get("tables", {}).get(table.upper(), []))


def find_column(
    pattern: str,
    connection=None,
    max_results: int = 20,
) -> list[tuple[str, str]]:
    """
    Busca columnas cuyos nombres contengan `pattern` (case-insensitive).
    Retorna lista de (tabla, columna) ordenada por relevancia.

    Utilizado por precondition_parser.py para mapear términos funcionales
    a columnas reales del schema.

    Ejemplo:
      find_column("corredor") → [("ROBLG", "OGCORREDOR"), ("RCLIE", "CLCORREDOR"), ...]
      find_column("riesgo")   → [("RCLIE", "CLRIESGOENT"), ("RCLIE", "CLRIESGOSIS"), ...]
    """
    schema = get_schema(connection=connection)
    pattern_upper = pattern.upper()
    results = []

    for table, columns in schema.get("tables", {}).items():
        for col in columns:
            if pattern_upper in col.upper():
                # Puntaje: coincidencia exacta > prefijo > contiene
                if col.upper() == pattern_upper:
                    score = 0
                elif col.upper().startswith(pattern_upper):
                    score = 1
                else:
                    score = 2
                results.append((score, table, col))

    results.sort(key=lambda x: (x[0], x[1], x[2]))
    return [(t, c) for _, t, c in results[:max_results]]


def column_exists(table: str, column: str, connection=None) -> bool:
    """Verifica que una columna existe en una tabla."""
    cols = get_columns(table.upper(), connection=connection)
    return column.upper() in [c.upper() for c in cols]


def get_tables_for_guard() -> frozenset:
    """
    Retorna frozenset de tablas para `sql_query_guard.py`.

    Combina las tablas del schema con la lista estática de fallback.
    Permite que `sql_query_guard` acepte tablas descubiertas dinámicamente.
    """
    schema = get_schema()
    discovered = frozenset(schema.get("tables", {}).keys())

    # Fallback estático (tablas conocidas antes del schema discovery)
    static_fallback = frozenset({
        "RAGEN", "RIDIOMA", "RAGTIP", "RAGMOT", "RAGCAL",
        "RACOMI", "RACON", "RAGPAR", "RASIST",
        # Tablas confirmadas con db_query_119.py
        "RLOTE", "ROBLG", "RCLIE",
    })

    return discovered | static_fallback


def refresh(connection=None) -> dict:
    """
    Fuerza actualización del schema desde BD.

    Retorna el schema actualizado.
    """
    return get_schema(force_refresh=True, connection=connection)


# ── Internos ──────────────────────────────────────────────────────────────────

def _refresh_from_db(connection) -> dict:
    """Ejecuta INFORMATION_SCHEMA query y construye el dict de schema."""
    cursor = connection.cursor()
    cursor.execute(_SCHEMA_QUERY)
    rows = cursor.fetchall()
    cursor.close()

    tables: dict = {}
    for row in rows:
        table_name = str(row[0]).upper()
        col_name   = str(row[1]).upper()

        # Filtrar tablas de sistema
        if any(table_name.startswith(p.upper()) for p in _EXCLUDED_TABLE_PREFIXES):
            continue

        if table_name not in tables:
            tables[table_name] = []
        if col_name not in tables[table_name]:
            tables[table_name].append(col_name)

    schema = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "table_count": len(tables),
        "tables": tables,
    }
    logger.info("schema_explorer: refreshed — %d tables discovered", len(tables))
    return schema


def _is_cache_fresh(raw: dict) -> bool:
    """Verifica si el cache tiene menos de TTL horas."""
    refreshed_at = raw.get("refreshed_at")
    if not refreshed_at:
        return False
    try:
        dt = datetime.fromisoformat(refreshed_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        return age_hours < _CACHE_TTL_HOURS
    except Exception:
        return False


def _write_cache(schema: dict) -> None:
    """Escribe el schema al disco."""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("schema_explorer: cache written to %s", _CACHE_PATH)
    except Exception as exc:
        logger.warning("schema_explorer: could not write cache: %s", exc)


def _connect():
    """Crea conexión pyodbc con env vars. Nunca hardcodea credenciales."""
    import pyodbc

    server = os.environ.get("RS_QA_DB_SERVER", _DB_SERVER_DEFAULT)
    user   = os.environ.get("RS_QA_DB_USER",   _DB_USER_DEFAULT)
    pwd    = os.environ.get("RS_QA_DB_PASS",   "")
    db     = os.environ.get("RS_QA_DB_NAME",   _DB_NAME_DEFAULT)

    if not pwd:
        raise ValueError("RS_QA_DB_PASS env var is required for schema_explorer")

    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={db};"
        f"UID={user};"
        f"PWD={pwd};"
        f"Connection Timeout=10;"
    )
    return pyodbc.connect(conn_str)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="schema_explorer — DB schema discovery")
    parser.add_argument("--refresh", action="store_true", help="Forzar actualización del cache")
    parser.add_argument("--find", metavar="PATTERN", help="Buscar columnas por patrón")
    parser.add_argument("--table", metavar="TABLA", help="Listar columnas de una tabla")
    parser.add_argument("--tables", action="store_true", help="Listar todas las tablas")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=__import__("sys").stderr,
                            format="%(levelname)s %(name)s: %(message)s")

    if args.refresh:
        s = refresh()
        print(f"Refreshed: {s['table_count']} tables at {s['refreshed_at']}")
    elif args.find:
        matches = find_column(args.find)
        if matches:
            print(f"Columns matching '{args.find}':")
            for t, c in matches:
                print(f"  {t}.{c}")
        else:
            print(f"No columns found matching '{args.find}'")
    elif args.table:
        cols = get_columns(args.table)
        if cols:
            print(f"{args.table.upper()} columns ({len(cols)}):")
            for c in cols:
                print(f"  {c}")
        else:
            print(f"Table '{args.table}' not found in schema cache")
    elif args.tables:
        tables = get_tables()
        print(f"{len(tables)} tables:")
        for t in tables:
            print(f"  {t}")
    else:
        parser.print_help()
