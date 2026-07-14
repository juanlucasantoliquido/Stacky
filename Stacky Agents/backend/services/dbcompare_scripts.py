"""services/dbcompare_scripts.py — Plan 125 F2/F3.

Emitters de paridad y resguardo por dialecto, a partir de un SchemaDiff v1
(doc 123 §F1) APLANADO por `flatten_diff`. Puro: string -> string, sin tocar
BD. Stacky GENERA estos scripts; nunca los ejecuta (human-in-the-loop).
"""
from __future__ import annotations

from typing import TypedDict

from services import dbcompare_sqlnames as sqlnames


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
