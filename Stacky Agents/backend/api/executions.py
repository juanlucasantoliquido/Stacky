import json
import logging
from datetime import datetime
from pathlib import Path

from flask import Blueprint, Response, abort, jsonify, request
from sqlalchemy import and_, or_, select

import log_streamer
from db import session_scope
from models import AgentExecution, Ticket
from ._helpers import current_user
from services.project_context import resolve_project_context
from project_manager import (
    PROJECTS_DIR,
    get_project_config,
    get_active_project,
    find_project_for_tracker,
)

bp = Blueprint("executions", __name__, url_prefix="/executions")
logger = logging.getLogger("stacky_agents.api.executions")


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

    # Enrutar al runner correcto según el runtime de la ejecución.
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        runtime = (row.metadata_dict or {}).get("runtime")

    if runtime == "claude_code_cli":
        from services.claude_code_cli_runner import send_input
    else:
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
        result = row.to_dict(include_output=False)
    # Memoria colaborativa (Fase B) — al aprobar, promueve/crea la memoria ACTIVE
    # (best-effort, gated por STACKY_MEMORY_CAPTURE_ENABLED). Fuera de la sesión.
    if verdict == "approved":
        try:
            from services import post_run_memory

            post_run_memory.capture_on_approval(execution_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "post_run_memory.capture_on_approval falló exec=%s", execution_id, exc_info=True
            )
    return jsonify(result)


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


# ── Endpoints portados desde WS2 (2026-05-23) ────────────────────────────────


@bp.post("/<int:execution_id>/cancel")
def cancel_execution(execution_id: int):
    """Cancela una ejecucion en curso (vscode_chat o running).

    Marca el status como 'cancelled' y registra la fecha de finalizacion.
    No publica nada al tracker.

    Portado desde WS2 (2026-05-23) — P1.3 item (1).
    """
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        if row.status not in ("vscode_chat", "running"):
            abort(409, f"Cannot cancel execution in status '{row.status}'")
        row.status = "cancelled"
        row.completed_at = datetime.utcnow()
        meta = row.metadata_dict or {}
        runtime = meta.get("runtime")
        # B6: capturar ticket_id/agent_type dentro del session_scope para
        # sincronizar luego el stacky_status del ticket (hoy el endpoint lo omitía
        # y el ticket quedaba "running" hasta el próximo reconcile).
        ticket_id = row.ticket_id
        agent_type = row.agent_type

    if runtime == "codex_cli":
        from services import codex_cli_runner
        codex_cli_runner.cancel(execution_id)
    elif runtime == "claude_code_cli":
        from services import claude_code_cli_runner
        claude_code_cli_runner.cancel(execution_id)
    else:
        # B6: github_copilot (y cualquier runtime sin subproceso propio) no tiene
        # un proceso CLI que matar; la cancelación es cooperativa vía el flag
        # in-memory de copilot_bridge, expuesto por agent_runner.cancel().
        try:
            import agent_runner
            agent_runner.cancel(execution_id)
        except Exception:  # noqa: BLE001 — best-effort, no romper el cancel
            logger.warning("cancel cooperativo (agent_runner) falló exec=%s", execution_id, exc_info=True)

    # B6: sacar el ticket de "running" de inmediato (sin esperar al reaper). El
    # status ya quedó terminal en la execution row; reflejamos cancelled en el
    # ticket vía el hook de ciclo de vida (también dispara post-hooks coherentes).
    if ticket_id is not None:
        try:
            from services import ticket_status
            ticket_status.on_execution_end(
                ticket_id=ticket_id,
                execution_id=execution_id,
                final_status="cancelled",
                agent_type=agent_type,
                reason_override="cancelado manualmente desde el board",
            )
        except Exception:  # noqa: BLE001
            logger.warning("on_execution_end (cancel) falló exec=%s", execution_id, exc_info=True)

    logger.info("execution cancelled manually exec=%s", execution_id)
    return jsonify({"ok": True, "execution_id": execution_id})


@bp.delete("/<int:execution_id>")
def delete_execution(execution_id: int):
    """Elimina una ejecucion del historial.

    Solo se permite borrar ejecuciones terminadas (completed, error, cancelled,
    published, discarded). Las ejecuciones en curso se rechazan con 409.

    Portado desde WS2 (2026-05-23) — P1.3 item (2).
    """
    _TERMINAL_STATUSES = {"completed", "error", "cancelled", "published", "discarded", "failed"}
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        if row.status not in _TERMINAL_STATUSES:
            abort(409, f"cannot delete execution in status '{row.status}'")
        session.delete(row)
    return jsonify({"ok": True, "deleted_id": execution_id})


@bp.delete("/bulk-by-ticket")
def delete_executions_by_ticket():
    """Elimina todas las ejecuciones terminadas de un agente para un ticket dado.

    Query params:
      - ticket_id (int, required)
      - agent_filename (str, required)

    Las ejecuciones en curso se omiten (no se borran).

    Portado desde WS2 (2026-05-23) — P1.3 item (2).
    """
    ticket_id_raw = request.args.get("ticket_id")
    agent_filename = request.args.get("agent_filename", "").strip()
    if not ticket_id_raw or not agent_filename:
        abort(400, "ticket_id and agent_filename are required")
    try:
        ticket_id = int(ticket_id_raw)
    except ValueError:
        abort(400, "ticket_id must be an integer")

    _TERMINAL_STATUSES = {"completed", "error", "cancelled", "published", "discarded", "failed"}

    deleted_ids: list[int] = []
    skipped_ids: list[int] = []
    with session_scope() as session:
        rows = session.execute(
            select(AgentExecution).where(
                AgentExecution.ticket_id == ticket_id,
                AgentExecution.agent_filename == agent_filename,
            )
        ).scalars().all()
        for row in rows:
            if row.status not in _TERMINAL_STATUSES:
                skipped_ids.append(row.id)
                continue
            session.delete(row)
            deleted_ids.append(row.id)

    return jsonify({"ok": True, "deleted": deleted_ids, "skipped": skipped_ids})


@bp.post("/<int:execution_id>/answer")
def answer_question(execution_id: int):
    """Envia la respuesta del usuario a un agente en estado 'waiting_for_question'.

    Body: { "answer": "..." }
    Desbloquea el thread del agente para que continue la ejecucion.

    Portado desde WS2 (2026-05-23) — P1.3 item (3).
    """
    payload = request.get_json(force=True, silent=True) or {}
    answer = (payload.get("answer") or "").strip()

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        if row.status != "waiting_for_question":
            abort(409, f"execution no esta esperando respuesta (status='{row.status}')")

    import agent_runner as _runner
    if not hasattr(_runner, "answer_question"):
        # WS1 agent_runner no implementa answer_question todavia
        abort(501, "answer_question not implemented in this runtime")

    ok = _runner.answer_question(execution_id, answer)
    if not ok:
        abort(409, "no hay pregunta pendiente para esta ejecucion")

    return jsonify({"ok": True, "execution_id": execution_id})


def _resolve_ticket_output_dir_ws1(
    row: AgentExecution,
    ticket: Ticket,
) -> "Path | None":
    """Resuelve la carpeta donde el agente deposito sus ficheros generados.

    Adaptado para WS1: usa project_manager en vez de find_project_for_tracker de WS2.
    Prueba: metadata.ticket_output_dir -> Output/tickets/{ado_id}/.
    """
    meta = row.metadata_dict or {}
    output_dir_override = meta.get("ticket_output_dir")
    if output_dir_override:
        p = Path(output_dir_override)
        if p.is_dir():
            return p

    # Resolver workspace_root desde config del proyecto
    project_name = ticket.project or ""
    cfg = get_project_config(project_name) or {}
    workspace_root = (cfg.get("workspace_root") or "").strip()

    if not workspace_root:
        from project_manager import PROJECTS_DIR
        instance_file = PROJECTS_DIR / project_name / "vscode_instance.json"
        if instance_file.exists():
            try:
                inst = json.loads(instance_file.read_text(encoding="utf-8"))
                workspace_root = (inst.get("workspace_root") or "").strip()
            except Exception:
                pass

    if not workspace_root:
        return None

    ado_id = ticket.ado_id or 0
    output_base = Path(workspace_root) / "Output" / "tickets"

    # Convención primaria: {ado_id}
    candidate = output_base / str(ado_id)
    if candidate.is_dir():
        return candidate

    # Convención legada: azure_devops-{ado_id}
    candidate2 = output_base / f"azure_devops-{ado_id}"
    if candidate2.is_dir():
        return candidate2

    return None


@bp.get("/<int:execution_id>/output-files")
def list_output_files(execution_id: int):
    """Lista los ficheros generados por el agente en Output/tickets/{ado_id}/.

    Portado desde WS2 (2026-05-23) — P1.3 item (4).
    """
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        ticket = session.get(Ticket, row.ticket_id) if row.ticket_id else None
        if ticket is None:
            abort(404, "ticket not found for execution")
        ticket_dir = _resolve_ticket_output_dir_ws1(row, ticket)

    if ticket_dir is None:
        return jsonify({"files": [], "dir": None})

    files = []
    for f in sorted(ticket_dir.rglob("*")):
        if not f.is_file():
            continue
        stat = f.stat()
        files.append({
            "name": f.name,
            "rel_path": str(f.relative_to(ticket_dir)).replace("\\", "/"),
            "size": stat.st_size,
            "modified": int(stat.st_mtime * 1000),
        })

    return jsonify({"files": files, "dir": str(ticket_dir)})


@bp.delete("/<int:execution_id>/output-files")
def delete_output_files(execution_id: int):
    """Borra los ficheros seleccionados del directorio de salida del agente.

    Body: { "files": ["rel_path/to/file1.md", "file2.diff"] }
    Path traversal es rechazado explicitamente.

    Portado desde WS2 (2026-05-23) — P1.3 item (4).
    """
    payload = request.get_json(force=True, silent=True) or {}
    rel_paths: list[str] = payload.get("files") or []
    if not isinstance(rel_paths, list) or not rel_paths:
        abort(400, "files list required")

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        ticket = session.get(Ticket, row.ticket_id) if row.ticket_id else None
        if ticket is None:
            abort(404, "ticket not found for execution")
        ticket_dir = _resolve_ticket_output_dir_ws1(row, ticket)

    if ticket_dir is None:
        abort(404, "output directory not found")

    deleted = []
    errors = []
    for rel in rel_paths:
        try:
            target = (ticket_dir / rel).resolve()
            ticket_dir_resolved = ticket_dir.resolve()
            if not str(target).startswith(str(ticket_dir_resolved)):
                errors.append({"rel_path": rel, "error": "path traversal rejected"})
                continue
            if target.is_file():
                target.unlink()
                deleted.append(rel)
            else:
                errors.append({"rel_path": rel, "error": "not found"})
        except Exception as exc:  # noqa: BLE001
            errors.append({"rel_path": rel, "error": str(exc)})

    return jsonify({"deleted": deleted, "errors": errors})
