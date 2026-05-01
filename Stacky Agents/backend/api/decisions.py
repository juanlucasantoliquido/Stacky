"""FA-13 — CRUD endpoints para historical decisions."""
from flask import Blueprint, abort, jsonify, request

from services import decisions
from ._helpers import current_user

bp = Blueprint("decisions", __name__, url_prefix="/decisions")


@bp.get("")
def list_route():
    active_only = request.args.get("active_only", "true").lower() != "false"
    return jsonify(decisions.list_all(active_only=active_only))


@bp.post("")
def create_route():
    payload = request.get_json(force=True, silent=True) or {}
    summary = payload.get("summary")
    reasoning = payload.get("reasoning")
    if not summary or not reasoning:
        abort(400, "summary and reasoning are required")
    new_id = decisions.create(
        summary=summary,
        reasoning=reasoning,
        tags=payload.get("tags") or [],
        project=payload.get("project"),
        supersedes_id=payload.get("supersedes_id"),
        made_by=current_user(),
    )
    return jsonify({"id": new_id}), 201


@bp.delete("/<int:decision_id>")
def deactivate_route(decision_id: int):
    if not decisions.deactivate(decision_id):
        abort(404)
    return jsonify({"ok": True})
