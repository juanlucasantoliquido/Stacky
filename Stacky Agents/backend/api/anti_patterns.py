"""FA-11 — CRUD endpoints para anti-pattern registry."""
from flask import Blueprint, abort, jsonify, request

from services import anti_patterns
from ._helpers import current_user

bp = Blueprint("anti_patterns", __name__, url_prefix="/anti-patterns")


@bp.get("")
def list_route():
    active_only = request.args.get("active_only", "true").lower() != "false"
    return jsonify(anti_patterns.list_all(active_only=active_only))


@bp.post("")
def create_route():
    payload = request.get_json(force=True, silent=True) or {}
    pattern = payload.get("pattern")
    reason = payload.get("reason")
    if not pattern or not reason:
        abort(400, "pattern and reason are required")
    new_id = anti_patterns.create(
        pattern=pattern,
        reason=reason,
        agent_type=payload.get("agent_type"),
        project=payload.get("project"),
        example=payload.get("example"),
        created_by=current_user(),
    )
    return jsonify({"id": new_id}), 201


@bp.delete("/<int:ap_id>")
def deactivate_route(ap_id: int):
    if not anti_patterns.deactivate(ap_id):
        abort(404)
    return jsonify({"ok": True})
