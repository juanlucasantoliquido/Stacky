import json
from datetime import datetime

from flask import Blueprint, Response, abort, jsonify, request
from sqlalchemy import and_, or_

import log_streamer
from db import session_scope
from models import AgentExecution, Ticket
from ._helpers import current_user
from services.project_context import resolve_project_context

bp = Blueprint("executions", __name__, url_prefix="/executions")


@bp.get("")
def list_executions():
    ticket_id = request.args.get("ticket_id", type=int)
    agent_type = request.args.get("agent_type")
    status = request.args.get("status")
    project_name = (request.args.get("project") or "").strip() or None
    limit = request.args.get("limit", default=50, type=int)

    project_ctx = resolve_project_context(project_name=project_name) if project_name else resolve_project_context()

    with session_scope() as session:
        q = session.query(AgentExecution)
        if project_ctx is not None:
            q = q.join(Ticket, Ticket.id == AgentExecution.ticket_id).filter(
                or_(
                    Ticket.stacky_project_name == project_ctx.stacky_project_name,
                    and_(
                        Ticket.stacky_project_name.is_(None),
                        Ticket.project == project_ctx.tracker_project,
                    ),
                )
            )
        if ticket_id:
            q = q.filter(AgentExecution.ticket_id == ticket_id)
        if agent_type:
            q = q.filter(AgentExecution.agent_type == agent_type)
        if status:
            q = q.filter(AgentExecution.status == status)
        rows = q.order_by(AgentExecution.started_at.desc()).limit(limit).all()
        return jsonify([r.to_dict(include_output=False) for r in rows])


@bp.get("/<int:execution_id>")
def get_execution(execution_id: int):
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404)
        return jsonify(row.to_dict())


@bp.get("/<int:execution_id>/logs")
def get_logs(execution_id: int):
    return jsonify(log_streamer.snapshot(execution_id))


@bp.post("/<int:execution_id>/input")
def send_execution_input(execution_id: int):
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "").strip()
    if not text:
        abort(400, "text is required")

    from services.codex_cli_runner import send_input

    try:
        result = send_input(execution_id, text, user=current_user())
    except ValueError as exc:
        abort(400, str(exc))
    except RuntimeError as exc:
        abort(409, str(exc))

    return jsonify(result)


@bp.get("/<int:execution_id>/logs/stream")
def stream_logs(execution_id: int):
    def generator():
        for event in log_streamer.stream(execution_id):
            event_type = event.get("type") or "log"
            data = json.dumps(event, ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"

    return Response(
        generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@bp.post("/<int:execution_id>/approve")
def approve(execution_id: int):
    return _set_verdict(execution_id, verdict="approved")


@bp.post("/<int:execution_id>/discard")
def discard(execution_id: int):
    return _set_verdict(execution_id, verdict="discarded")


def _set_verdict(execution_id: int, verdict: str):
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404)
        if row.status != "completed":
            abort(409, "execution not in completed state")
        row.verdict = verdict
        return jsonify(row.to_dict(include_output=False))


@bp.post("/<int:execution_id>/publish-to-ado")
def publish_to_ado(execution_id: int):
    """Stub. En Fase 1 delegamos a `Tools/Stacky/ado_attachment_manager` & co."""
    target = (request.get_json(silent=True) or {}).get("target", "comment")
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404)
        # TODO Fase 1: llamar al ADO real.
        return jsonify(
            {
                "ok": True,
                "stubbed": True,
                "target": target,
                "ado_url": f"https://dev.azure.com/.../_workitems/edit/{row.ticket_id}",
                "published_at": datetime.utcnow().isoformat(),
            }
        )


@bp.get("/<int:execution_id>/diff/<int:other_id>")
def diff(execution_id: int, other_id: int):
    with session_scope() as session:
        a = session.get(AgentExecution, execution_id)
        b = session.get(AgentExecution, other_id)
        if a is None or b is None:
            abort(404)
        if a.ticket_id != b.ticket_id or a.agent_type != b.agent_type:
            abort(400, "executions must share ticket_id and agent_type")
        return jsonify({"left": a.to_dict(), "right": b.to_dict()})
