"""services/dbcompare_data.py — Plan 126 F2: diff de datos por PK para el
Comparador de BD entre ambientes (paridad de DATOS de tablas de parámetros).

Compara filas de una tabla entre dos ambientes registrados (Plan 122), usando
el ÚLTIMO snapshot de cada lado (Plan 122 F3) para resolver PK/columnas, y
SELECTs generados internamente que SIEMPRE pasan por validate_select_only
(services/db_query.py) antes de ejecutarse — cinturón y tiradores: ningún SQL
que no sea SELECT puede llegar al motor (KPI-2).

Ver Stacky Agents/docs/126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md #F2.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from sqlalchemy import text as _sql_text

from config import Config
from services import dbcompare_engine, dbcompare_runs, dbcompare_snapshot
from services import dbcompare_sqlnames as sqlnames
from services import dbcompare_sqlvalues as sqlvalues
from services.db_query import validate_select_only

_MAX_TABLES_PER_DATA_DIFF = 20

_ACTIVE_DATA_RUNS: set[str] = set()
_ACTIVE_LOCK = threading.Lock()


class DbCompareDataError(RuntimeError):
    """La comparación de datos no puede iniciarse o completarse."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# build_select / fetch_rows — SELECT-only, cap +1, orden por PK
# ---------------------------------------------------------------------------


def build_select(
    schema: str, table: str, columns: list[str], pk_cols: list[str], dialect: str, max_rows: int
) -> str:
    q = sqlnames.qualified(schema, table, dialect)
    cols_sql = ", ".join(sqlnames.quote_ident(c, dialect) for c in columns)
    order_sql = ", ".join(sqlnames.quote_ident(c, dialect) for c in pk_cols)
    limit = max_rows + 1  # +1 detecta truncamiento sin contar toda la tabla.
    if dialect == "sqlserver":
        return f"SELECT TOP ({limit}) {cols_sql} FROM {q} ORDER BY {order_sql}"
    if dialect == "oracle":
        return (
            f"SELECT {cols_sql} FROM (SELECT {cols_sql} FROM {q} ORDER BY {order_sql}) "
            f"WHERE ROWNUM <= {limit}"
        )
    if dialect == "sqlite":
        return f"SELECT {cols_sql} FROM {q} ORDER BY {order_sql} LIMIT {limit}"
    raise DbCompareDataError(f"dialecto desconocido: {dialect!r}")


def fetch_rows(engine, sql: str) -> list[tuple]:
    validation = validate_select_only(sql)  # KPI-2 — assert interno, nunca ejecuta si no ok.
    if not validation.ok:
        raise DbCompareDataError(
            f"SQL generado internamente rechazado por validate_select_only: {validation.errors}"
        )
    with engine.connect() as conn:
        result = conn.execute(_sql_text(sql))
        return [tuple(row) for row in result]


# ---------------------------------------------------------------------------
# diff_table_data — resolución de columnas (FIX C3) + diff por PK (KPI-1)
# ---------------------------------------------------------------------------


def _find_table(snapshot: dict, schema: str, table: str) -> dict | None:
    return (snapshot.get("schemas", {}).get(schema, {}).get("tables", {}) or {}).get(table)


def diff_table_data(
    source_alias: str,
    target_alias: str,
    schema: str,
    table: str,
    *,
    engines: tuple | None = None,
    max_rows: int | None = None,
) -> dict:
    if max_rows is None:
        max_rows = Config.STACKY_DB_COMPARE_DATA_MAX_ROWS

    # [FIX C3] paso 1-2: ambos snapshots, explícitos.
    src_snap = dbcompare_snapshot.latest_snapshot(source_alias)
    if src_snap is None:
        raise DbCompareDataError(f"sin snapshot de '{source_alias}'; tomá uno primero")
    tgt_snap = dbcompare_snapshot.latest_snapshot(target_alias)
    if tgt_snap is None:
        raise DbCompareDataError(f"sin snapshot de '{target_alias}'; tomá uno primero")

    # [FIX C3] paso 3: existencia de la tabla en ambos lados.
    src_table = _find_table(src_snap, schema, table)
    if src_table is None:
        raise DbCompareDataError(f"la tabla {schema}.{table} no existe en '{source_alias}'")
    tgt_table = _find_table(tgt_snap, schema, table)
    if tgt_table is None:
        raise DbCompareDataError(f"la tabla {schema}.{table} no existe en '{target_alias}'; no comparable")

    # [FIX C3] paso 4: PK del ORIGEN es la fuente de verdad.
    pk_cols = list(src_table["primary_key"].get("columns") or [])
    if not pk_cols:
        raise DbCompareDataError(f"la tabla {schema}.{table} no tiene PK; no comparable")

    # [FIX C3] paso 5: columnas = intersección por nombre; columns_skipped = unión - intersección.
    src_cols = [c["name"] for c in src_table["columns"]]
    tgt_cols_set = {c["name"] for c in tgt_table["columns"]}
    columns = [c for c in src_cols if c in tgt_cols_set]
    columns_skipped = sorted(({*src_cols, *tgt_cols_set}) - set(columns))

    missing_pk = [c for c in pk_cols if c not in columns]
    if missing_pk:
        raise DbCompareDataError(
            f"el PK de {schema}.{table} ({', '.join(pk_cols)}) no existe completo en '{target_alias}'"
        )

    dialect = src_snap["engine"]

    # [FIX C4] engines=None -> resolver conexiones reales.
    owns_engines = False
    if engines is None:
        source_engine = dbcompare_engine.open_engine(source_alias)
        target_engine = dbcompare_engine.open_engine(target_alias)
        owns_engines = True
    else:
        source_engine, target_engine = engines

    try:
        sql = build_select(schema, table, columns, pk_cols, dialect, max_rows)
        source_rows = fetch_rows(source_engine, sql)
        target_rows = fetch_rows(target_engine, sql)
    finally:
        if owns_engines:
            source_engine.dispose()
            target_engine.dispose()

    truncated = len(source_rows) > max_rows or len(target_rows) > max_rows
    source_rows = source_rows[:max_rows]
    target_rows = target_rows[:max_rows]

    n_pk = len(pk_cols)

    def _to_map(rows: list[tuple]) -> dict[tuple, dict[str, str | None]]:
        out: dict[tuple, dict[str, str | None]] = {}
        for row in rows:
            pk_tuple = tuple(row[:n_pk])
            out[pk_tuple] = {col: sqlvalues.normalize_value(v) for col, v in zip(columns, row)}
        return out

    source_map = _to_map(source_rows)
    target_map = _to_map(target_rows)

    only_source_keys = sorted(set(source_map) - set(target_map))
    only_target_keys = sorted(set(target_map) - set(source_map))
    common_keys = sorted(set(source_map) & set(target_map))

    def _pk_dict(pk_tuple: tuple) -> dict:
        # Normalizado explícitamente (no depender del merge con source_map/target_map
        # para que "pk" de only_source/only_target/changed sea consistente siempre).
        return {col: sqlvalues.normalize_value(v) for col, v in zip(pk_cols, pk_tuple)}

    only_source = [dict(_pk_dict(k), **source_map[k]) for k in only_source_keys]
    only_target = [dict(_pk_dict(k), **target_map[k]) for k in only_target_keys]

    changed = []
    for k in common_keys:
        cells = {
            col: {"source": source_map[k][col], "target": target_map[k][col]}
            for col in columns
            if source_map[k][col] != target_map[k][col]
        }
        if cells:
            changed.append({"pk": _pk_dict(k), "cells": cells})

    # Addendum F2 (descubierto implementando F3): el tipo real de cada columna
    # (del snapshot de origen) viaja con el DataDiff — sql_literal_from_normalized
    # (F1) lo necesita para saber si un valor normalizado va sin comillas
    # (numérico), envuelto en CONVERT/TO_TIMESTAMP (fecha) o citado (texto).
    src_types = {c["name"]: c["type"] for c in src_table["columns"]}
    column_types = {c: src_types[c] for c in columns}

    return {
        "version": 1,
        "schema": schema,
        "table": table,
        "pk_cols": pk_cols,
        "columns": columns,
        "column_types": column_types,
        "columns_skipped": columns_skipped,
        "only_source": only_source,
        "only_target": only_target,
        "changed": changed,
        "row_counts": {"source": len(source_map), "target": len(target_map)},
        "truncated": truncated,
        "identical": not (only_source or only_target or changed),
    }


# ---------------------------------------------------------------------------
# run_data_diff — threaded, lock por run_id, escritura en el archivo del run
# ---------------------------------------------------------------------------


def run_data_diff(run_id: str, tables: list[dict]) -> None:
    if len(tables) > _MAX_TABLES_PER_DATA_DIFF:
        raise DbCompareDataError(
            f"máximo {_MAX_TABLES_PER_DATA_DIFF} tablas por corrida (recibidas {len(tables)})"
        )

    run = dbcompare_runs.get_run(run_id)
    if run is None:
        raise DbCompareDataError(f"corrida '{run_id}' no existe")
    if run.get("status") != "done":
        raise DbCompareDataError(f"la corrida no está done (status={run.get('status')})")

    with _ACTIVE_LOCK:
        if run_id in _ACTIVE_DATA_RUNS:
            raise DbCompareDataError(f"ya hay un diff de datos activo para la corrida '{run_id}'")
        _ACTIVE_DATA_RUNS.add(run_id)

    source_alias = run["source_alias"]
    target_alias = run["target_alias"]
    started = _now()
    data_diff = {
        "status": "running",
        "phase": f"tabla 0/{len(tables)}",
        "tables": {},
        "started_at": _iso(started),
        "finished_at": None,
        "error": None,
    }
    # Reusa el escritor atómico (tmp+os.replace) de dbcompare_runs — MISMO
    # archivo de run, evita un segundo escritor independiente del mismo JSON.
    dbcompare_runs._update(run_id, data_diff=dict(data_diff))

    try:
        threading.Thread(
            target=_execute_data_diff,
            args=(run_id, tables, source_alias, target_alias, data_diff),
            daemon=True,
        ).start()
    except Exception:
        with _ACTIVE_LOCK:
            _ACTIVE_DATA_RUNS.discard(run_id)
        raise


def _execute_data_diff(
    run_id: str, tables: list[dict], source_alias: str, target_alias: str, data_diff: dict
) -> None:
    try:
        for i, t in enumerate(tables, start=1):
            key = f"{t['schema']}.{t['table']}"
            data_diff["phase"] = f"tabla {i}/{len(tables)}: {key}"
            dbcompare_runs._update(run_id, data_diff=dict(data_diff))
            try:
                data_diff["tables"][key] = diff_table_data(source_alias, target_alias, t["schema"], t["table"])
            except DbCompareDataError as exc:
                data_diff["tables"][key] = {"error": str(exc)}
            dbcompare_runs._update(run_id, data_diff=dict(data_diff))
        data_diff["status"] = "done"
        data_diff["phase"] = "done"
    except Exception as exc:  # noqa: BLE001 — cualquier fallo inesperado termina en error, nunca "running" para siempre.
        data_diff["status"] = "error"
        data_diff["error"] = str(exc)
    finally:
        data_diff["finished_at"] = _iso(_now())
        dbcompare_runs._update(run_id, data_diff=dict(data_diff))
        with _ACTIVE_LOCK:
            _ACTIVE_DATA_RUNS.discard(run_id)
