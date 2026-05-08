"""FA-52 — CRUD endpoints para webhooks."""
from flask import Blueprint, abort, jsonify, request

from services import webhooks

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


@bp.get("")
def list_route():
    return jsonify(webhooks.list_all())


@bp.post("")
def create_route():
    payload = request.get_json(force=True, silent=True) or {}
    url = payload.get("url")
    event = payload.get("event", "exec.completed")
    if not url:
        abort(400, "url is required")
    new_id = webhooks.create(
        url=url,
        event=event,
        project=payload.get("project"),
        secret=payload.get("secret"),
    )
    return jsonify({"id": new_id}), 201


@bp.delete("/<int:wh_id>")
def deactivate_route(wh_id: int):
    if not webhooks.deactivate(wh_id):
        abort(404)
    return jsonify({"ok": True})


@bp.post("/test/<int:wh_id>")
def test_route(wh_id: int):
    """Manda un payload de test al webhook."""
    fired = webhooks.fire(
        "exec.completed",
        {"event": "exec.completed", "test": True, "from": "stacky-agents"},
    )
    return jsonify({"fired": fired})
