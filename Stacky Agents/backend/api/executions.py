import json
import logging
from datetime import datetime

from flask import Blueprint, Response, abort, jsonify, request

import log_streamer
from db import session_scope
from models import AgentExecution

logger = logging.getLogger("stacky_agents.executions")

bp = Blueprint("executions", __name__, url_prefix="/executions")


@bp.get("")
def list_executions():
    ticket_id = request.args.get("ticket_id", type=int)
    agent_type = request.args.get("agent_type")
    status = request.args.get("status")
    limit = request.args.get("limit", default=50, type=int)

    with session_scope() as session:
        q = session.query(AgentExecution)
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
    """Publica el output de una ejecución como comentario en el work item ADO.

    Guarda el comment_id en metadata para habilitar rollback posterior.
    Si el ADO client no está configurado, devuelve un resultado stubbed para desarrollo.
    """
    target = (request.get_json(silent=True) or {}).get("target", "comment")
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404)
        if not row.output:
            abort(400, "execution has no output to publish")

        # Obtener el ado_id del ticket
        ticket = row.ticket
        if ticket is None:
            abort(404, "ticket not found")
        ado_id = ticket.ado_id

        try:
            from services.ado_client import AdoClient, AdoConfigError, AdoApiError

            client = AdoClient()
            # ADO acepta HTML en comentarios; envolvemos el markdown en <pre> si no tiene tags HTML
            output_text = row.output or ""
            if "<" not in output_text:
                body_html = "<pre>" + output_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>"
            else:
                body_html = output_text
            result = client.publish_comment(ado_id, body_html)

            # Persistir en metadata para habilitar rollback
            meta = row.metadata_dict
            meta["ado_comment_id"] = result["comment_id"]
            meta["ado_published_at"] = datetime.utcnow().isoformat()
            meta["ado_published_target"] = target
            row.metadata_dict = meta

            logger.info(
                "exec #%s publicada en ADO-%s (comment_id=%s)",
                execution_id, ado_id, result["comment_id"],
            )
            return jsonify({
                "ok": True,
                "stubbed": False,
                "target": target,
                "ado_url": result["ado_url"],
                "comment_id": result["comment_id"],
                "published_at": meta["ado_published_at"],
            })

        except (AdoConfigError, AdoApiError) as e:
            # En desarrollo / sin PAT configurado: modo stubbed
            logger.warning("publish_to_ado stubbed: %s", e)
            meta = row.metadata_dict
            meta["ado_published_at"] = datetime.utcnow().isoformat()
            meta["ado_published_target"] = target
            meta["ado_stub"] = True
            row.metadata_dict = meta
            return jsonify({
                "ok": True,
                "stubbed": True,
                "target": target,
                "ado_url": f"https://dev.azure.com/.../_workitems/edit/{ado_id}",
                "published_at": meta["ado_published_at"],
            })
        except ImportError:
            # Fallback si el módulo no está disponible
            return jsonify({
                "ok": True,
                "stubbed": True,
                "target": target,
                "ado_url": f"https://dev.azure.com/.../_workitems/edit/{ado_id}",
                "published_at": datetime.utcnow().isoformat(),
            })


@bp.post("/<int:execution_id>/rollback-ado")
def rollback_ado(execution_id: int):
    """Elimina el comentario publicado en ADO para esta ejecución.

    Requiere que la ejecución haya sido publicada previamente (metadata.ado_comment_id).
    Marca metadata.ado_rollback_at para trazabilidad.
    """
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404)

        meta = row.metadata_dict
        if not meta.get("ado_published_at"):
            abort(409, "execution was not published to ADO")

        # Si fue publicado en modo stub no hay nada real que borrar
        if meta.get("ado_stub"):
            meta["ado_rollback_at"] = datetime.utcnow().isoformat()
            meta["ado_rollback_stub"] = True
            row.metadata_dict = meta
            return jsonify({"ok": True, "stubbed": True})

        comment_id = meta.get("ado_comment_id")
        if not comment_id:
            abort(409, "ado_comment_id not found in metadata; cannot rollback")

        ticket = row.ticket
        if ticket is None:
            abort(404, "ticket not found")
        ado_id = ticket.ado_id

        try:
            from services.ado_client import AdoClient, AdoApiError

            client = AdoClient()
            client.delete_comment(ado_id, comment_id)

            meta["ado_rollback_at"] = datetime.utcnow().isoformat()
            row.metadata_dict = meta

            logger.info(
                "exec #%s: rollback ADO-%s comment_id=%s OK",
                execution_id, ado_id, comment_id,
            )
            return jsonify({
                "ok": True,
                "stubbed": False,
                "rolled_back_comment_id": comment_id,
                "rolled_back_at": meta["ado_rollback_at"],
            })

        except Exception as e:
            logger.error("rollback_ado exec #%s error: %s", execution_id, e)
            abort(502, f"Error al eliminar comentario de ADO: {e}")


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
