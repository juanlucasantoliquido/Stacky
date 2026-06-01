"""
api/db_query.py — Endpoint server-side para ejecutar SELECTs read-only desde
los agentes técnicos. Plan §4.4 / §7.1.

Endpoints:
  POST /api/tickets/<ticket_id>/db/query
       body: { "sql": "SELECT ...", "row_limit"?: int, "timeout_s"?: int,
               "project"?: "RSPACIFICO" }
       → 200 { ok, would_execute, statement_kind, sanitized_query, dialect, ... }
       → 400 { ok:false, error } si el SQL no es SELECT puro o faltan credenciales

  GET  /api/tickets/<ticket_id>/db/audit?limit=50
       → { ok, events: [...] }

  GET  /api/db/audit?limit=100&project=RSPACIFICO
       → { ok, events: [...] } (vista global, para el panel de configuración)
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from project_manager import get_active_project, get_project_config
from services.db_query import (
    DbQueryError,
    execute_query,
    list_audit_events,
)

logger = logging.getLogger("stacky_agents.api.db_query")

bp = Blueprint("db_query", __name__, url_prefix="")


def _actor() -> str:
    return (request.headers.get("X-User-Email") or "operator").strip() or "operator"


def _resolve_project(payload: dict | None) -> str:
    if isinstance(payload, dict):
        project = (payload.get("project") or "").strip()
        if project:
            return project
    qs = (request.args.get("project") or "").strip()
    if qs:
        return qs
    active = get_active_project() or ""
    return active.strip()


@bp.post("/tickets/<string:ticket_id>/db/query")
def run_db_query(ticket_id: str):
    payload = request.get_json(force=True, silent=True) or {}
    sql = payload.get("sql") if isinstance(payload, dict) else None
    project = _resolve_project(payload)

    if not project:
        return jsonify({"ok": False, "error": "No hay proyecto activo y 'project' no fue indicado."}), 400
    if not get_project_config(project):
        return jsonify({"ok": False, "error": f"Proyecto '{project}' no encontrado"}), 404

    try:
        row_limit = int(payload.get("row_limit") or 1000)
    except Exception:
        row_limit = 1000
    try:
        timeout_s = int(payload.get("timeout_s") or 30)
    except Exception:
        timeout_s = 30

    try:
        result = execute_query(
            project=project,
            ticket_id=ticket_id,
            sql=sql or "",
            actor=_actor(),
            row_limit=row_limit,
            timeout_s=timeout_s,
        )
    except DbQueryError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error inesperado ejecutando db/query (project=%s, ticket=%s)", project, ticket_id)
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify(result)


@bp.get("/tickets/<string:ticket_id>/db/audit")
def list_ticket_db_audit(ticket_id: str):
    try:
        limit = int(request.args.get("limit") or 100)
    except Exception:
        limit = 100
    events = list_audit_events(ticket_id=ticket_id, limit=limit)
    return jsonify({"ok": True, "events": events})


@bp.get("/db/audit")
def list_global_db_audit():
    project = (request.args.get("project") or "").strip() or None
    try:
        limit = int(request.args.get("limit") or 100)
    except Exception:
        limit = 100
    events = list_audit_events(project=project, limit=limit)
    return jsonify({"ok": True, "events": events})
