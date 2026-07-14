"""api/db_compare.py — Plan 122 F4: núcleo del Comparador de BD entre ambientes
(serie 122-126). url_prefix="/db-compare" → rutas finales /api/db-compare/...

Gate estricto: TODOS los endpoints excepto /health devuelven 403 si
STACKY_DB_COMPARE_ENABLED está OFF (default). El password entra SOLO por
POST .../password (write-only), JAMÁS sale en respuestas ni logs.
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, current_app, jsonify, request

from services import (
    dbcompare_data,
    dbcompare_engine,
    dbcompare_registry,
    dbcompare_runs,
    dbcompare_scripts,
    dbcompare_snapshot,
)
from services import dbcompare_sqlnames as _sqlnames
from services.db_query import validate_select_only as _validate_select_only

bp = Blueprint("db_compare", __name__, url_prefix="/db-compare")


def _require_enabled():
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    return None


def _require_data_enabled():
    """[Plan 126 F4] Gate adicional para paridad de DATOS (hija, opt-in doble)."""
    if not getattr(_config.config, "STACKY_DB_COMPARE_DATA_DIFF_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "Paridad de datos deshabilitada (STACKY_DB_COMPARE_DATA_DIFF_ENABLED).",
        }), 403
    return None


def _with_snapshot_recency(env: dict) -> dict:
    """[ADICIÓN ARQUITECTO] agrega latest_snapshot_taken_at/latest_snapshot_hash8."""
    snap = dbcompare_snapshot.latest_snapshot(env["alias"])
    env = dict(env)
    env["latest_snapshot_taken_at"] = snap["taken_at"] if snap else None
    env["latest_snapshot_hash8"] = snap["content_hash"][:8] if snap else None
    return env


@bp.get("/health")
def health_route():
    return jsonify({
        "ok": True,
        "flag_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False)),
        # [FIX C5, Plan 126] la UI (F5) lee este campo para mostrar/ocultar el
        # botón "Comparar datos…" sin tener que llamar a un endpoint aparte.
        "data_diff_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_DATA_DIFF_ENABLED", False)),
        "keyring_available": dbcompare_registry.keyring_available(),
        "drivers": dbcompare_engine.driver_status(),
    })


@bp.get("/environments")
def list_environments_route():
    gate = _require_enabled()
    if gate:
        return gate
    envs = [_with_snapshot_recency(e) for e in dbcompare_registry.list_environments()]
    return jsonify({
        "ok": True,
        "environments": envs,
        "keyring_available": dbcompare_registry.keyring_available(),
    })


@bp.post("/environments")
def upsert_environment_route():
    gate = _require_enabled()
    if gate:
        return gate
    body = request.get_json(silent=True) or {}
    try:
        env = dbcompare_registry.upsert_environment(
            alias=(body.get("alias") or "").strip(),
            engine=(body.get("engine") or "").strip(),
            host=(body.get("host") or "").strip(),
            port=body.get("port"),
            database=(body.get("database") or "").strip(),
            username=(body.get("username") or "").strip(),
            odbc_driver=body.get("odbc_driver") or "ODBC Driver 17 for SQL Server",
            schema_filter=body.get("schema_filter"),
            notes=body.get("notes") or "",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "environment": _with_snapshot_recency(env)})


@bp.delete("/environments/<alias>")
def delete_environment_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    if not dbcompare_registry.delete_environment(alias):
        return jsonify({"ok": False, "error": f"ambiente '{alias}' no existe."}), 404
    return jsonify({"ok": True})


@bp.post("/environments/<alias>/password")
def set_password_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    body = request.get_json(silent=True) or {}
    password = body.get("password")
    if not password:
        return jsonify({"ok": False, "error": "password requerido"}), 400
    if not dbcompare_registry.keyring_available():
        return jsonify({
            "ok": False,
            "error": (
                "keyring no disponible: instale keyring==25.6.0; el password NO se "
                "guardó (nunca se persiste en texto plano)."
            ),
        }), 503
    dbcompare_registry.set_password(alias, password)
    return jsonify({"ok": True})


@bp.delete("/environments/<alias>/password")
def clear_password_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    dbcompare_registry.clear_password(alias)
    return jsonify({"ok": True})


@bp.post("/environments/<alias>/test")
def test_connection_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    result = dbcompare_engine.test_connection(alias)
    return jsonify(result)


@bp.post("/environments/<alias>/snapshot")
def take_snapshot_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    try:
        snapshot = dbcompare_snapshot.take_snapshot(alias)
    except (ValueError, dbcompare_engine.DbCompareEngineError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(snapshot)


@bp.get("/environments/<alias>/snapshots")
def list_snapshots_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    return jsonify({"ok": True, "snapshots": dbcompare_snapshot.list_snapshots(alias)})


@bp.get("/snapshots/<snapshot_id>")
def get_snapshot_route(snapshot_id):
    gate = _require_enabled()
    if gate:
        return gate
    snapshot = dbcompare_snapshot.load_snapshot(snapshot_id)
    if snapshot is None:
        return jsonify({"ok": False, "error": f"snapshot '{snapshot_id}' no existe."}), 404
    return jsonify(snapshot)


# --------------------------------------------------------------------------
# Plan 123 F3 — corridas comparativas (motor de diff sobre los snapshots de arriba)
# --------------------------------------------------------------------------

@bp.post("/compare")
def create_compare_run_route():
    gate = _require_enabled()
    if gate:
        return gate
    body = request.get_json(silent=True) or {}
    source_alias = (body.get("source_alias") or "").strip()
    target_alias = (body.get("target_alias") or "").strip()
    mode = body.get("mode") or "fresh"
    if not source_alias or not target_alias:
        return jsonify({"ok": False, "error": "source_alias y target_alias son requeridos"}), 400
    try:
        run = dbcompare_runs.create_run(source_alias, target_alias, mode=mode)
    except dbcompare_runs.DbCompareBusyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    except (dbcompare_runs.DbCompareRunError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "run": run}), 202


@bp.get("/runs")
def list_runs_route():
    gate = _require_enabled()
    if gate:
        return gate
    raw_limit = request.args.get("limit")
    limit = 50
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "limit debe ser un entero"}), 400
        if limit < 0:
            return jsonify({"ok": False, "error": "limit no puede ser negativo"}), 400
    return jsonify({"ok": True, "runs": dbcompare_runs.list_runs(limit=limit)})


@bp.get("/runs/<run_id>")
def get_run_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    return jsonify(run)


@bp.get("/runs/<run_id>/export.md")
def export_run_markdown_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    if run.get("status") != "done":
        return jsonify({
            "ok": False,
            "error": f"la corrida no está 'done' (status={run.get('status')}).",
        }), 409
    md = dbcompare_runs.export_markdown(run)
    response = current_app.response_class(md, mimetype="text/markdown; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{run_id}.md"'
    return response


# --------------------------------------------------------------------------
# Plan 125 F5 — bundle de scripts de paridad + backups pareados (mismo blueprint,
# mismo _require_enabled; Stacky GENERA, jamás ejecuta — ver doc 125 §3).
# --------------------------------------------------------------------------

_SCRIPTS_RUN_ERRORS = (dbcompare_scripts.DbCompareRunError, dbcompare_runs.DbCompareRunError)


@bp.post("/runs/<run_id>/scripts")
def generate_scripts_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    if run.get("status") != "done":
        return jsonify({
            "ok": False,
            "error": f"la corrida no está 'done' (status={run.get('status')}).",
        }), 409
    try:
        manifest = dbcompare_scripts.generate_parity_bundle(run_id)
    except _SCRIPTS_RUN_ERRORS as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "manifest": manifest})


@bp.get("/runs/<run_id>/scripts")
def get_scripts_manifest_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    manifest = dbcompare_scripts.load_manifest(run_id)
    if manifest is None:
        return jsonify({
            "ok": False,
            "error": "todavía no se generaron scripts de paridad para esta corrida.",
        }), 404
    return jsonify({"ok": True, "manifest": manifest})


def _scripts_allowlist(manifest: dict) -> set[str]:
    allowed = {"README.md", "MANIFEST.json"}
    for entry in manifest.get("entries", []):
        allowed.add(entry["file"])
        if entry.get("backup_file"):
            allowed.add(entry["backup_file"])
        if entry.get("rollback_file"):
            allowed.add(entry["rollback_file"])
    return allowed


@bp.get("/runs/<run_id>/scripts/file")
def get_scripts_file_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    rel_path = request.args.get("path") or ""
    if not rel_path or ".." in rel_path or rel_path.startswith("/") or rel_path.startswith("\\"):
        return jsonify({"ok": False, "error": "path inválido."}), 400
    manifest = dbcompare_scripts.load_manifest(run_id)
    if manifest is None:
        return jsonify({
            "ok": False,
            "error": "todavía no se generaron scripts de paridad para esta corrida.",
        }), 404
    if rel_path not in _scripts_allowlist(manifest):
        return jsonify({"ok": False, "error": "archivo no encontrado en el manifest de esta corrida."}), 400
    content = dbcompare_scripts.read_bundle_file(run_id, rel_path)
    if content is None:
        return jsonify({"ok": False, "error": "archivo no encontrado en disco."}), 404
    return current_app.response_class(content, mimetype="text/plain; charset=utf-8")


@bp.get("/runs/<run_id>/scripts.zip")
def get_scripts_zip_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    manifest = dbcompare_scripts.load_manifest(run_id)
    if manifest is None:
        return jsonify({
            "ok": False,
            "error": "todavía no se generaron scripts de paridad para esta corrida.",
        }), 404
    zip_bytes = dbcompare_scripts.bundle_zip_bytes(run_id)
    response = current_app.response_class(zip_bytes, mimetype="application/zip")
    response.headers["Content-Disposition"] = f'attachment; filename="dbcompare_{run_id}.zip"'
    return response


# --------------------------------------------------------------------------
# Plan 126 F4 — paridad de DATOS (gate doble: master + STACKY_DB_COMPARE_DATA_DIFF_ENABLED)
# --------------------------------------------------------------------------


def _best_effort_row_count(alias: str, schema: str, table: str, dialect: str) -> int | None:
    """[ADICIÓN ARQUITECTO, crítica v2] COUNT(*) best-effort por lado; nunca
    lanza — timeout/error de conexión/driver faltante -> None (no rompe el
    endpoint). El SQL generado pasa por el MISMO validador que F2 (KPI-2)."""
    try:
        q = _sqlnames.qualified(schema, table, dialect)
        sql = f"SELECT COUNT(*) FROM {q}"
        if not _validate_select_only(sql).ok:
            return None
        engine = dbcompare_engine.open_engine(alias)
    except Exception:  # noqa: BLE001 — best-effort: cualquier fallo -> None
        return None
    try:
        from sqlalchemy import text as _sql_text

        with engine.connect() as conn:
            return conn.execute(_sql_text(sql)).scalar()
    except Exception:  # noqa: BLE001
        return None
    finally:
        engine.dispose()


@bp.get("/runs/<run_id>/data-candidates")
def data_candidates_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    gate = _require_data_enabled()
    if gate:
        return gate

    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    if run.get("status") != "done":
        return jsonify({"ok": False, "error": f"la corrida no está done (status={run.get('status')})."}), 409

    dialect = run["engine"]
    src_snap = dbcompare_snapshot.latest_snapshot(run["source_alias"])
    candidates: list[dict] = []
    if src_snap is not None:
        for schema in sorted(src_snap.get("schemas", {})):
            tables = src_snap["schemas"][schema].get("tables", {})
            for tname in sorted(tables):
                table = tables[tname]
                pk_cols = table.get("primary_key", {}).get("columns") or []
                comparable = bool(pk_cols)
                candidates.append({
                    "schema": schema,
                    "table": tname,
                    "has_pk": comparable,
                    "estimated_columns": len(table.get("columns") or []),
                    "comparable": comparable,
                    "reason": "" if comparable else "la tabla no tiene PK en el snapshot de origen",
                    "row_count_source": _best_effort_row_count(run["source_alias"], schema, tname, dialect),
                    "row_count_target": _best_effort_row_count(run["target_alias"], schema, tname, dialect),
                })
    return jsonify({"ok": True, "candidates": candidates})


@bp.post("/runs/<run_id>/data-diff")
def start_data_diff_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    gate = _require_data_enabled()
    if gate:
        return gate

    body = request.get_json(silent=True) or {}
    tables = body.get("tables") or []
    if len(tables) > dbcompare_data._MAX_TABLES_PER_DATA_DIFF:
        return jsonify({
            "ok": False,
            "error": f"máximo {dbcompare_data._MAX_TABLES_PER_DATA_DIFF} tablas por corrida (recibidas {len(tables)}).",
        }), 400

    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    if run.get("status") != "done":
        return jsonify({"ok": False, "error": f"la corrida no está done (status={run.get('status')})."}), 409

    try:
        dbcompare_data.run_data_diff(run_id, tables)
    except dbcompare_data.DbCompareDataError as exc:
        # A esta altura ya se validó existencia/estado/tamaño arriba: lo único
        # que puede fallar es el lock de "ya hay un diff de datos activo".
        return jsonify({"ok": False, "error": str(exc)}), 409

    return jsonify({"ok": True}), 202
