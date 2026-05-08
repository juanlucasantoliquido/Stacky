"""
Endpoints agrupados de la tanda 3:
- FA-43 /api/coaching/tips
- FA-46 /api/best-practices/feed
- FA-22 /api/translate
- FA-23 /api/export
"""
from flask import Blueprint, abort, jsonify, request

from db import session_scope
from models import AgentExecution
from services import best_practices, coaching, exporter, translator

bp = Blueprint("extras", __name__, url_prefix="")


# ---------------- FA-43 ----------------

@bp.get("/coaching/tips")
def coaching_tips():
    user = request.args.get("user") or request.headers.get("X-User-Email") or "dev@local"
    days = request.args.get("days", default=30, type=int)
    tips = coaching.tips_for(user, lookback_days=days)
    return jsonify({"user": user, "tips": [t.to_dict() for t in tips]})


# ---------------- FA-46 ----------------

@bp.get("/best-practices/feed")
def best_practices_feed():
    days = request.args.get("days", default=7, type=int)
    return jsonify(best_practices.to_payload(days=days))


# ---------------- FA-22 ----------------

@bp.post("/translate")
def translate_route():
    payload = request.get_json(force=True, silent=True) or {}
    output = payload.get("output")
    target = (payload.get("target_lang") or "").lower()
    exec_id = payload.get("execution_id")
    if exec_id and not output:
        with session_scope() as session:
            row = session.get(AgentExecution, int(exec_id))
            if row is None:
                abort(404, "execution not found")
            output = row.output
    if not output:
        abort(400, "output (or execution_id) required")
    if not target:
        abort(400, "target_lang required (en|es|pt)")
    try:
        result = translator.translate(output=output, target_lang=target)
    except ValueError as e:
        abort(400, str(e))
    return jsonify(result.to_dict())


# ---------------- FA-23 ----------------

@bp.post("/export")
def export_route():
    payload = request.get_json(force=True, silent=True) or {}
    fmt = (payload.get("format") or "md").lower()
    exec_id = payload.get("execution_id")
    output = payload.get("output")
    agent_type = payload.get("agent_type") or "agent"
    if exec_id and not output:
        with session_scope() as session:
            row = session.get(AgentExecution, int(exec_id))
            if row is None:
                abort(404, "execution not found")
            output = row.output
            agent_type = row.agent_type
    if not output:
        abort(400, "output (or execution_id) required")
    try:
        result = exporter.export(
            output=output, fmt=fmt, agent_type=agent_type, exec_id=exec_id
        )
    except ValueError as e:
        abort(400, str(e))
    return jsonify(result.to_dict())
