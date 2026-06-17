from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from config import config
from services import pipeline_orchestrator

bp = Blueprint("pipelines", __name__, url_prefix="/pipelines")


def _ensure_enabled() -> None:
    if not bool(getattr(config, "STACKY_PIPELINES_ENABLED", False)):
        abort(404, "pipelines feature disabled")


@bp.post("")
def start_pipeline():
    _ensure_enabled()
    body = request.get_json(silent=True) or {}
    ticket_id = body.get("ticket_id")
    stages = body.get("stages")
    runtime = (body.get("runtime") or "github_copilot").strip() or "github_copilot"
    if not ticket_id:
        abort(400, "ticket_id is required")
    try:
        result = pipeline_orchestrator.start(
            ticket_id=int(ticket_id),
            stages=stages if isinstance(stages, list) else None,
            runtime=runtime,
        )
        return jsonify(result), 202
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        code = 409 if str(exc) == "pipeline_already_active" else 400
        return jsonify({"ok": False, "error": str(exc)}), code


@bp.get("/<int:pipeline_id>")
def get_pipeline(pipeline_id: int):
    _ensure_enabled()
    run = pipeline_orchestrator.get_run(pipeline_id)
    if run is None:
        abort(404)
    return jsonify({"ok": True, "pipeline": run})


@bp.post("/<int:pipeline_id>/cancel")
def cancel_pipeline(pipeline_id: int):
    _ensure_enabled()
    try:
        result = pipeline_orchestrator.cancel(pipeline_id)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.post("/<int:pipeline_id>/resume")
def resume_pipeline(pipeline_id: int):
    _ensure_enabled()
    body = request.get_json(silent=True) or {}
    runtime = (body.get("runtime") or "github_copilot").strip() or "github_copilot"
    try:
        result = pipeline_orchestrator.resume(pipeline_id, runtime=runtime)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
