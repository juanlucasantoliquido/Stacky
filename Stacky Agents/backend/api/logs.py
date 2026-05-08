"""
System Logs REST API
====================

GET    /api/logs           — list system logs with filters + pagination
GET    /api/logs/<id>      — single log entry (full detail)
GET    /api/logs/export    — export as JSON or CSV (max 10 000 rows)
POST   /api/logs/frontend  — ingest a JS error / event from the browser
DELETE /api/logs/purge     — delete logs older than N days
GET    /api/logs/stats     — aggregated counts by level and source
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from flask import Blueprint, Response, abort, jsonify, request
from sqlalchemy import func, or_

from db import session_scope
from models import SystemLog
from services.stacky_logger import RETENTION_DAYS, logger as stacky_logger

bp = Blueprint("logs", __name__, url_prefix="/logs")

_VALID_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


# ── helpers ────────────────────────────────────────────────────────────────

def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_query(session, args):
    """Apply URL query params as filters on SystemLog."""
    q = session.query(SystemLog)

    level = (args.get("level") or "").upper()
    if level and level in _VALID_LEVELS:
        q = q.filter(SystemLog.level == level)

    source = args.get("source") or None
    if source:
        q = q.filter(SystemLog.source.contains(source))

    action = args.get("action") or None
    if action:
        q = q.filter(SystemLog.action.contains(action))

    execution_id = args.get("execution_id", type=int)
    if execution_id is not None:
        q = q.filter(SystemLog.execution_id == execution_id)

    ticket_id = args.get("ticket_id", type=int)
    if ticket_id is not None:
        q = q.filter(SystemLog.ticket_id == ticket_id)

    user = args.get("user") or None
    if user:
        q = q.filter(SystemLog.user.contains(user))

    request_id = args.get("request_id") or None
    if request_id:
        q = q.filter(SystemLog.request_id == request_id)

    from_dt = _parse_iso(args.get("from"))
    if from_dt:
        q = q.filter(SystemLog.timestamp >= from_dt)

    to_dt = _parse_iso(args.get("to"))
    if to_dt:
        q = q.filter(SystemLog.timestamp <= to_dt)

    # Full-text search across action, source, input, output, error
    search = args.get("q") or None
    if search:
        q = q.filter(or_(
            SystemLog.action.contains(search),
            SystemLog.source.contains(search),
            SystemLog.input_json.contains(search),
            SystemLog.output_json.contains(search),
            SystemLog.error_json.contains(search),
            SystemLog.context_json.contains(search),
        ))

    return q


# ── endpoints ──────────────────────────────────────────────────────────────

@bp.get("")
def list_logs():
    """
    List system logs with optional filters.

    Query params:
      level, source, action, execution_id, ticket_id, user,
      request_id, from (ISO date), to (ISO date), q (full-text),
      limit (max 1000, default 100), offset (default 0)
    """
    limit = min(request.args.get("limit", default=100, type=int), 1000)
    offset = max(request.args.get("offset", default=0, type=int), 0)

    with session_scope() as session:
        q = _build_query(session, request.args)
        total = q.count()
        rows = (
            q.order_by(SystemLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return jsonify({
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": [r.to_dict() for r in rows],
        })


@bp.get("/stats")
def log_stats():
    """Return aggregated counts by level and by source (top 20)."""
    with session_scope() as session:
        by_level = (
            session.query(SystemLog.level, func.count(SystemLog.id))
            .group_by(SystemLog.level)
            .all()
        )
        by_source = (
            session.query(SystemLog.source, func.count(SystemLog.id))
            .group_by(SystemLog.source)
            .order_by(func.count(SystemLog.id).desc())
            .limit(20)
            .all()
        )
        total = session.query(func.count(SystemLog.id)).scalar() or 0
        return jsonify({
            "total": total,
            "by_level": {level: count for level, count in by_level},
            "by_source": [{"source": s, "count": c} for s, c in by_source],
        })


@bp.get("/export")
def export_logs():
    """
    Export system logs as JSON or CSV.

    Query params: format (json|csv), limit (max 10 000), level, source
    """
    fmt = (request.args.get("format") or "json").lower()
    limit = min(request.args.get("limit", default=5_000, type=int), 10_000)

    with session_scope() as session:
        q = _build_query(session, request.args)
        rows = q.order_by(SystemLog.timestamp.desc()).limit(limit).all()

    if fmt == "csv":
        fields = [
            "id", "timestamp", "level", "source", "action",
            "execution_id", "ticket_id", "user", "request_id",
            "method", "endpoint", "status_code", "duration_ms",
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            d = r.to_dict()
            writer.writerow({f: d.get(f) for f in fields})
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=stacky_system_logs.csv"},
        )

    return Response(
        json.dumps([r.to_dict() for r in rows], ensure_ascii=False, default=str),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=stacky_system_logs.json"},
    )


@bp.get("/<int:log_id>")
def get_log(log_id: int):
    """Fetch a single system log entry by ID (full detail including payloads)."""
    with session_scope() as session:
        row = session.get(SystemLog, log_id)
        if row is None:
            abort(404)
        return jsonify(row.to_dict())


@bp.post("/frontend")
def ingest_frontend_event():
    """
    Receive a structured log event from the browser / frontend.

    Expected JSON body:
    {
        "level":   "ERROR" | "WARNING" | "INFO",
        "source":  "component.MyComponent",
        "action":  "unhandled_error",
        "message": "Cannot read property ...",
        "stack":   "Error: ...\n  at ...",
        "url":     "http://localhost:5173/tickets",
        "context": { ...arbitrary extra data... }
    }
    """
    body = request.get_json(silent=True) or {}
    level = (str(body.get("level") or "ERROR")).upper()
    if level not in _VALID_LEVELS:
        level = "ERROR"

    source = f"frontend.{str(body.get('source') or 'unknown')}"
    action = str(body.get("action") or "frontend_event")
    user = request.headers.get("X-User-Email") or body.get("user") or "unknown"

    context_data: dict = {
        k: body[k]
        for k in ("message", "stack", "url")
        if body.get(k) is not None
    }
    if body.get("context"):
        context_data["extra"] = body["context"]

    stacky_logger._emit(
        level,
        source,
        action,
        user=user,
        context_data=context_data,
        tags=["frontend"],
    )
    return jsonify({"ok": True})


@bp.delete("/purge")
def purge_logs():
    """
    Delete system logs older than N days.

    Query param: days (default: SYSLOG_RETENTION_DAYS env var, fallback 90)
    """
    days = request.args.get("days", default=RETENTION_DAYS, type=int)
    if days < 1:
        return jsonify({"error": "days must be >= 1"}), 400
    deleted = stacky_logger.purge_old_logs(days=days)
    return jsonify({"deleted": deleted, "older_than_days": days})
