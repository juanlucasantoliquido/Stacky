"""api/db_compare.py — Plan 122 F4: núcleo del Comparador de BD entre ambientes
(serie 122-126). url_prefix="/db-compare" → rutas finales /api/db-compare/...

Gate estricto: TODOS los endpoints excepto /health devuelven 403 si
STACKY_DB_COMPARE_ENABLED está OFF (default). El password entra SOLO por
POST .../password (write-only), JAMÁS sale en respuestas ni logs.
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, current_app, jsonify, request

from services import dbcompare_engine, dbcompare_registry, dbcompare_runs, dbcompare_snapshot

bp = Blueprint("db_compare", __name__, url_prefix="/db-compare")


def _require_enabled():
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
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
