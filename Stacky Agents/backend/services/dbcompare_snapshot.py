"""services/dbcompare_snapshot.py — Plan 122 F3: snapshot canónico de esquema para el
Comparador de BD entre ambientes (serie 122-126).

Produce un JSON v1 determinista (listas ordenadas, dict con sort_keys al hashear) cuyo
content_hash cambia sii el esquema cambia. Persistido bajo
data_dir()/db_compare/snapshots/<alias>/<snapshot_id>.json.

NOTA (fix C5, crítica v2 del plan 122): las secuencias se persisten ORDENADAS
explícitamente — a diferencia de los diccionarios (tablas/vistas, que json.dumps con
sort_keys=True ordena solas), `sequences` es una lista plana cuyo orden de origen NO
está garantizado por el dialecto (relevante en Oracle, con secuencias reales).

NOTA (fix C2, crítica v2 del plan 122): el `id` del snapshot tiene resolución de 1
segundo; `_next_snapshot_id` desambigua colisiones (mismo alias, mismo segundo)
agregando un sufijo `_2`, `_3`, ... determinista por existencia en disco.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

from sqlalchemy import inspect

from runtime_paths import data_dir
from services import dbcompare_registry

SNAPSHOT_VERSION = 1          # shape v1 (compat: NO tocar — referencia histórica)
SNAPSHOT_VERSION_V2 = 2       # Plan 179 — superset aditivo con type_detail por columna
_SNAPSHOTS_DIRNAME = "db_compare/snapshots"
_MAX_SNAPSHOTS_PER_ALIAS = 20
_VIEW_DEF_MAX_CHARS = 100_000


def default_schemas(engine_kind: str, username: str) -> list[str]:
    if engine_kind == "sqlserver":
        return ["dbo"]
    if engine_kind == "oracle":
        return [(username or "").upper()]
    return ["main"]  # sqlite


def _snapshot_dir(alias: str):
    return data_dir() / _SNAPSHOTS_DIRNAME / alias


def _snapshot_path(alias: str, snapshot_id: str):
    return _snapshot_dir(alias) / f"{snapshot_id}.json"


def _next_snapshot_id(alias: str, taken_at: datetime) -> str:
    base = f"{alias}_{taken_at:%Y%m%dT%H%M%SZ}"
    if not _snapshot_path(alias, base).exists():
        return base
    i = 2
    while _snapshot_path(alias, f"{base}_{i}").exists():
        i += 1
    return f"{base}_{i}"


TYPE_DETAIL_KEYS = ("base", "precision", "scale", "length", "collation", "timezone", "identity", "computed")


def _snapshot_v2_enabled() -> bool:
    import config as _config

    return bool(getattr(_config.config, "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED", False))


def _int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_sqltext_for_hash(sqltext: str) -> str:
    import re as _re

    return _re.sub(r"\s+", " ", (sqltext or "")).strip().upper()


def derive_type_detail(col: dict) -> dict:
    """Plan 179 F1 — deriva el subobjeto type_detail v1 (doc 179 §4) desde el dict
    de columna que devuelve insp.get_columns(). Función PURA: sin red, sin disco.
    Los subcampos que el dialecto no reporta quedan None — NUNCA se inventan."""
    col_type = col.get("type")
    type_str = str(col_type).upper() if col_type is not None else ""
    base = type_str.split("(")[0].strip()

    tz_attr = getattr(col_type, "timezone", None)
    identity_raw = col.get("identity")
    identity = None
    if isinstance(identity_raw, dict) and identity_raw:
        identity = {
            "start": _int_or_none(identity_raw.get("start")),
            "increment": _int_or_none(identity_raw.get("increment")),
        }
    computed_raw = col.get("computed")
    computed = None
    if isinstance(computed_raw, dict) and computed_raw:
        sqltext = computed_raw.get("sqltext")
        computed = {
            "persisted": bool(computed_raw.get("persisted") or False),
            "sqltext_sha256": (
                hashlib.sha256(_normalize_sqltext_for_hash(str(sqltext)).encode("utf-8")).hexdigest()
                if sqltext else None
            ),
        }
    return {
        "base": base,
        "precision": _int_or_none(getattr(col_type, "precision", None)),
        "scale": _int_or_none(getattr(col_type, "scale", None)),
        "length": _int_or_none(getattr(col_type, "length", None)),
        "collation": (str(getattr(col_type, "collation")) if getattr(col_type, "collation", None) else None),
        "timezone": (bool(tz_attr) if tz_attr is not None else None),
        "identity": identity,
        "computed": computed,
    }


def _reflect_table(insp, tname: str, schema: str, *, v2: bool = False) -> dict:
    columns = []
    for col in insp.get_columns(tname, schema=schema):
        default = col.get("default")
        entry = {
            "name": col["name"],
            "type": str(col["type"]).upper(),
            "nullable": bool(col.get("nullable", True)),
            "default": (str(default) if default is not None else None),
            "autoincrement": bool(col.get("autoincrement") or False),
        }
        if v2:
            entry["type_detail"] = derive_type_detail(col)
        columns.append(entry)

    pk_raw = insp.get_pk_constraint(tname, schema=schema) or {}
    primary_key = {
        "name": pk_raw.get("name"),
        "columns": list(pk_raw.get("constrained_columns") or []),
    }

    fks = []
    for fk in insp.get_foreign_keys(tname, schema=schema):
        fks.append({
            "name": fk.get("name"),
            "columns": list(fk.get("constrained_columns") or []),
            "referred_schema": fk.get("referred_schema"),
            "referred_table": fk.get("referred_table"),
            "referred_columns": list(fk.get("referred_columns") or []),
        })
    fks.sort(key=lambda x: x["name"] or "")

    indexes = []
    for ix in insp.get_indexes(tname, schema=schema):
        indexes.append({
            "name": ix.get("name"),
            "columns": list(ix.get("column_names") or []),
            "unique": bool(ix.get("unique")),
        })
    indexes.sort(key=lambda x: x["name"] or "")

    try:
        uniques_raw = insp.get_unique_constraints(tname, schema=schema)
    except NotImplementedError:
        uniques_raw = []
    uniques = [
        {"name": u.get("name"), "columns": list(u.get("column_names") or [])}
        for u in uniques_raw
    ]
    uniques.sort(key=lambda x: x["name"] or "")

    try:
        checks_raw = insp.get_check_constraints(tname, schema=schema)
    except NotImplementedError:
        checks_raw = []
    checks = [{"name": c.get("name"), "sqltext": c.get("sqltext", "")} for c in checks_raw]
    checks.sort(key=lambda x: x["name"] or "")

    return {
        "columns": columns,
        "primary_key": primary_key,
        "foreign_keys": fks,
        "indexes": indexes,
        "unique_constraints": uniques,
        "check_constraints": checks,
    }


def _reflect_view(insp, vname: str, schema: str) -> dict:
    try:
        definition = insp.get_view_definition(vname, schema=schema)
        error = None
    except Exception as exc:  # noqa: BLE001 — permisos insuficientes u otro fallo del dialecto
        definition = None
        error = str(exc)

    if definition is not None:
        text_val = str(definition)[:_VIEW_DEF_MAX_CHARS]
        sha = hashlib.sha256(text_val.encode("utf-8")).hexdigest()
    else:
        text_val = None
        sha = None

    return {"definition": text_val, "definition_sha256": sha, "error": error}


def take_snapshot(alias: str, *, engine=None) -> dict:
    env = dbcompare_registry.get_environment(alias)
    if env is None:
        raise ValueError(f"ambiente desconocido: '{alias}' — registralo primero")

    started = time.monotonic()
    owns_engine = False
    if engine is None:
        from services import dbcompare_engine

        engine = dbcompare_engine.open_engine(alias)
        owns_engine = True

    try:
        v2 = _snapshot_v2_enabled()  # Plan 179 — gate de captura (OFF ⇒ byte-idéntico a v1)
        insp = inspect(engine)
        schemas = env.get("schema_filter") or default_schemas(env["engine"], env["username"])

        schemas_out: dict = {}
        counts_tables = counts_views = counts_sequences = counts_columns = 0

        for schema in schemas:
            tables_out = {}
            for tname in insp.get_table_names(schema=schema):
                table = _reflect_table(insp, tname, schema, v2=v2)
                tables_out[tname] = table
                counts_tables += 1
                counts_columns += len(table["columns"])

            views_out = {}
            for vname in insp.get_view_names(schema=schema):
                views_out[vname] = _reflect_view(insp, vname, schema)
                counts_views += 1

            try:
                sequences = sorted(insp.get_sequence_names(schema=schema))  # [FIX C5]
            except NotImplementedError:
                sequences = []
            counts_sequences += len(sequences)

            schemas_out[schema] = {
                "tables": tables_out,
                "views": views_out,
                "sequences": sequences,
            }

        taken_at_dt = datetime.now(timezone.utc)
        duration_ms = int((time.monotonic() - started) * 1000)
        counts = {
            "tables": counts_tables,
            "views": counts_views,
            "sequences": counts_sequences,
            "columns": counts_columns,
        }

        snapshot_version = SNAPSHOT_VERSION_V2 if v2 else SNAPSHOT_VERSION
        body = {
            "version": snapshot_version,
            "alias": alias,
            "engine": env["engine"],
            "schemas": schemas_out,
            "counts": counts,
        }
        content_hash = hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        snapshot_id = _next_snapshot_id(alias, taken_at_dt)  # [FIX C2]
        result = {
            "version": snapshot_version,
            "id": snapshot_id,
            "alias": alias,
            "engine": env["engine"],
            "taken_at": taken_at_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "duration_ms": duration_ms,
            "schemas": schemas_out,
            "counts": counts,
            "content_hash": content_hash,
        }

        path = _snapshot_path(alias, snapshot_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        prune_snapshots(alias)
        return result
    finally:
        if owns_engine:
            engine.dispose()


def _load_all_raw(alias: str) -> list[dict]:
    d = _snapshot_dir(alias)
    if not d.exists():
        return []
    out = []
    for f in d.glob("*.json"):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — snapshot corrupto: se ignora, no rompe el listado
            continue
    return out


def list_snapshots(alias: str) -> list[dict]:
    raw = _load_all_raw(alias)
    raw.sort(key=lambda s: s.get("taken_at", ""), reverse=True)
    return [
        {
            "id": s.get("id"),
            "taken_at": s.get("taken_at"),
            "duration_ms": s.get("duration_ms"),
            "counts": s.get("counts"),
            "content_hash": s.get("content_hash"),
        }
        for s in raw
    ]


def load_snapshot(snapshot_id: str) -> dict | None:
    root = data_dir() / _SNAPSHOTS_DIRNAME
    if not root.exists():
        return None
    for alias_dir in root.iterdir():
        candidate = alias_dir / f"{snapshot_id}.json"
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return None
    return None


def latest_snapshot(alias: str) -> dict | None:
    snapshots = list_snapshots(alias)
    if not snapshots:
        return None
    return load_snapshot(snapshots[0]["id"])


def prune_snapshots(alias: str) -> int:
    raw = _load_all_raw(alias)
    if len(raw) <= _MAX_SNAPSHOTS_PER_ALIAS:
        return 0
    raw.sort(key=lambda s: s.get("taken_at", ""))  # más viejo primero
    to_delete = raw[: len(raw) - _MAX_SNAPSHOTS_PER_ALIAS]
    deleted = 0
    for s in to_delete:
        path = _snapshot_path(alias, s.get("id", ""))
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except Exception:  # noqa: BLE001
            pass
    return deleted
