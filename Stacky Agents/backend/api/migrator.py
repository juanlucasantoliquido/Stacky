"""Plan 74 F6 — Blueprint Migrador ADO→GitLab (HITL, dry-run obligatorio).

Endpoints:
  POST /api/migrator/plan              — dry-run: genera plan SIN escribir.
  POST /api/migrator/execute           — ejecuta el plan (confirmed=true obligatorio).
  GET  /api/migrator/health            — estado del flag (503 si OFF).
  GET  /api/migrator/<project>/mapping — mapeo ado_id↔gitlab_iid (JSON o CSV).
  GET  /api/migrator/<project>/runs    — historial de corridas.

Blueprint registrado en api/__init__.py con url_prefix="/migrator" sobre api_bp
(url_prefix="/api") → rutas finales /api/migrator/... (C1, sin doble prefijo).

Flag STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED: default OFF, env_only=False (UI).
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

import config as _config
from flask import Blueprint, abort, jsonify, request, make_response

# Blueprint con url_prefix="/migrator" → registrado en api_bp (url_prefix="/api") → /api/migrator/...
# NUNCA url_prefix="/api/migrator" (daría /api/api/migrator, doble prefijo, C1).
bp = Blueprint("migrator", __name__, url_prefix="/migrator")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _flag_enabled() -> bool:
    return getattr(_config.config, "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED", False)


def _get_db() -> sqlite3.Connection:
    """Abre la DB SQLite viva. Igual que ado_edit_ledger."""
    from runtime_paths import data_dir
    db_path = str(data_dir() / "stacky_agents.db")
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    return db


def _compute_plan_hash(plan) -> str:
    """Hash determinista del plan (ado_ids + counts)."""
    import hashlib
    sorted_ids = sorted(
        op.ado_id for op in plan.ops if op.op_kind == "create_item"
    )
    payload = json.dumps({"ids": sorted_ids, "counts": plan.counts_by_type}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_providers(stacky_project: str):
    """Obtiene (origin_provider, dest_provider) para el proyecto.
    origin = ADO, dest = GitLab (el migrador siempre va ADO→GitLab).
    Usa get_tracker_provider con type override para cada dirección.
    """
    from services.tracker_provider import get_tracker_provider, TrackerConfigError
    try:
        origin = get_tracker_provider(stacky_project)
        dest = get_tracker_provider(stacky_project)
    except TrackerConfigError as e:
        abort(503, description=str(e))
    return origin, dest


def _get_ado_pat(stacky_project: str) -> str:
    """Obtiene el PAT ADO del client_profile del proyecto."""
    try:
        from services.project_context import resolve_project_context
        ctx = resolve_project_context(project_name=stacky_project)
        return getattr(ctx, "ado_pat", "") or ""
    except Exception:
        return ""


# ── Endpoints ────────────────────────────────────────────────────────────────

@bp.get("/health")
def migrator_health():
    """GET /api/migrator/health — 200 si flag ON, 503 si OFF."""
    if not _flag_enabled():
        return jsonify({"ok": False, "reason": "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=false"}), 503
    return jsonify({"ok": True})


@bp.post("/plan")
def migrator_plan():
    """POST /api/migrator/plan — dry-run: genera plan SIN escribir.

    body: {stacky_project, items_filter?, epic_policy?}
    → {plan_id, counts_by_type, warnings, ops_preview (max 50), total_ops}
    Requiere STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=true (sino 503).
    """
    if not _flag_enabled():
        return jsonify({"error": "Migrador no habilitado (STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=false)"}), 503

    data = request.get_json(force=True) or {}
    stacky_project = data.get("stacky_project") or ""
    if not stacky_project:
        return jsonify({"error": "stacky_project requerido"}), 400

    origin, dest = _get_providers(stacky_project)

    from services.migrator_core import plan_migration
    from services.migrator_executor import hydrate_map_from_destination

    db = _get_db()
    try:
        from services.migrator_map import ensure_map_schema
        ensure_map_schema(db)
        existing_map = hydrate_map_from_destination(dest, db, stacky_project=stacky_project)
        plan = plan_migration(origin, dest, stacky_project=stacky_project, existing_map=existing_map)

        plan_id = str(uuid.uuid4())
        plan_hash = _compute_plan_hash(plan)
        now = datetime.now(timezone.utc).isoformat()

        from services.migrator_map import save_plan_snapshot
        save_plan_snapshot(
            db,
            plan_id=plan_id,
            stacky_project=stacky_project,
            counts_json=json.dumps(plan.counts_by_type),
            plan_hash=plan_hash,
            created_at=now,
        )

        ops_preview = [
            {
                "op_kind": op.op_kind,
                "ado_id": op.ado_id,
                "ado_type": op.ado_type,
                "dest_parent_ado_id": op.dest_parent_ado_id,
            }
            for op in plan.ops[:50]
        ]

        return jsonify({
            "plan_id": plan_id,
            "counts_by_type": plan.counts_by_type,
            "warnings": plan.warnings,
            "ops_preview": ops_preview,
            "total_ops": len(plan.ops),
        })
    finally:
        db.close()


@bp.post("/execute")
def migrator_execute():
    """POST /api/migrator/execute — ejecuta el plan (HITL: confirmed=true obligatorio).

    body: {plan_id, confirmed: true}
    → {applied, skipped, failed, orphaned, migration_run}
    """
    if not _flag_enabled():
        return jsonify({"error": "Migrador no habilitado"}), 503

    data = request.get_json(force=True) or {}
    if not data.get("confirmed"):
        return jsonify({"error": "confirmed=true requerido (HITL gate)"}), 400

    plan_id = data.get("plan_id") or ""
    if not plan_id:
        return jsonify({"error": "plan_id requerido"}), 400

    db = _get_db()
    try:
        from services.migrator_map import ensure_map_schema, get_plan_snapshot
        ensure_map_schema(db)

        snapshot = get_plan_snapshot(db, plan_id)
        if not snapshot:
            return jsonify({"error": f"plan_id {plan_id!r} no encontrado"}), 404

        stacky_project = snapshot["stacky_project"]
        origin, dest = _get_providers(stacky_project)

        from services.migrator_core import plan_migration
        from services.migrator_executor import execute_migration, hydrate_map_from_destination

        # Rehidratar desde destino (C4 — idempotencia ante DB vacía)
        existing_map = hydrate_map_from_destination(dest, db, stacky_project=stacky_project)

        # Re-correr plan y detectar drift (C5)
        current_plan = plan_migration(origin, dest, stacky_project=stacky_project, existing_map=existing_map)
        current_hash = _compute_plan_hash(current_plan)
        if current_hash != snapshot["plan_hash"]:
            return jsonify({
                "error": "El origen cambió desde el dry-run. Re-corré el plan antes de ejecutar.",
                "plan_id": plan_id,
            }), 409

        migration_run = str(uuid.uuid4())
        result = execute_migration(
            current_plan, dest, db,
            stacky_project=stacky_project,
            migration_run=migration_run,
            existing_map=existing_map,
        )

        return jsonify({
            "applied": result.applied,
            "skipped": result.skipped,
            "failed": result.failed,
            "orphaned": result.orphaned,
            "migration_run": migration_run,
        })
    finally:
        db.close()


@bp.get("/<stacky_project>/mapping")
def migrator_mapping(stacky_project: str):
    """GET /api/migrator/<project>/mapping — mapeo ado_id↔gitlab_iid.

    Accept: text/csv → CSV descargable.
    Default → JSON.
    """
    if not _flag_enabled():
        return jsonify({"error": "Migrador no habilitado"}), 503

    db = _get_db()
    try:
        from services.migrator_map import ensure_map_schema, get_full_mapping
        ensure_map_schema(db)
        rows = get_full_mapping(db, stacky_project)

        accept = request.headers.get("Accept", "")
        if "text/csv" in accept:
            out = io.StringIO()
            fieldnames = ["stacky_project", "ado_id", "ado_type", "gitlab_iid",
                          "gitlab_web_url", "marker", "migrated_at", "migration_run"]
            writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            resp = make_response(out.getvalue())
            resp.headers["Content-Type"] = "text/csv"
            resp.headers["Content-Disposition"] = (
                f'attachment; filename="migrator_mapping_{stacky_project}.csv"'
            )
            return resp

        return jsonify({"stacky_project": stacky_project, "mapping": rows, "total": len(rows)})
    finally:
        db.close()


@bp.get("/<stacky_project>/runs")
def migrator_runs(stacky_project: str):
    """GET /api/migrator/<project>/runs — historial de corridas."""
    if not _flag_enabled():
        return jsonify({"error": "Migrador no habilitado"}), 503

    db = _get_db()
    try:
        from services.migrator_map import ensure_map_schema
        ensure_map_schema(db)

        rows = db.execute(
            """
            SELECT migration_run, max(migrated_at) as ts,
                   count(*) as item_count
            FROM migrator_ado_gitlab_map
            WHERE stacky_project=?
            GROUP BY migration_run
            ORDER BY ts DESC
            """,
            (stacky_project,),
        ).fetchall()

        return jsonify({
            "stacky_project": stacky_project,
            "runs": [dict(r) for r in rows],
        })
    finally:
        db.close()
