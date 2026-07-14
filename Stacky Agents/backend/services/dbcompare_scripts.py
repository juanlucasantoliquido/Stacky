"""services/dbcompare_scripts.py — Plan 125 F2/F3.

Emitters de paridad y resguardo por dialecto, a partir de un SchemaDiff v1
(doc 123 §F1) APLANADO por `flatten_diff`. Puro: string -> string, sin tocar
BD. Stacky GENERA estos scripts; nunca los ejecuta (human-in-the-loop).
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from os import replace as _os_replace
from pathlib import Path
from typing import TypedDict

from runtime_paths import data_dir
from services import dbcompare_sqlnames as sqlnames


class DbCompareRunError(RuntimeError):
    """Bundle invalido, run no encontrado/no done, o dependencia (Plan 122/123) ausente."""


class ScriptPiece(TypedDict):
    action: str  # kind del diff (p.ej. "table_added") o "table_backup"/"rollback_..."
    object_type: str
    schema: str
    name: str
    sql: str
    destructive: bool  # True si puede perder datos u objetos
    modifies_table: bool  # True si toca una tabla existente en destino


# ---------------------------------------------------------------------------
# F2 (parte 0): flatten_diff — SchemaDiff v1 anidado -> piezas planas
# ---------------------------------------------------------------------------


def flatten_diff(diff: dict) -> list[dict]:
    """Traduce diff["items"] (con "action" + "changes"[]) a una secuencia
    plana de piezas {"kind","object_type","schema","name","detail"}, en el
    mismo orden en que aparecen en el SchemaDiff v1 (doc 123 §F1)."""
    pieces: list[dict] = []
    for item in diff.get("items", []):
        action = item.get("action")
        if action in ("added", "removed"):
            pieces.append(
                {
                    "kind": f"{item['object_type']}_{action}",
                    "object_type": item["object_type"],
                    "schema": item["schema"],
                    "name": item["name"],
                    "detail": {},
                }
            )
        elif action == "changed":
            for change in item.get("changes", []):
                pieces.append(
                    {
                        "kind": change["kind"],
                        "object_type": item["object_type"],
                        "schema": item["schema"],
                        "name": item["name"],
                        "detail": change.get("detail", {}),
                    }
                )
    return pieces


# ---------------------------------------------------------------------------
# Lookups sobre el snapshot ({"alias":..., "schemas": {schema: {"tables": {...
# }, "views": {...}, "sequences": [...]}}}, forma congelada en doc 122 §F3)
# ---------------------------------------------------------------------------


def _get_table(schema_obj: dict, schema: str, name: str) -> dict:
    return schema_obj.get("schemas", {}).get(schema, {}).get("tables", {}).get(name, {})


def _get_view(schema_obj: dict, schema: str, name: str) -> dict:
    return schema_obj.get("schemas", {}).get(schema, {}).get("views", {}).get(name, {})


def _find_by_name(items: list[dict], name: str | None) -> dict | None:
    for it in items:
        if it.get("name") == name:
            return it
    return None


# ---------------------------------------------------------------------------
# Renderers reutilizables (columnas, tabla completa, piezas de constraint)
# ---------------------------------------------------------------------------


def render_column_def(col: dict, dialect: str) -> str:
    q = sqlnames.quote_ident(col["name"], dialect)
    parts = [q, col.get("type", "")]
    if dialect == "sqlserver" and col.get("autoincrement"):
        parts.append("IDENTITY(1,1)")
    parts.append("NULL" if col.get("nullable", True) else "NOT NULL")
    return " ".join(parts)


def render_create_table(schema: str, name: str, table: dict, dialect: str) -> str:
    lines = [f"    {render_column_def(col, dialect)}" for col in table.get("columns", [])]
    pk = table.get("primary_key") or {}
    if pk.get("columns"):
        pk_name = pk.get("name") or f"PK_{name}"
        cols_q = ", ".join(sqlnames.quote_ident(c, dialect) for c in pk["columns"])
        lines.append(f"    CONSTRAINT {sqlnames.quote_ident(pk_name, dialect)} PRIMARY KEY ({cols_q})")
    body = ",\n".join(lines)
    q = sqlnames.qualified(schema, name, dialect)
    return f"CREATE TABLE {q} (\n{body}\n);"


def _render_index_create(schema: str, table: str, idx: dict, dialect: str) -> str:
    kw = "UNIQUE " if idx.get("unique") else ""
    cols_q = ", ".join(sqlnames.quote_ident(c, dialect) for c in idx["columns"])
    n_q = sqlnames.quote_ident(idx["name"], dialect)
    return f"CREATE {kw}INDEX {n_q} ON {sqlnames.qualified(schema, table, dialect)} ({cols_q});"


def _render_fk_add(schema: str, table: str, fk: dict, dialect: str) -> str:
    cols_q = ", ".join(sqlnames.quote_ident(c, dialect) for c in fk["columns"])
    ref_cols_q = ", ".join(sqlnames.quote_ident(c, dialect) for c in fk["referred_columns"])
    ref_q = sqlnames.qualified(fk["referred_schema"], fk["referred_table"], dialect)
    n_q = sqlnames.quote_ident(fk["name"], dialect)
    return (
        f"ALTER TABLE {sqlnames.qualified(schema, table, dialect)} ADD CONSTRAINT {n_q} "
        f"FOREIGN KEY ({cols_q}) REFERENCES {ref_q} ({ref_cols_q});"
    )


def _render_unique_add(schema: str, table: str, uq: dict, dialect: str) -> str:
    cols_q = ", ".join(sqlnames.quote_ident(c, dialect) for c in uq["columns"])
    n_q = sqlnames.quote_ident(uq["name"], dialect)
    return f"ALTER TABLE {sqlnames.qualified(schema, table, dialect)} ADD CONSTRAINT {n_q} UNIQUE ({cols_q});"


def _render_check_add(schema: str, table: str, ck: dict, dialect: str) -> str:
    n_q = sqlnames.quote_ident(ck["name"], dialect)
    return f"ALTER TABLE {sqlnames.qualified(schema, table, dialect)} ADD CONSTRAINT {n_q} CHECK ({ck['sqltext']});"


def _render_drop_constraint(schema: str, table: str, constraint_name: str, dialect: str) -> str:
    n_q = sqlnames.quote_ident(constraint_name, dialect)
    return f"ALTER TABLE {sqlnames.qualified(schema, table, dialect)} DROP CONSTRAINT {n_q};"


def _render_view_create(schema: str, name: str, definition: str | None, dialect: str) -> str:
    q = sqlnames.qualified(schema, name, dialect)
    verb = "CREATE OR ALTER VIEW" if dialect == "sqlserver" else "CREATE OR REPLACE VIEW"
    if definition:
        return f"{verb} {q} AS\n{definition}"
    return "-- DEFINICIÓN NO CAPTURADA EN SNAPSHOT; completar a mano\n" f"-- {verb} {q} AS ..."


def render_header(run_id: str, source_alias: str, target_alias: str, dialect: str, destructive: bool = False) -> str:
    lines = [
        "-- Generado por Stacky · Comparador de BD (plan 125) · NO EJECUTADO por Stacky.",
        f"-- Corrida: {run_id} · Origen: {source_alias} · Destino: {target_alias} · Motor: {dialect}",
        "-- ORDEN: ejecutar SIEMPRE los backups (01_...) antes que la paridad (2xx/9xx).",
    ]
    if destructive:
        lines.append("-- ⚠ DESTRUCTIVO: revisá el backup pareado ANTES de ejecutar.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# F2: emit_parity — pieza(s) aplanada(s) -> SQL de paridad por dialecto
# ---------------------------------------------------------------------------


def emit_parity(item: dict, source_schema_obj: dict, target_schema_obj: dict, dialect: str, ts: str) -> list[ScriptPiece]:
    kind = item["kind"]
    schema = item["schema"]
    name = item["name"]
    object_type = item.get("object_type", "table")
    detail = item.get("detail") or {}
    q = sqlnames.qualified(schema, name, dialect)

    def piece(action: str, sql: str, destructive: bool, modifies_table: bool, obj_type: str | None = None, extra_detail=None) -> ScriptPiece:
        p: dict = {
            "action": action,
            "object_type": obj_type or object_type,
            "schema": schema,
            "name": name,
            "sql": sql,
            "destructive": destructive,
            "modifies_table": modifies_table,
        }
        p["_detail"] = detail if extra_detail is None else extra_detail
        return p  # type: ignore[return-value]

    if kind == "table_added":
        table = _get_table(source_schema_obj, schema, name)
        out = [piece("table_added", render_create_table(schema, name, table, dialect), False, False)]
        for idx in table.get("indexes", []):
            out.append(piece("index_added", _render_index_create(schema, name, idx, dialect), False, False, extra_detail=idx))
        for fk in table.get("foreign_keys", []):
            out.append(piece("fk_added", _render_fk_add(schema, name, fk, dialect), False, True, extra_detail=fk))
        return out

    if kind == "table_removed":
        return [piece("table_removed", f"DROP TABLE {q};", True, True)]

    if kind == "column_added":
        col_source = dict(detail.get("source") or {})
        force_null = (not col_source.get("nullable", True)) and not col_source.get("default")
        if force_null:
            col_source["nullable"] = True
        col_def = render_column_def(col_source, dialect)
        sql = f"ALTER TABLE {q} ADD ({col_def});" if dialect == "oracle" else f"ALTER TABLE {q} ADD {col_def};"
        if force_null:
            sql += (
                "\n-- AJUSTAR: en el origen esta columna es NOT NULL sin default; "
                "completá los datos y endurecé después."
            )
        return [piece("column_added", sql, False, True)]

    if kind == "column_removed":
        c = sqlnames.quote_ident(detail["column"], dialect)
        return [piece("column_removed", f"ALTER TABLE {q} DROP COLUMN {c};", True, True)]

    if kind == "column_type_changed":
        source_col = detail.get("source") or {}
        c = sqlnames.quote_ident(detail["column"], dialect)
        if dialect == "sqlserver":
            nullability = "NULL" if source_col.get("nullable", True) else "NOT NULL"
            sql = f"ALTER TABLE {q} ALTER COLUMN {c} {source_col.get('type', '')} {nullability};"
        else:
            sql = f"ALTER TABLE {q} MODIFY ({c} {source_col.get('type', '')});"
        return [piece("column_type_changed", sql, True, True)]

    if kind in ("column_nullable_relaxed", "column_nullable_tightened"):
        source_col = detail.get("source") or {}
        c = sqlnames.quote_ident(detail["column"], dialect)
        nullability = "NULL" if source_col.get("nullable", True) else "NOT NULL"
        if dialect == "sqlserver":
            sql = f"ALTER TABLE {q} ALTER COLUMN {c} {source_col.get('type', '')} {nullability};"
        else:
            sql = f"ALTER TABLE {q} MODIFY ({c} {nullability});"
        destructive = kind == "column_nullable_tightened"
        return [piece(kind, sql, destructive, True)]

    if kind == "column_default_changed":
        source_col = detail.get("source") or {}
        column = detail["column"]
        expr = source_col.get("default")
        c_q = sqlnames.quote_ident(column, dialect)
        if dialect == "sqlserver":
            df_name_q = sqlnames.quote_ident(f"DF_{name}_{column}", dialect)
            sql = (
                "DECLARE @df sysname;\n"
                "SELECT @df = dc.name FROM sys.default_constraints dc\n"
                "JOIN sys.columns c ON c.default_object_id = dc.object_id\n"
                f"WHERE dc.parent_object_id = OBJECT_ID(N'{schema}.{name}') AND c.name = N'{column}';\n"
                f"IF @df IS NOT NULL EXEC(N'ALTER TABLE {q} DROP CONSTRAINT [' + @df + N']');\n"
                f"ALTER TABLE {q} ADD CONSTRAINT {df_name_q} DEFAULT {expr} FOR {c_q};"
            )
        else:
            sql = f"ALTER TABLE {q} MODIFY ({c_q} DEFAULT {expr});"
        return [piece("column_default_changed", sql, False, True)]

    if kind == "pk_changed":
        source_pk = detail.get("source") or {}
        target_pk = detail.get("target") or {}
        pk_dest_q = sqlnames.quote_ident(target_pk.get("name") or f"PK_{name}", dialect)
        pk_src_q = sqlnames.quote_ident(source_pk.get("name") or f"PK_{name}", dialect)
        cols_q = ", ".join(sqlnames.quote_ident(c, dialect) for c in source_pk.get("columns", []))
        sql = (
            f"ALTER TABLE {q} DROP CONSTRAINT {pk_dest_q};\n"
            f"ALTER TABLE {q} ADD CONSTRAINT {pk_src_q} PRIMARY KEY ({cols_q});"
        )
        return [piece("pk_changed", sql, True, True)]

    if kind == "fk_added":
        return [piece("fk_added", _render_fk_add(schema, name, detail, dialect), False, True)]

    if kind == "unique_added":
        return [piece("unique_added", _render_unique_add(schema, name, detail, dialect), False, True)]

    if kind == "check_added":
        return [piece("check_added", _render_check_add(schema, name, detail, dialect), False, True)]

    if kind in ("fk_removed", "check_removed", "unique_removed"):
        sql = _render_drop_constraint(schema, name, detail["name"], dialect)
        destructive = kind == "unique_removed"  # FIX C3 (critica v1->v2)
        return [piece(kind, sql, destructive, True)]

    if kind == "index_added":
        return [piece("index_added", _render_index_create(schema, name, detail, dialect), False, False)]

    if kind == "index_removed":
        n_q = sqlnames.quote_ident(detail["name"], dialect)
        sql = f"DROP INDEX {n_q} ON {q};" if dialect == "sqlserver" else f"DROP INDEX {n_q};"
        return [piece("index_removed", sql, False, True)]

    if kind in ("view_added", "view_definition_changed"):
        definition = _get_view(source_schema_obj, schema, name).get("definition")
        return [piece(kind, _render_view_create(schema, name, definition, dialect), False, False, obj_type="view")]

    if kind == "view_removed":
        return [piece("view_removed", f"DROP VIEW {q};", False, False, obj_type="view")]

    if kind == "sequence_added":
        sql = f"CREATE SEQUENCE {q} START WITH 1; -- START WITH no capturado en snapshot v1"
        return [piece("sequence_added", sql, False, False, obj_type="sequence")]

    if kind == "sequence_removed":
        return [piece("sequence_removed", f"DROP SEQUENCE {q};", False, False, obj_type="sequence")]

    raise ValueError(f"kind de diff no soportado por los emitters (Plan 125 F2): {kind!r}")


# ---------------------------------------------------------------------------
# F2: emit_resguardo — backup de datos y/o rollback DDL por pieza
# ---------------------------------------------------------------------------

# Piezas destructive=true que tocan DATOS -> backup de datos de la tabla.
_DATA_BACKUP_KINDS = {
    "table_removed",
    "column_removed",
    "column_type_changed",
    "column_nullable_tightened",
    "pk_changed",
    "unique_removed",  # FIX C3
}

# Piezas que DROPean/cambian un objeto reconstruible -> rollback DDL desde destino.
_RECONSTRUCTIBLE_KINDS = {
    "index_removed",
    "fk_removed",
    "unique_removed",
    "check_removed",
    "view_removed",
    "table_removed",
    "pk_changed",
    "column_type_changed",
    "column_nullable_tightened",
}


def _render_data_backup(schema: str, name: str, dialect: str, ts: str) -> ScriptPiece:
    bkp = sqlnames.backup_table_name(name, ts, sqlnames.IDENT_MAX[dialect])
    q = sqlnames.qualified(schema, name, dialect)
    q_bkp = sqlnames.qualified(schema, bkp, dialect)
    if dialect == "oracle":
        sql = (
            f"CREATE TABLE {q_bkp} AS SELECT * FROM {q};\n"
            "DECLARE v_src NUMBER; v_bak NUMBER;\n"
            "BEGIN\n"
            f"  SELECT COUNT(*) INTO v_src FROM {q};\n"
            f"  SELECT COUNT(*) INTO v_bak FROM {q_bkp};\n"
            "  IF v_src <> v_bak THEN\n"
            "    RAISE_APPLICATION_ERROR(-20001, 'BACKUP INCOMPLETO: counts no coinciden "
            f"para {schema}.{name} - NO CONTINUAR con la paridad');\n"
            "  END IF;\n"
            "END;\n/"
        )
    else:
        sql = (
            f"SELECT * INTO {q_bkp} FROM {q};\n"
            f"IF (SELECT COUNT(*) FROM {q_bkp}) <> (SELECT COUNT(*) FROM {q})\n"
            "    THROW 50001, 'BACKUP INCOMPLETO: counts no coinciden "
            f"para {schema}.{name} - NO CONTINUAR con la paridad', 1;"
        )
    return {
        "action": "table_backup",
        "object_type": "table",
        "schema": schema,
        "name": name,
        "sql": sql,
        "destructive": False,
        "modifies_table": False,
    }  # type: ignore[return-value]


def _render_rollback(kind: str, piece: ScriptPiece, target_schema_obj: dict, dialect: str, ts: str) -> ScriptPiece | None:
    schema = piece["schema"]
    name = piece["name"]
    q = sqlnames.qualified(schema, name, dialect)
    target_alias = target_schema_obj.get("alias", "<target>")
    header = f"-- ROLLBACK: recrea el objeto tal como existía en {target_alias} el {ts}\n"
    detail = piece.get("_detail") or {}  # type: ignore[attr-defined]

    if kind == "table_removed":
        table = _get_table(target_schema_obj, schema, name)
        body = (
            render_create_table(schema, name, table, dialect)
            if table.get("columns")
            else f"-- (definición de {name} no disponible en el snapshot destino)"
        )
        sql = header + body + "\n-- Los DATOS se restauran desde la tabla de backup pareada."
    elif kind == "index_removed":
        idx = _find_by_name(_get_table(target_schema_obj, schema, name).get("indexes", []), detail.get("name"))
        sql = header + (
            _render_index_create(schema, name, idx, dialect)
            if idx
            else f"-- (definición de índice {detail.get('name')} no disponible en el snapshot destino)"
        )
    elif kind == "fk_removed":
        fk = _find_by_name(_get_table(target_schema_obj, schema, name).get("foreign_keys", []), detail.get("name"))
        sql = header + (
            _render_fk_add(schema, name, fk, dialect)
            if fk
            else f"-- (definición de FK {detail.get('name')} no disponible en el snapshot destino)"
        )
    elif kind == "unique_removed":
        uq = _find_by_name(_get_table(target_schema_obj, schema, name).get("unique_constraints", []), detail.get("name"))
        sql = header + (
            _render_unique_add(schema, name, uq, dialect)
            if uq
            else f"-- (definición de UNIQUE {detail.get('name')} no disponible en el snapshot destino)"
        )
    elif kind == "check_removed":
        ck = _find_by_name(_get_table(target_schema_obj, schema, name).get("check_constraints", []), detail.get("name"))
        sql = header + (
            _render_check_add(schema, name, ck, dialect)
            if ck
            else f"-- (definición de CHECK {detail.get('name')} no disponible en el snapshot destino)"
        )
    elif kind == "view_removed":
        definition = _get_view(target_schema_obj, schema, name).get("definition")
        sql = header + _render_view_create(schema, name, definition, dialect)
    elif kind == "pk_changed":
        target_pk = detail.get("target") or {}
        source_pk = detail.get("source") or {}
        cols_q = ", ".join(sqlnames.quote_ident(c, dialect) for c in target_pk.get("columns", []))
        sql = header + (
            f"ALTER TABLE {q} DROP CONSTRAINT {sqlnames.quote_ident(source_pk.get('name') or f'PK_{name}', dialect)};\n"
            f"ALTER TABLE {q} ADD CONSTRAINT {sqlnames.quote_ident(target_pk.get('name') or f'PK_{name}', dialect)} "
            f"PRIMARY KEY ({cols_q});"
        )
    elif kind in ("column_type_changed", "column_nullable_tightened"):
        target_col = detail.get("target") or {}
        col_name = detail.get("column")
        c_q = sqlnames.quote_ident(col_name, dialect) if col_name else ""
        if dialect == "sqlserver":
            nullability = "NULL" if target_col.get("nullable", True) else "NOT NULL"
            sql = header + f"ALTER TABLE {q} ALTER COLUMN {c_q} {target_col.get('type', '')} {nullability};"
        else:
            sql = header + f"ALTER TABLE {q} MODIFY ({c_q} {target_col.get('type', '')});"
    else:
        return None

    return {
        "action": f"rollback_{kind}",
        "object_type": piece["object_type"],
        "schema": schema,
        "name": name,
        "sql": sql,
        "destructive": False,
        "modifies_table": False,
    }  # type: ignore[return-value]


def emit_resguardo(piece: ScriptPiece, source_schema_obj: dict, target_schema_obj: dict, dialect: str, ts: str) -> list[ScriptPiece]:
    kind = piece["action"]
    out: list[ScriptPiece] = []
    if kind in _DATA_BACKUP_KINDS:
        out.append(_render_data_backup(piece["schema"], piece["name"], dialect, ts))
    if kind in _RECONSTRUCTIBLE_KINDS:
        rb = _render_rollback(kind, piece, target_schema_obj, dialect, ts)
        if rb is not None:
            out.append(rb)
    return out


# ---------------------------------------------------------------------------
# F4: order_table_pieces — orden seguro por FKs (Kahn) para creates/drops
# ---------------------------------------------------------------------------


def order_table_pieces(pieces: list[ScriptPiece], schema_obj: dict, mode: str) -> tuple[list[ScriptPiece], list[str], str | None]:
    """Ordena piezas table_added ("create") o table_removed ("drop") por sus
    FKs dentro del propio conjunto de `pieces` (FKs hacia tablas fuera del
    conjunto se ignoran: esas tablas ya existen sin cambios). "create" ->
    padres antes que hijos (FKs del snapshot ORIGEN); "drop" -> hijos antes
    que padres (FKs del snapshot DESTINO). Empates por nombre ASC (Kahn).
    Si hay un ciclo, el subconjunto ciclico cae a orden alfabetico y se
    devuelve la linea de warning literal para el README del bundle.
    """
    nodes = [(p["schema"], p["name"]) for p in pieces]
    node_set = set(nodes)
    by_key = {(p["schema"], p["name"]): p for p in pieces}

    indegree = {k: 0 for k in nodes}
    adj: dict[tuple[str, str], list[tuple[str, str]]] = {k: [] for k in nodes}
    for key in nodes:
        schema, name = key
        table = _get_table(schema_obj, schema, name)
        for fk in table.get("foreign_keys", []):
            ref_key = (fk.get("referred_schema"), fk.get("referred_table"))
            if ref_key not in node_set or ref_key == key:
                continue
            before, after = (ref_key, key) if mode == "create" else (key, ref_key)
            adj[before].append(after)
            indegree[after] += 1

    remaining = set(nodes)
    ready = sorted(k for k in remaining if indegree[k] == 0)
    ordered_keys: list[tuple[str, str]] = []
    while ready:
        ready.sort()
        k = ready.pop(0)
        if k not in remaining:
            continue
        ordered_keys.append(k)
        remaining.discard(k)
        for v in adj[k]:
            indegree[v] -= 1
            if indegree[v] == 0 and v in remaining:
                ready.append(v)

    cycle_keys = sorted(remaining)
    ordered_keys.extend(cycle_keys)

    warning = None
    cycle_names = [f"{s}.{n}" for s, n in cycle_keys]
    if cycle_names:
        warning = f"⚠ Ciclo de FKs detectado entre: {', '.join(cycle_names)}; revisá el orden manualmente."

    ordered_pieces = [by_key[k] for k in ordered_keys]
    return ordered_pieces, cycle_names, warning


def collect_resguardos(
    pieces: list[ScriptPiece], source_schema_obj: dict, target_schema_obj: dict, dialect: str, ts: str
) -> list[ScriptPiece]:
    """emit_resguardo por cada pieza, dedupeando el backup de DATOS por
    (schema, tabla) — 1 solo backup por tabla por bundle."""
    seen_tables: set[tuple[str, str]] = set()
    out: list[ScriptPiece] = []
    for p in pieces:
        for r in emit_resguardo(p, source_schema_obj, target_schema_obj, dialect, ts):
            if r["action"] == "table_backup":
                key = (r["schema"], r["name"])
                if key in seen_tables:
                    continue
                seen_tables.add(key)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# F3: bundle + manifest con emparejamiento 1:1 (KPI-1)
# ---------------------------------------------------------------------------

_BUNDLES_DIRNAME = "db_compare/bundles"  # data_dir()/db_compare/bundles/<run_id>/
MANIFEST_VERSION = 1

# Kinds que REQUIEREN resguardo pareado (backup de datos y/o rollback DDL).
# Nota de diseño (hallazgo de implementacion, no cubierto por la critica v1->v2
# escrita en el doc): el texto de KPI-1 dice "destructive=true O modifies_table=true",
# pero piezas puramente aditivas (column_added, fk_added, unique_added, check_added)
# tienen modifies_table=true en la tabla de F2 y a la vez "sin backup" por diseño
# explicito de §F2 ("Piezas aditivas puras... sin backup, backup_file: null").
# El invariante real y consistente es: requiere pareo exactamente el conjunto de
# kinds que emit_resguardo() efectivamente sabe resguardar (_DATA_BACKUP_KINDS |
# _RECONSTRUCTIBLE_KINDS) — asi el invariante nunca puede violarse por construccion
# y las piezas aditivas quedan con backup_file/rollback_file=null tal como pide el plan.
_REQUIRES_RESGUARDO_KINDS = _DATA_BACKUP_KINDS | _RECONSTRUCTIBLE_KINDS


def _bundle_dir(run_id: str) -> Path:
    return data_dir() / _BUNDLES_DIRNAME / run_id


def _render_readme(manifest: dict, warnings: list[str]) -> str:
    lines = [
        f"# Bundle de paridad — {manifest['run_id']}",
        "",
        f"Origen: {manifest['source_alias']} · Destino: {manifest['target_alias']} · Motor: {manifest['engine']}",
        "",
        "🛑 Si CUALQUIER backup falla su verificación de counts: NO ejecutar NINGÚN "
        "script de paridad ni destructivo. Primero resolver el backup.",
        "",
        "Orden: 1) 01_backups/ 2) 02_paridad/ 3) 09_destructivo/ (revisados).",
        "",
    ]
    for w in warnings:
        lines.append(w)
        lines.append("")
    lines.append("## Entradas")
    lines.append("")
    for e in manifest["entries"]:
        lines.append(
            f"- `{e['file']}` ({e['action']}) — backup: {e['backup_file'] or '—'} · "
            f"rollback: {e['rollback_file'] or '—'}"
        )
    return "\n".join(lines) + "\n"


def _write_bundle_atomic(run_id: str, files: dict[str, str]) -> None:
    """[FIX C4 de la critica v1->v2] Escribe TODO el bundle bajo <run_id>.tmp/
    y recien al final hace os.replace() al directorio final. Si algo falla
    antes de este punto (p.ej. la invariante KPI-1), CERO bytes se tocan en
    disco: nunca se persiste un bundle parcial ni invalido."""
    base = data_dir() / _BUNDLES_DIRNAME
    final_dir = base / run_id
    tmp_dir = base / f"{run_id}.tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for relpath, content in files.items():
        dest = tmp_dir / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    if final_dir.exists():
        shutil.rmtree(final_dir)
    _os_replace(str(tmp_dir), str(final_dir))


def generate_parity_bundle_from_diff(
    diff: dict,
    run_id: str,
    source_schema_obj: dict,
    target_schema_obj: dict,
    dialect: str,
    ts: str | None = None,
) -> dict:
    """Version PURA (sin depender de services.dbcompare_runs, Plan 123 F2 —
    ver NOTA C1 en doc 125 v2 F3) de la materializacion del bundle: recibe el
    SchemaDiff v1 y ambos snapshots YA CARGADOS por el caller. Construye todo
    en memoria, valida el invariante KPI-1, y RECIEN ENTONCES escribe en
    disco de forma atomica (FIX C4)."""
    if ts is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    source_alias = source_schema_obj.get("alias") or diff.get("source", {}).get("alias", "origen")
    target_alias = target_schema_obj.get("alias") or diff.get("target", {}).get("alias", "destino")

    flat_items = flatten_diff(diff)
    item_groups = [(item, emit_parity(item, source_schema_obj, target_schema_obj, dialect, ts)) for item in flat_items]

    create_groups = [g for g in item_groups if g[0]["kind"] == "table_added"]
    drop_groups = [g for g in item_groups if g[0]["kind"] == "table_removed"]
    other_groups = [g for g in item_groups if g[0]["kind"] not in ("table_added", "table_removed")]

    warnings: list[str] = []
    if create_groups:
        reps = [pcs[0] for _, pcs in create_groups]
        ordered_reps, _cycle, warn = order_table_pieces(reps, source_schema_obj, "create")
        if warn:
            warnings.append(warn)
        by_key = {(pcs[0]["schema"], pcs[0]["name"]): (item, pcs) for item, pcs in create_groups}
        create_groups = [by_key[(p["schema"], p["name"])] for p in ordered_reps]
    if drop_groups:
        reps = [pcs[0] for _, pcs in drop_groups]
        ordered_reps, _cycle, warn = order_table_pieces(reps, target_schema_obj, "drop")
        if warn:
            warnings.append(warn)
        by_key = {(pcs[0]["schema"], pcs[0]["name"]): (item, pcs) for item, pcs in drop_groups}
        drop_groups = [by_key[(p["schema"], p["name"])] for p in ordered_reps]

    parity_pieces: list[ScriptPiece] = [p for _, pcs in (create_groups + other_groups + drop_groups) for p in pcs]
    per_piece_resguardos = [emit_resguardo(p, source_schema_obj, target_schema_obj, dialect, ts) for p in parity_pieces]

    files: dict[str, str] = {}

    # Pasada 1+2: backups de datos, dedupeados por tabla, numerados 001+ en el
    # orden de la PRIMERA pieza que los necesita.
    backup_seq_by_table: dict[tuple[str, str], int] = {}
    for _p, resguardos in zip(parity_pieces, per_piece_resguardos):
        for r in resguardos:
            if r["action"] == "table_backup" and (r["schema"], r["name"]) not in backup_seq_by_table:
                backup_seq_by_table[(r["schema"], r["name"])] = len(backup_seq_by_table) + 1

    backup_file_by_table: dict[tuple[str, str], str] = {}
    for (schema, name), seq in backup_seq_by_table.items():
        backup_piece = _render_data_backup(schema, name, dialect, ts)
        relpath = f"01_backups/{sqlnames.script_filename(seq, 'table_backup', schema, name)}"
        files[relpath] = render_header(run_id, source_alias, target_alias, dialect) + "\n\n" + backup_piece["sql"] + "\n"
        backup_file_by_table[(schema, name)] = relpath

    # Pasada 3: rollbacks, uno por pieza que lo necesite, numerados a
    # continuacion de los backups de datos.
    rollback_seq = len(backup_seq_by_table)
    rollback_file_by_index: dict[int, str] = {}
    for i, (_p, resguardos) in enumerate(zip(parity_pieces, per_piece_resguardos)):
        for r in resguardos:
            if r["action"].startswith("rollback_"):
                rollback_seq += 1
                relpath = f"01_backups/{sqlnames.script_filename(rollback_seq, r['action'], r['schema'], r['name'])}"
                files[relpath] = render_header(run_id, source_alias, target_alias, dialect) + "\n\n" + r["sql"] + "\n"
                rollback_file_by_index[i] = relpath

    # Pasada 4: paridad no destructiva (201+) y destructiva (901+), en el
    # orden ya resuelto por FK para los grupos de tabla.
    parity_seq = 200
    destructive_seq = 900
    entries: list[dict] = []
    for i, p in enumerate(parity_pieces):
        if p["destructive"]:
            destructive_seq += 1
            seq, group_dir = destructive_seq, "09_destructivo"
        else:
            parity_seq += 1
            seq, group_dir = parity_seq, "02_paridad"
        relpath = f"{group_dir}/{sqlnames.script_filename(seq, p['action'], p['schema'], p['name'])}"
        header = render_header(run_id, source_alias, target_alias, dialect, destructive=p["destructive"])
        files[relpath] = header + "\n\n" + p["sql"] + "\n"

        backup_file = backup_file_by_table.get((p["schema"], p["name"])) if p["action"] in _DATA_BACKUP_KINDS else None
        rollback_file = rollback_file_by_index.get(i)

        entries.append(
            {
                "seq": seq,
                "file": relpath,
                "action": p["action"],
                "object_type": p["object_type"],
                "schema": p["schema"],
                "name": p["name"],
                "destructive": p["destructive"],
                "modifies_table": p["modifies_table"],
                "backup_file": backup_file,
                "rollback_file": rollback_file,
            }
        )

    # Invariante KPI-1: se valida ANTES de escribir nada a disco (FIX C4).
    for e in entries:
        if e["action"] in _REQUIRES_RESGUARDO_KINDS and not (e["backup_file"] or e["rollback_file"]):
            raise DbCompareRunError(
                f"invariante de pareo violada (Plan 125 KPI-1): {e['schema']}.{e['name']} "
                f"({e['action']}) requiere backup_file o rollback_file y no tiene ninguno"
            )

    manifest = {
        "version": MANIFEST_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine": dialect,
        "source_alias": source_alias,
        "target_alias": target_alias,
        "entries": entries,
        "counts": {
            "backups": len(backup_file_by_table) + len(rollback_file_by_index),
            "parity": sum(1 for e in entries if not e["destructive"]),
            "destructive": sum(1 for e in entries if e["destructive"]),
        },
    }
    files["MANIFEST.json"] = json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True)
    files["README.md"] = _render_readme(manifest, warnings)

    _write_bundle_atomic(run_id, files)
    return manifest


def load_manifest(run_id: str) -> dict | None:
    path = _bundle_dir(run_id) / "MANIFEST.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def bundle_zip_bytes(run_id: str) -> bytes:
    base = _bundle_dir(run_id)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(base.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(base)).replace("\\", "/"))
    return buf.getvalue()


def read_bundle_file(run_id: str, rel_path: str) -> str | None:
    """Lee el contenido de un archivo del bundle ya materializado. El CALLER
    (API F5) es responsable de validar `rel_path` contra el allowlist del
    manifest antes de llamar esto — esta función solo lee, no valida."""
    path = _bundle_dir(run_id) / rel_path
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def generate_parity_bundle(run_id: str) -> dict:
    """Wrapper por run_id real. Resuelve el run vía services.dbcompare_runs
    (Plan 123 F2) y los snapshots de origen/destino vía services.dbcompare_snapshot
    (Plan 122 F3) — ambos ahora disponibles (mergeados a main 2026-07-14, ver
    doc 125 v2 §F3/C1, gap cerrado)."""
    from services import dbcompare_runs, dbcompare_snapshot

    run = dbcompare_runs.get_run(run_id)
    if run is None:
        raise DbCompareRunError(f"run no encontrado: {run_id}")
    if run.get("status") != "done":
        raise DbCompareRunError(f"run no está done (status={run.get('status')}): {run_id}")
    diff = run.get("diff")
    if not diff:
        raise DbCompareRunError(f"run '{run_id}' está done pero no tiene diff persistido")

    source_schema_obj = dbcompare_snapshot.load_snapshot(run["source_snapshot_id"])
    target_schema_obj = dbcompare_snapshot.load_snapshot(run["target_snapshot_id"])
    if source_schema_obj is None or target_schema_obj is None:
        raise DbCompareRunError(
            f"no se encontraron los snapshots del run '{run_id}' en disco "
            f"(source={run.get('source_snapshot_id')}, target={run.get('target_snapshot_id')})"
        )

    return generate_parity_bundle_from_diff(diff, run_id, source_schema_obj, target_schema_obj, diff["engine"])
