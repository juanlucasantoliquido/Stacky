import json
import logging
import os
import uuid as _uuid_mod
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

import fingerprint
from db import session_scope
from models import AgentExecution, SystemLog, Ticket
from services import glossary
from services.ado_sync import (
    AdoApiError,
    AdoConfigError,
    get_last_sync_at,
    sync_tickets,
)
from services.pipeline_status import get_pipeline_status, get_pipeline_summary
from services.ado_pipeline_inference import infer_pipeline, invalidate_cache
from services.ado_client import AdoClient, AdoApiError as _AdoApiError, AdoConfigError as _AdoConfigError

logger = logging.getLogger("stacky_agents.api.tickets")

bp = Blueprint("tickets", __name__, url_prefix="/tickets")

# ── Fase 2: constantes para create_child_task ─────────────────────────────────

# Campos obligatorios en pending-task.json para que Stacky pueda procesarlo
_PENDING_TASK_REQUIRED_FIELDS = {
    "generated_at", "generated_by", "epic_id", "rf_id",
    "title", "description_html", "plan_de_pruebas_path",
    "parent_link_type", "status",
}

# Resuelve el root del repo (honra STACKY_REPO_ROOT para tests)
def _repo_root() -> Path:
    env = os.getenv("STACKY_REPO_ROOT")
    if env:
        return Path(env).resolve()
    # api/tickets.py → api/ → backend/ → Stacky Agents/ → Stacky/ → Tools/ → <repo>
    return Path(__file__).resolve().parents[5]

# Exportado como módulo-level para que los tests puedan patchearlo
REPO_ROOT: Path = _repo_root()


def _resolve_repo_root() -> Path:
    """Permite que los tests puedan sobreescribir REPO_ROOT vía patch."""
    return REPO_ROOT


def _check_finish_manifest_gate(execution_id: int | None) -> dict | None:
    """Lee MANIFEST.json para una execution_id y retorna un resumen.

    Retorna None si no hay execution o el manifest no existe / es inválido.
    Caso contrario:
      { "exists": True, "status": "...", "work_completed": bool,
        "written_at": str|None, "execution_id": int }
    """
    if execution_id is None:
        return None
    from services.manifest_watcher import MANIFEST_FILENAME, default_runs_dir

    path = default_runs_dir() / str(execution_id) / MANIFEST_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    signals = data.get("signals") or {}
    return {
        "exists": True,
        "execution_id": execution_id,
        "status": data.get("status"),
        "work_completed": bool(signals.get("work_completed", False)),
        "written_at": data.get("written_at"),
    }


@bp.get("/hierarchy")
def get_hierarchy():
    """Devuelve todos los tickets organizados en jerarquía Epic → hijos.

    Response:
      {
        "epics": [ { ...ticket, "children": [ {...ticket}, ... ] } ],
        "orphans": [ {...ticket} ]    // tickets sin parent o cuyo parent no está en BD
      }

    Incluye pipeline_summary (solo BD local, sin LLM) para cada ticket.
    """
    project = request.args.get("project")
    with session_scope() as session:
        q = session.query(Ticket)
        if project:
            q = q.filter(Ticket.project == project)
        all_tickets = q.order_by(Ticket.ado_id).all()

        ado_id_to_ticket: dict[int, dict] = {}
        for t in all_tickets:
            d = t.to_dict()
            d["pipeline_summary"] = get_pipeline_summary(t.id)
            d["children"] = []
            ado_id_to_ticket[t.ado_id] = d

        epics: list[dict] = []
        orphans: list[dict] = []

        for t in all_tickets:
            d = ado_id_to_ticket[t.ado_id]
            wi_type = (t.work_item_type or "").lower()

            if wi_type == "epic":
                epics.append(d)
            elif t.parent_ado_id and t.parent_ado_id in ado_id_to_ticket:
                # tiene parent en BD → agregar como hijo
                ado_id_to_ticket[t.parent_ado_id]["children"].append(d)
            else:
                orphans.append(d)

        return jsonify({"epics": epics, "orphans": orphans})


@bp.get("")
def list_tickets():
    project = request.args.get("project")
    search = request.args.get("search", "").strip().lower()
    with session_scope() as session:
        q = session.query(Ticket)
        if project:
            q = q.filter(Ticket.project == project)
        rows = q.order_by(Ticket.last_synced_at.desc().nulls_last(), Ticket.id.desc()).limit(500).all()
        out = []
        for t in rows:
            if search and search not in (t.title or "").lower() and search not in str(t.ado_id):
                continue
            d = t.to_dict()
            last = (
                session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == t.id)
                .order_by(AgentExecution.started_at.desc())
                .first()
            )
            d["last_execution"] = last.to_dict(include_output=False) if last else None
            d["pipeline_summary"] = get_pipeline_summary(t.id)
            out.append(d)
        return jsonify(out)


@bp.post("/sync")
def sync_from_ado():
    """Trae los work items abiertos desde Azure DevOps y actualiza la BD local."""
    try:
        result = sync_tickets()
    except AdoConfigError as e:
        logger.warning("ADO sync — config: %s", e)
        return jsonify({"ok": False, "error": "config", "message": str(e)}), 400
    except AdoApiError as e:
        logger.warning("ADO sync — api: %s", e)
        return jsonify({"ok": False, "error": "ado_api", "message": str(e)}), 502
    except Exception as e:
        logger.exception("ADO sync — fallo inesperado")
        return jsonify({"ok": False, "error": "unexpected", "message": str(e)}), 500
    return jsonify({"ok": True, **result})


@bp.get("/sync/status")
def sync_status():
    last = get_last_sync_at()
    return jsonify({"last_synced_at": last.isoformat() if last else None})


@bp.get("/<int:ticket_id>")
def get_ticket(ticket_id: int):
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        d = t.to_dict()
        execs = (
            session.query(AgentExecution)
            .filter(AgentExecution.ticket_id == ticket_id)
            .order_by(AgentExecution.started_at.desc())
            .limit(50)
            .all()
        )
        d["executions"] = [e.to_dict(include_output=False) for e in execs]
        return jsonify(d)


@bp.get("/<int:ticket_id>/pipeline-status")
def get_pipeline_status_endpoint(ticket_id: int):
    """Infiere qué etapas del pipeline (business, functional, technical, developer, qa)
    ya fueron ejecutadas para este ticket.

    Query params:
      include_ado_comments=true  — también escanea comentarios del work item en ADO
                                   (requiere una llamada extra a la API de ADO).
    """
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id

    ado_comments = None
    if request.args.get("include_ado_comments", "").lower() in ("1", "true", "yes"):
        try:
            from services.ado_client import AdoClient
            client = AdoClient()
            ado_comments = client.fetch_comments(ado_id, top=30)
        except Exception as e:
            logger.warning("pipeline-status: no se pudo leer comentarios ADO para %s: %s", ado_id, e)

    status = get_pipeline_status(ticket_id, ado_comments=ado_comments)
    return jsonify(status.to_dict())


@bp.get("/<int:ticket_id>/ado-pipeline-status")
def get_ado_pipeline_status(ticket_id: int):
    """Infiere el estado del pipeline usando ÚNICAMENTE datos de ADO + LLM.

    No depende de archivos locales. Reproducible en cualquier máquina.
    Cachea resultado 60 min por defecto.

    Query params:
      force_refresh=true  — ignora cache y re-llama al LLM
      model=gpt-4o-mini   — modelo LLM a usar (default: gpt-4o-mini)
    """
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id

    force = request.args.get("force_refresh", "").lower() in ("1", "true", "yes")
    model = request.args.get("model") or None

    try:
        result = infer_pipeline(ado_id=ado_id, force_refresh=force, model=model)
        return jsonify(result.to_dict())
    except Exception as e:
        logger.exception("ado-pipeline-status falló para ticket %s (ADO-%s)", ticket_id, ado_id)
        return jsonify({"error": str(e)}), 500


@bp.post("/ado-pipeline-batch")
def ado_pipeline_batch():
    """Infiere el pipeline para múltiples tickets en un solo request.

    Body: { "ticket_ids": [1, 2, 3], "force_refresh": false, "model": "gpt-4o-mini" }
    Retorna: { "results": { "1": {...}, "2": {...} } }

    Usa cache — solo re-infiere los que no tienen cache fresco.
    """
    body = request.get_json(silent=True) or {}
    ticket_ids: list[int] = [int(x) for x in (body.get("ticket_ids") or [])]
    force = bool(body.get("force_refresh", False))
    model = body.get("model") or None

    if not ticket_ids:
        return jsonify({"results": {}})

    # Resolver ado_ids desde BD
    with session_scope() as session:
        tickets = session.query(Ticket).filter(Ticket.id.in_(ticket_ids)).all()
        id_to_ado = {t.id: t.ado_id for t in tickets}

    results: dict[str, dict] = {}
    for tid in ticket_ids:
        ado_id = id_to_ado.get(tid)
        if ado_id is None:
            results[str(tid)] = {"error": "not_found"}
            continue
        try:
            r = infer_pipeline(ado_id=ado_id, force_refresh=force, model=model)
            results[str(tid)] = r.to_dict()
        except Exception as e:
            logger.warning("batch inference falló para ticket %s (ADO-%s): %s", tid, ado_id, e)
            results[str(tid)] = {"error": str(e)}

    return jsonify({"results": results})


@bp.delete("/<int:ticket_id>/ado-pipeline-cache")
def delete_ado_pipeline_cache(ticket_id: int):
    """Invalida el cache de inferencia para forzar re-inferencia en la próxima llamada."""
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id
    invalidate_cache(ado_id)
    return jsonify({"ok": True, "ado_id": ado_id})


@bp.get("/<int:ticket_id>/fingerprint")
def get_fingerprint(ticket_id: int):
    """N3 — Ticket Pre-Analysis Fingerprint (TPAF).
    Retorna análisis rápido del ticket: dominio, tipo de cambio, complejidad, pack sugerido.
    Fase 1: keyword-based (sin LLM). Fase 3+: embeddings.
    """
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        result = fingerprint.analyze(t)
        return jsonify(result.to_dict())


@bp.get("/<int:ticket_id>/glossary")
def get_glossary(ticket_id: int):
    """FA-09 — Glossary auto-detection.
    Devuelve un ContextBlock listo para inyectar con los términos detectados
    en el título + descripción del ticket.
    """
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        block = glossary.build_glossary_block([t.title or "", t.description or ""])
        return jsonify(block)


@bp.get("/<int:ticket_id>/comments")
def get_comments(ticket_id: int):
    """Devuelve los comentarios/notas del ticket desde Azure DevOps (on-demand).

    Busca el ticket en BD para obtener su ado_id, luego llama a AdoClient.fetch_comments.
    Retorna: { "comments": [{ "author", "date", "text" }] }
    """
    from services.ado_client import AdoClient, AdoApiError, AdoConfigError
    from services.ado_sync import _html_to_text

    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id

    try:
        client = AdoClient()
    except AdoConfigError as e:
        return jsonify({"comments": [], "error": str(e)}), 200

    raw = client.fetch_comments(ado_id)
    comments = [
        {
            "author": c["author"],
            "date": c["date"],
            "text": _html_to_text(c["text"]),
        }
        for c in raw
        if c.get("text")
    ]
    return jsonify({"comments": comments})


@bp.get("/<int:ticket_id>/attachments")
def get_attachments(ticket_id: int):
    """Devuelve los adjuntos del ticket desde Azure DevOps (on-demand).

    Retorna: { "attachments": [{ "name", "url", "size", "text_content" }] }
    text_content se incluye solo para archivos de texto <= 64KB.
    """
    from services.ado_client import AdoClient, AdoConfigError

    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id

    try:
        client = AdoClient()
    except AdoConfigError as e:
        return jsonify({"attachments": [], "error": str(e)}), 200

    attachments = client.fetch_attachments(ado_id)
    return jsonify({"attachments": attachments})


@bp.get("/<int:ticket_id>/stacky-status")
def get_stacky_status(ticket_id: int):
    """Devuelve el stacky_status actual del ticket y su historial de transiciones.

    Response:
      {
        "ticket_id": 1,
        "current_status": "idle" | "running" | "completed" | "error" | "cancelled",
        "history": [ { "id", "old_status", "new_status", "changed_by", "changed_at",
                        "execution_id", "agent_type", "reason", "metadata" } ]
      }
    """
    from services import ticket_status as ts

    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)

    limit = request.args.get("limit", default=20, type=int)
    return jsonify({
        "ticket_id": ticket_id,
        "current_status": ts.get_current_status(ticket_id),
        "history": ts.get_history(ticket_id, limit=limit),
    })


@bp.patch("/<int:ticket_id>/stacky-status")
def set_stacky_status(ticket_id: int):
    """Permite actualizar manualmente el stacky_status de un ticket.

    Body: { "status": "idle" | "running" | "completed" | "error" | "cancelled",
            "reason": "texto libre opcional" }
    Útil para resets manuales del operador o integraciones externas.
    """
    from services import ticket_status as ts

    body = request.get_json(silent=True) or {}
    new_status = body.get("status", "").strip()
    reason = body.get("reason")
    user = request.headers.get("X-User-Email") or "anonymous"

    if not new_status:
        return jsonify({"error": "campo 'status' requerido"}), 400

    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)

    try:
        ts.set_status(
            ticket_id,
            new_status,
            changed_by=user,
            reason=reason or f"Manual update via API by {user}",
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "ticket_id": ticket_id,
        "current_status": ts.get_current_status(ticket_id),
    })


@bp.patch("/by-ado/<int:ado_id>/stacky-status")
def set_stacky_status_by_ado(ado_id: int):
    """Override manual auditado de stacky_status (endpoint legacy, plan §17).

    IMPORTANTE: Este endpoint se mantiene como OVERRIDE MANUAL AUDITADO.
    No debe usarse para el flujo normal de finalización de agentes — para eso
    está POST /api/tickets/by-ado/{ado_id}/agent-completion con el gateway.

    Cada invocación:
    - Escribe completion_source='manual' en la AgentExecution si el campo existe.
    - Emite SystemLog(source='legacy_stacky_status', action='manual_override') con
      correlation_id, user_email, reason.
    - Si STACKY_COMPLETION_GATEWAY=on, agrega warning en log indicando que se
      usó el override manual mientras el gateway está activo.
    - Auto-publish server-side: cuando status=completed Y html_output_path apunta
      a un archivo existente Y existe AgentExecution válida, Stacky invoca
      ado_publisher.publish_from_execution automáticamente. El agente NO envía
      ningún flag para activar esto — la decisión es enteramente server-side.
      Controlado por env var STACKY_LEGACY_AUTO_PUBLISH (default "on").
      Si está en "off", el publish se omite y se registra publish.skipped.
      Si publish falla, el error se registra pero NO rompe el PATCH (el estado
      local ya quedó guardado). El resultado de publish se incluye en el response.

    Body:
      {
        "status": "completed" | "error" | "cancelled" | "idle",
        "reason": "texto libre opcional",
        "agent_type": "developer" | "technical" | ... (opcional),
        "html_output_path": "Agentes/outputs/<ADO_ID>/comment.html" (opcional)
      }

    Nota: el campo "auto_publish" es ignorado si está presente en el body —
    el comportamiento de publicación es server-side y no puede ser controlado
    por el agente.

    Responde 200 aunque el ticket no esté en BD (para no romper al agente).
    """
    import os as _os
    import uuid as _uuid
    from services import ticket_status as ts
    from models import SystemLog

    body = request.get_json(silent=True) or {}
    new_status = body.get("status", "").strip()
    reason = body.get("reason")
    agent_type = body.get("agent_type")
    html_output_path = body.get("html_output_path")
    user = request.headers.get("X-User-Email") or "agent"
    correlation_id = str(_uuid.uuid4())

    # Leer env vars de control server-side
    gateway_mode = _os.getenv("STACKY_COMPLETION_GATEWAY", "off").lower().strip()
    legacy_auto_publish = _os.getenv("STACKY_LEGACY_AUTO_PUBLISH", "on").lower().strip()

    # Warning si gateway está activo (plan §B-2)
    if gateway_mode == "on":
        logger.warning(
            "legacy_stacky_status: manual override while gateway is active — "
            "ado_id=%s user=%s corr=%s — verificar si fue intencional",
            ado_id, user, correlation_id,
        )

    if not new_status:
        return jsonify({"ok": False, "error": "campo 'status' requerido"}), 400

    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
        if t is None:
            logger.warning("set_stacky_status_by_ado: ADO-%s no encontrado en BD — ignorado", ado_id)
            return jsonify({"ok": True, "skipped": True, "reason": "ticket not in local DB"}), 200
        ticket_id = t.id

        # Persistir html_output_path + completion_source='manual' en la última AgentExecution
        last_exec = None
        if html_output_path or True:  # siempre intentar marcar completion_source
            q = session.query(AgentExecution).filter(
                AgentExecution.ticket_id == ticket_id
            )
            if agent_type:
                q = q.filter(AgentExecution.agent_type == agent_type)
            last_exec = q.order_by(AgentExecution.started_at.desc()).first()
            if last_exec is not None:
                if html_output_path and hasattr(last_exec, "html_output_path"):
                    last_exec.html_output_path = html_output_path
                # Marcar como override manual (campo de P2)
                if hasattr(last_exec, "completion_source"):
                    last_exec.completion_source = "manual"

        # Emitir SystemLog de override manual auditado
        log_ctx = {
            "correlation_id": correlation_id,
            "ado_id": ado_id,
            "new_status": new_status,
            "agent_type": agent_type,
            "html_output_path": html_output_path,
            "reason": reason,
            "gateway_mode": gateway_mode,
            "legacy_auto_publish": legacy_auto_publish,
            "gateway_active_warning": gateway_mode == "on",
            "execution_id": last_exec.id if last_exec else None,
        }
        audit_log = SystemLog(
            level="WARNING" if gateway_mode == "on" else "INFO",
            source="legacy_stacky_status",
            action="manual_override",
            ticket_id=ticket_id,
            execution_id=last_exec.id if last_exec else None,
            user=user,
            context_json=__import__("json").dumps(log_ctx, ensure_ascii=False, default=str),
            tags_json=__import__("json").dumps(
                ["legacy", "manual_override"] + (["gateway_active_warning"] if gateway_mode == "on" else [])
            ),
        )
        session.add(audit_log)

    # ── Cierre unificado: ticket_status + auto-publish vía helper ────────────
    # close_execution_with_publish reemplaza el bloque de ~70 líneas que antes
    # vivía acá inline. Es el mismo path que usa el output_watcher para cerrar
    # runs huérfanos automáticamente.
    publish_result: dict
    if last_exec is None:
        # Caller pasó un ticket sin ejecuciones — sólo seteamos stacky_status manual,
        # sin path de auto-publish posible (no hay execution_id).
        try:
            ts.set_status(
                ticket_id,
                new_status,
                changed_by=user,
                agent_type=agent_type,
                reason=reason or f"Manual override via legacy endpoint (ADO-{ado_id}) corr={correlation_id}",
                metadata={"html_output_path": html_output_path, "completion_source": "manual"} if html_output_path else {"completion_source": "manual"},
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        if new_status != "completed":
            publish_result = {"skipped": True, "reason": "status_not_completed"}
        elif legacy_auto_publish == "off":
            publish_result = {"skipped": True, "reason": "legacy_auto_publish_disabled"}
        elif not html_output_path:
            publish_result = {"skipped": True, "reason": "html_output_path_missing"}
        else:
            publish_result = {"skipped": True, "reason": "no_execution_found"}
            logger.warning(
                "set_stacky_status_by_ado: publish.skipped(no_execution_found) — "
                "ADO-%s html_output_path=%s corr=%s",
                ado_id, html_output_path, correlation_id,
            )
    else:
        # Path normal: hay execution. Usar la helper unificada.
        from services.agent_completion_internal import close_execution_with_publish

        # Si estamos transicionando a estados no-terminal (p.ej. status=idle),
        # la helper no aplica (es solo para terminal). Caemos al set_status manual.
        if new_status not in {"completed", "error", "cancelled"}:
            try:
                ts.set_status(
                    ticket_id,
                    new_status,
                    changed_by=user,
                    agent_type=agent_type,
                    reason=reason or f"Manual override via legacy endpoint (ADO-{ado_id}) corr={correlation_id}",
                    metadata={"completion_source": "manual"},
                )
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
            publish_result = {"skipped": True, "reason": "status_not_completed"}
        else:
            close_result = close_execution_with_publish(
                execution_id=last_exec.id,
                triggered_by="legacy_auto_publish",
                final_status=new_status,
                html_output_path=html_output_path,
                user=user,
                reason=reason or f"Manual override via legacy endpoint (ADO-{ado_id}) corr={correlation_id}",
                completion_source="manual",
                agent_type_hint=agent_type,
                # Si legacy_auto_publish=="off" forzamos disable; sino dejamos default (lee env).
                auto_publish=False if legacy_auto_publish == "off" else None,
            )
            publish_result = close_result.publish
            # Backward-compat con el contrato legacy: el reason del skip era
            # "legacy_auto_publish_disabled" antes del refactor.
            if publish_result.get("reason") == "auto_publish_disabled":
                publish_result = dict(publish_result)
                publish_result["reason"] = "legacy_auto_publish_disabled"
            if close_result.publish.get("ok") is True:
                logger.info(
                    "set_stacky_status_by_ado: publish.succeeded — ADO-%s exec=%d corr=%s",
                    ado_id, last_exec.id, correlation_id,
                )
            elif close_result.publish.get("ok") is False:
                logger.warning(
                    "set_stacky_status_by_ado: publish.failed — ADO-%s exec=%d reason=%s corr=%s",
                    ado_id, last_exec.id, close_result.publish.get("reason"), correlation_id,
                )

    return jsonify({
        "ok": True,
        "ado_id": ado_id,
        "ticket_id": ticket_id,
        "current_status": ts.get_current_status(ticket_id),
        "html_output_path": html_output_path,
        "completion_source": "manual",
        "correlation_id": correlation_id,
        "gateway_active_warning": gateway_mode == "on",
        "publish": publish_result,
    })


@bp.post("/by-ado/<int:ado_id>/agent-completion")
def agent_completion(ado_id: int):
    """Gateway canónico de finalización de agentes (Plan SSD P1).

    Endpoint: POST /api/tickets/by-ado/{ado_id}/agent-completion

    Auth obligatoria: header X-Stacky-Agent-Token. Si falta o es inválido → 401.
    X-User-Email opcional (trazabilidad).

    Feature flag STACKY_COMPLETION_GATEWAY:
      off    → 404 (endpoint deshabilitado, comportamiento P0).
      shadow → corre en simulación, no muta DB/ADO. Responde 200 con plan.
      on     → gateway canónico activo (reservado para P5, responde 501 por ahora).

    Payload v1:
      {
        "execution_id": 44,               // opcional; si se omite, se resuelve
        "agent_type": "functional",       // requerido
        "status": "completed",            // requerido; uno de: completed|error|cancelled|needs_review
        "html_output_path": "Agentes/outputs/149/comment.html",  // opcional
        "metadata": {
          "html_sha256": "...",           // opcional
          "agent_version": "Agente@2026-05-14",  // opcional
          "duration_ms": 184232          // opcional
        },
        "reason": "texto libre",          // opcional
        "allow_synthetic_rescue": false   // opcional; solo con status=completed
      }

    Respuesta shadow:
      {
        "mode": "shadow",
        "ok": true,
        "would_succeed": true|false,
        "correlation_id": "uuid",
        "ticket_id": 42,
        "execution_id": 44,
        "plan": [...],
        "errors": [...],
        "discrepancies": [...]
      }
    """
    import os as _os
    import uuid as _uuid
    from services.agent_completion import CompletionPayload, GatewayError

    correlation_id = str(_uuid.uuid4())
    # Leer el flag dinámicamente en cada request para permitir hot-reload en tests
    # y cambios sin reiniciar el proceso (via env var update o config en runtime).
    gateway_mode = _os.getenv("STACKY_COMPLETION_GATEWAY", "off").lower().strip()

    # ── Feature flag: off → 404 ──────────────────────────────────────────────
    if gateway_mode == "off":
        return jsonify({
            "ok": False,
            "error": {
                "code": "gateway_disabled",
                "message": (
                    "El gateway de finalización de agentes está deshabilitado. "
                    "Establezca STACKY_COMPLETION_GATEWAY=shadow para activarlo. "
                    "Use PATCH /api/tickets/by-ado/{ado_id}/stacky-status para el flujo legacy."
                ),
            },
        }), 404

    # ── Auth: X-Stacky-Agent-Token ───────────────────────────────────────────
    agent_token_header = request.headers.get("X-Stacky-Agent-Token", "").strip()
    expected_token = _os.getenv("STACKY_AGENT_TOKEN", "").strip()

    if not agent_token_header:
        logger.warning(
            "gateway[%s] 401 missing token: ado_id=%s corr=%s",
            gateway_mode, ado_id, correlation_id,
        )
        return jsonify({
            "ok": False,
            "error": {"code": "auth_required", "message": "Header X-Stacky-Agent-Token requerido"},
            "correlation_id": correlation_id,
        }), 401

    if expected_token and agent_token_header != expected_token:
        logger.warning(
            "gateway[%s] 401 invalid token: ado_id=%s corr=%s",
            gateway_mode, ado_id, correlation_id,
        )
        return jsonify({
            "ok": False,
            "error": {"code": "auth_required", "message": "X-Stacky-Agent-Token inválido"},
            "correlation_id": correlation_id,
        }), 401

    user = request.headers.get("X-User-Email") or "agent"

    # ── Parse payload v1 ─────────────────────────────────────────────────────
    body = request.get_json(silent=True) or {}
    if not body:
        return jsonify({
            "ok": False,
            "error": {"code": "payload_invalid", "message": "Body JSON requerido"},
            "correlation_id": correlation_id,
        }), 400

    try:
        payload = CompletionPayload.from_dict(body)
    except (ValueError, KeyError) as exc:
        return jsonify({
            "ok": False,
            "error": {"code": "payload_invalid", "message": str(exc)},
            "correlation_id": correlation_id,
        }), 400

    # ── Modo shadow ──────────────────────────────────────────────────────────
    if gateway_mode == "shadow":
        from services.agent_completion import run_shadow

        # legacy_state: si el cliente quiere que el gateway detecte discrepancias
        # puede pasar el resultado del legacy en body["_legacy_observed"].
        # Es opcional — si no viene, el gateway solo simula.
        legacy_state: dict | None = body.get("_legacy_observed")

        try:
            result, http_status = run_shadow(
                ado_id=ado_id,
                payload=payload,
                user=user,
                correlation_id=correlation_id,
                legacy_state=legacy_state,
            )
            return jsonify(result.to_dict()), http_status
        except Exception as exc:
            logger.exception(
                "gateway[shadow] internal_error: ado_id=%s corr=%s", ado_id, correlation_id,
            )
            return jsonify({
                "ok": False,
                "error": {
                    "code": "internal_error",
                    "message": "Error interno en el gateway shadow",
                    "detail": {"correlation_id": correlation_id},
                },
                "correlation_id": correlation_id,
            }), 500

    # ── Modo on (P5 — gateway canónico activo) ───────────────────────────────
    if gateway_mode == "on":
        from services.agent_completion import run_on

        try:
            result, http_status = run_on(
                ado_id=ado_id,
                payload=payload,
                user=user,
                correlation_id=correlation_id,
            )
            return jsonify(result.to_dict()), http_status
        except Exception as exc:
            logger.exception(
                "gateway[on] internal_error: ado_id=%s corr=%s", ado_id, correlation_id,
            )
            return jsonify({
                "ok": False,
                "error": {
                    "code": "internal_error",
                    "message": "Error interno en el gateway (modo on)",
                    "detail": {"correlation_id": correlation_id},
                },
                "correlation_id": correlation_id,
            }), 500

    # Modo desconocido (guardrail)
    return jsonify({
        "ok": False,
        "error": {
            "code": "gateway_config_error",
            "message": (
                f"STACKY_COMPLETION_GATEWAY='{gateway_mode}' no es un valor válido. "
                "Valores aceptados: off | shadow | on"
            ),
        },
        "correlation_id": correlation_id,
    }), 500


@bp.post("/recover-stale-status")
def recover_stale_status():
    """Corrige tickets con stacky_status='running' cuya última ejecución ya terminó.

    Equivalente al startup recovery pero invocable on-demand desde el frontend
    o el operador. También detecta ejecuciones con timeout (running por más de
    EXECUTION_TIMEOUT_MINUTES) y las cierra como 'error'.

    Response:
      {
        "ok": true,
        "fixed": N,                         // cantidad (compatibilidad)
        "count": N,                         // mismo valor, nombre explícito
        "trigger": "manual",
        "details": [
          { "ticket_id": 42, "ado_id": 122, "old_status": "running",
            "new_status": "completed", "execution_id": 99,
            "agent_type": "developer", "kind": "execution_ended",
            "reason": "...", "trigger": "manual" },
          ...
        ]
      }
    """
    from services.ticket_status import recover_stale_running_tickets

    try:
        details = recover_stale_running_tickets(trigger="manual")
    except Exception as exc:
        logger.exception("recover-stale-status falló")
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({
        "ok": True,
        "fixed": len(details),
        "count": len(details),
        "trigger": "manual",
        "details": details,
    })


# ── Fase 4: cierre manual fallback ────────────────────────────────────────────


@bp.post("/<int:ticket_id>/finish-work")
def finish_work(ticket_id: int):
    """Cierre manual de un ticket cuando la automatización no lo logró (Fase 4).

    Acciones (en orden, todas con audit trail):
      1. Validar precondiciones (existe ticket, no está ya completed).
      2. Si publish_to_ado=True: localizar y publicar el HTML del agente en ADO.
      3. Si target_ado_state se provee: cambiar el System.State del work item.
      4. Marcar stacky_status='completed' con changed_by=operador.
      5. Registrar evento estructurado en stacky_logger ('manual_finish_work').

    Body (JSON):
      {
        "operator_reason": "texto obligatorio, min 5 chars",
        "publish_to_ado": true,         // default true
        "html_output_path": "..."|null, // override del HTML — opcional
        "target_ado_state": "Done"|null,// si null, no se cambia el estado ADO
        "force_publish": false,          // bypassea dedupe de ado_publisher
        "dry_run": false                 // si true, solo valida — no ejecuta
      }

    Response:
      {
        "ok": bool,
        "dry_run": bool,
        "ticket_id": int,
        "ado_id": int|null,
        "preconditions": { html_exists, html_valid_reason, current_stacky_status },
        "actions": [
          { "action": "publish_ado_comment", "ok": bool, "reason": str|null,
            "html_sha256": str|null, "record_id": int|null },
          { "action": "update_ado_state",    "ok": bool, "to": str, "reason": str|null },
          { "action": "update_stacky_status","ok": bool, "to": "completed" }
        ],
        "current_status": str
      }
    """
    from services import ticket_status as ts
    from services.ado_publisher import publish_from_execution
    from services import agent_html_output as html_io

    body = request.get_json(silent=True) or {}
    operator_reason = (body.get("operator_reason") or "").strip()
    publish_to_ado_flag = bool(body.get("publish_to_ado", True))
    html_output_path = body.get("html_output_path")
    target_ado_state = body.get("target_ado_state")
    force_publish = bool(body.get("force_publish", False))
    # force_finish=true permite cerrar manualmente aunque el MANIFEST diga
    # work_completed=false (caso: operador limpia un ticket conocido como
    # roto). Sin este flag, el manifest gate devuelve 409.
    force_finish = bool(body.get("force_finish", False))
    dry_run = bool(body.get("dry_run", False))
    operator = request.headers.get("X-User-Email") or "anonymous"
    # Trazabilidad de origen: el frontend UI envía "manual_ui"; agentes envían "agent" u omiten.
    # Backward-compat: si no viene el header ni el campo, default "manual".
    completion_source: str = (
        request.headers.get("X-Completion-Source")
        or body.get("completion_source")
        or "manual"
    )

    if len(operator_reason) < 5:
        return jsonify({
            "ok": False,
            "error": "operator_reason requerido (mínimo 5 caracteres)",
        }), 400

    # ── 1. Cargar contexto ────────────────────────────────────────────────────
    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            abort(404)
        ado_id: int | None = getattr(ticket, "ado_id", None)
        current_stacky = getattr(ticket, "stacky_status", "idle") or "idle"

        # Última ejecución para localizar el HTML del agente
        last_exec = (
            session.query(AgentExecution)
            .filter(AgentExecution.ticket_id == ticket_id)
            .order_by(AgentExecution.started_at.desc())
            .first()
        )
        execution_id = last_exec.id if last_exec else None
        # html_output_path se setea dinámicamente (no es columna); usamos
        # getattr para no romper en runs que nunca lo recibieron.
        exec_hint = getattr(last_exec, "html_output_path", None) if last_exec else None

    if current_stacky == "completed":
        return jsonify({
            "ok": False,
            "error": "ticket ya está en stacky_status='completed'",
            "current_status": current_stacky,
        }), 409

    # ── 1b. Manifest gate (Fase 3/5) ──────────────────────────────────────────
    # Si la última ejecución dejó un MANIFEST que dice work_completed=false, el
    # cierre manual es probablemente prematuro. Devolvemos 409 con el manifest
    # para que la UI muestre por qué; el operador puede pasar force_finish=true
    # para override.
    manifest_check = _check_finish_manifest_gate(execution_id)
    if (
        manifest_check is not None
        and not manifest_check["work_completed"]
        and not dry_run
        and not force_finish
    ):
        return jsonify({
            "ok": False,
            "error": "manifest_work_not_completed",
            "message": (
                "La última ejecución dejó un MANIFEST con work_completed=false. "
                "Si querés cerrar igual, mandá force_finish=true."
            ),
            "manifest": manifest_check,
            "current_status": current_stacky,
        }), 409

    # ── 2. Preflight: HTML existe y es válido? ────────────────────────────────
    html_exists = False
    html_invalid_reason: str | None = None
    if ado_id is not None and publish_to_ado_flag:
        hint = html_output_path or exec_hint
        try:
            html_io.read_and_validate(int(ado_id), hint=hint)
            html_exists = True
        except html_io.ValidationError as exc:
            html_invalid_reason = str(exc)
            # NOT_FOUND no es bloqueante — publicaremos una nota de cierre manual.
            # SECRET_DETECTED sí: rechazar la operación.
            if exc.code == "SECRET_DETECTED":
                return jsonify({
                    "ok": False,
                    "error": f"HTML contiene secretos; cierre manual abortado: {exc.message}",
                    "preconditions": {
                        "html_exists": False,
                        "html_invalid_reason": html_invalid_reason,
                        "current_stacky_status": current_stacky,
                    },
                }), 422

    preconditions = {
        "html_exists": html_exists,
        "html_invalid_reason": html_invalid_reason,
        "current_stacky_status": current_stacky,
        "execution_id": execution_id,
        "ado_id": ado_id,
    }

    if dry_run:
        return jsonify({
            "ok": True,
            "dry_run": True,
            "ticket_id": ticket_id,
            "ado_id": ado_id,
            "preconditions": preconditions,
            "actions": [],
            "current_status": current_stacky,
            "operator": operator,
        })

    actions: list[dict] = []

    # ── 3. Publicar en ADO ────────────────────────────────────────────────────
    if publish_to_ado_flag and ado_id is not None:
        if html_exists and execution_id is not None:
            result = publish_from_execution(
                execution_id,
                triggered_by="finish_work",
                force=force_publish,
            )
            actions.append({
                "action": "publish_ado_comment",
                "ok": result.ok,
                "status": result.status,
                "reason": result.reason,
                "html_sha256": result.html_sha256,
                "record_id": result.record_id,
            })
        else:
            # No hay HTML — publicar nota de cierre manual textual
            try:
                from services.ado_client import AdoClient
                fallback_html = (
                    "<p><b>Cierre manual desde Stacky Agents.</b></p>"
                    f"<p>Operador: {operator}</p>"
                    f"<p>Motivo: {operator_reason}</p>"
                )
                AdoClient().post_comment(int(ado_id), fallback_html, "html")
                actions.append({
                    "action": "publish_ado_comment",
                    "ok": True,
                    "status": "ok",
                    "reason": "no_agent_html_fallback_note",
                    "html_sha256": None,
                    "record_id": None,
                })
            except Exception as exc:  # noqa: BLE001
                logger.exception("finish_work: fallback note falló")
                actions.append({
                    "action": "publish_ado_comment",
                    "ok": False,
                    "status": "failed",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "html_sha256": None,
                    "record_id": None,
                })

    # ── 4. Cambiar estado en ADO ──────────────────────────────────────────────
    if target_ado_state and ado_id is not None:
        try:
            from services.ado_client import AdoClient
            AdoClient().update_work_item_state(int(ado_id), target_ado_state)
            actions.append({
                "action": "update_ado_state",
                "ok": True,
                "to": target_ado_state,
                "reason": None,
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("finish_work: update_ado_state falló")
            actions.append({
                "action": "update_ado_state",
                "ok": False,
                "to": target_ado_state,
                "reason": f"{type(exc).__name__}: {exc}",
            })

    # ── 5. Cerrar en Stacky BD ────────────────────────────────────────────────
    try:
        ts.set_status(
            ticket_id,
            "completed",
            changed_by=operator,
            execution_id=execution_id,
            reason=f"Manual finish-work: {operator_reason}",
            metadata={
                "trigger": "manual_finish_work",
                "completion_source": completion_source,
                "operator": operator,
                "operator_reason": operator_reason,
                "target_ado_state": target_ado_state,
                "actions": actions,
            },
        )
        actions.append({
            "action": "update_stacky_status",
            "ok": True,
            "to": "completed",
            "reason": None,
        })
    except ValueError as exc:
        actions.append({
            "action": "update_stacky_status",
            "ok": False,
            "to": "completed",
            "reason": str(exc),
        })

    # ── 6. Evento estructurado para audit ─────────────────────────────────────
    try:
        from services.stacky_logger import logger as slog
        slog.info(
            "tickets",
            "manual_finish_work",
            ticket_id=ticket_id,
            execution_id=execution_id,
            user=operator,
            context_data={
                "ado_id": ado_id,
                "completion_source": completion_source,
                "operator_reason": operator_reason,
                "target_ado_state": target_ado_state,
                "preconditions": preconditions,
                "actions": actions,
                "dry_run": False,
            },
            tags=["ticket", "finish_work", "manual", completion_source],
        )
    except Exception:
        logger.exception("emit manual_finish_work falló (no crítico)")

    overall_ok = all(a.get("ok") for a in actions)
    return jsonify({
        "ok": overall_ok,
        "dry_run": False,
        "ticket_id": ticket_id,
        "ado_id": ado_id,
        "preconditions": preconditions,
        "actions": actions,
        "current_status": ts.get_current_status(ticket_id),
        "operator": operator,
    })


# ── Fase 2: Create Child Task from pending-task.json ──────────────────────────


@bp.get("/by-ado/<int:ado_id>/pending-tasks")
def list_pending_tasks(ado_id: int):
    """Lista los pending-task.json no consumidos para un Epic (CA-11).

    Escanea `Agentes/outputs/epic-{ado_id}/*/pending-task.json`.
    Retorna solo los que tienen status=pending_manual_creation (sin consumed_at).

    Response:
      {
        "ok": true,
        "epic_ado_id": 149,
        "pending_tasks": [ { rf_id, title, pending_task_path, generated_at,
                              plan_de_pruebas_path, plan_exists, status } ],
        "total_pending": N,
        "total_consumed": M
      }
    """
    repo_root = _resolve_repo_root()
    epic_dir = repo_root / "Agentes" / "outputs" / f"epic-{ado_id}"

    pending: list[dict] = []
    consumed_count = 0

    if epic_dir.is_dir():
        for rf_dir in sorted(epic_dir.iterdir()):
            if not rf_dir.is_dir():
                continue
            pt_file = rf_dir / "pending-task.json"
            if not pt_file.is_file():
                continue
            try:
                payload = json.loads(pt_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("list_pending_tasks: no se pudo parsear %s: %s", pt_file, exc)
                continue

            if "consumed_at" in payload or payload.get("status") == "consumed":
                consumed_count += 1
                continue

            # Verificar si existe el plan de pruebas
            plan_rel = payload.get("plan_de_pruebas_path", "")
            plan_path = repo_root / plan_rel if plan_rel else None
            plan_exists = bool(plan_path and plan_path.is_file())

            # Ruta relativa al repo para el cliente
            try:
                rel_path = str(pt_file.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                rel_path = str(pt_file)

            pending.append({
                "rf_id": payload.get("rf_id", ""),
                "title": payload.get("title", ""),
                "pending_task_path": rel_path,
                "generated_at": payload.get("generated_at", ""),
                "plan_de_pruebas_path": plan_rel,
                "plan_exists": plan_exists,
                "status": payload.get("status", "pending_manual_creation"),
            })

    return jsonify({
        "ok": True,
        "epic_ado_id": ado_id,
        "pending_tasks": pending,
        "total_pending": len(pending),
        "total_consumed": consumed_count,
    })


@bp.post("/by-ado/<int:ado_id>/create-child-task")
def create_child_task(ado_id: int):
    """Crea una Task hija del Epic en ADO consumiendo un pending-task.json (Fase 2).

    Cadena de acciones:
      1. Leer y validar pending-task.json (schema + idempotencia).
      2. AdoClient.create_work_item → JSON Patch con Hierarchy-Reverse al Epic.
      3. AdoClient.upload_attachment → plan-de-pruebas.md como adjunto.
      4. AdoClient.link_attachment_to_work_item → vincular adjunto a la Task.
      5. AdoClient.post_comment → registrar operator_reason en la Task.
      6. Marcar pending-task.json como consumed (bajo file lock).
      7. Registrar SystemLog con auditoría completa.

    Body:
      { "pending_task_path": str, "operator_reason": str?, "dry_run": bool? }

    Response (éxito):
      { ok, dry_run, epic_ado_id, task_ado_id, task_url, attachment_id,
        actions, pending_task_consumed, idempotent?, correlation_id }
    """
    correlation_id = str(_uuid_mod.uuid4())
    body = request.get_json(silent=True) or {}
    pending_task_path_str: str = (body.get("pending_task_path") or "").strip()
    operator_reason: str = (body.get("operator_reason") or "").strip()
    dry_run: bool = bool(body.get("dry_run", False))
    completion_source: str = (
        request.headers.get("X-Completion-Source")
        or body.get("completion_source")
        or "manual"
    )
    user = request.headers.get("X-User-Email") or "anonymous"

    if not pending_task_path_str:
        return jsonify({
            "ok": False,
            "error": "MISSING_PENDING_TASK_PATH",
            "message": "El campo 'pending_task_path' es obligatorio",
            "correlation_id": correlation_id,
        }), 400

    repo_root = _resolve_repo_root()
    pt_file = repo_root / pending_task_path_str

    # ── [1a] Verificar existencia del archivo ──────────────────────────────────
    if not pt_file.is_file():
        return jsonify({
            "ok": False,
            "error": "PENDING_TASK_FILE_NOT_FOUND",
            "message": f"No se encontró el archivo: {pending_task_path_str}",
            "correlation_id": correlation_id,
        }), 400

    # ── [1b] Parsear y validar schema ─────────────────────────────────────────
    try:
        pt_payload = json.loads(pt_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": "PENDING_TASK_PARSE_ERROR",
            "message": f"No se pudo parsear el archivo JSON: {exc}",
            "correlation_id": correlation_id,
        }), 400

    missing_fields = sorted(_PENDING_TASK_REQUIRED_FIELDS - set(pt_payload.keys()))
    if missing_fields:
        return jsonify({
            "ok": False,
            "error": "PENDING_TASK_SCHEMA_INVALID",
            "missing_fields": missing_fields,
            "message": f"Campos requeridos ausentes en pending-task.json: {missing_fields}",
            "correlation_id": correlation_id,
        }), 400

    # ── [1c] Verificar que epic_id coincide con la URL ─────────────────────────
    file_epic_id = str(pt_payload.get("epic_id", "")).strip()
    if file_epic_id != str(ado_id):
        return jsonify({
            "ok": False,
            "error": "PENDING_TASK_EPIC_MISMATCH",
            "message": (
                f"epic_id en el archivo ('{file_epic_id}') no coincide con "
                f"epic_ado_id en la URL ({ado_id})"
            ),
            "file_epic_id": file_epic_id,
            "url_epic_ado_id": ado_id,
            "correlation_id": correlation_id,
        }), 400

    # ── [1d] Idempotencia: ¿ya fue consumido? ──────────────────────────────────
    if "consumed_at" in pt_payload or pt_payload.get("status") == "consumed":
        prev_task_id = pt_payload.get("task_ado_id")
        prev_url = None
        if prev_task_id:
            try:
                prev_url = AdoClient().work_item_url(int(prev_task_id))
            except Exception:
                pass
        return jsonify({
            "ok": True,
            "dry_run": False,
            "epic_ado_id": ado_id,
            "task_ado_id": prev_task_id,
            "task_url": prev_url,
            "attachment_id": pt_payload.get("attachment_id"),
            "actions": [],
            "pending_task_consumed": True,
            "idempotent": True,
            "reason": "PENDING_TASK_ALREADY_CONSUMED",
            "correlation_id": correlation_id,
        })

    # ── [dry_run] Retornar plan de acciones sin tocar ADO ─────────────────────
    plan_rel = pt_payload.get("plan_de_pruebas_path", "")
    plan_path = repo_root / plan_rel if plan_rel else None
    plan_exists = bool(plan_path and plan_path.is_file())

    if dry_run:
        dry_actions = [
            {
                "action": "create_work_item",
                "would_call": f"POST _apis/wit/workitems/$Task?api-version=7.1",
                "payload_preview": {
                    "title": pt_payload.get("title"),
                    "parent": ado_id,
                    "state": pt_payload.get("target_state", "Technical review"),
                },
            },
            {
                "action": "upload_attachment",
                "would_call": "POST _apis/wit/attachments?fileName=plan-de-pruebas.md",
                "file_exists": plan_exists,
            },
            {
                "action": "link_attachment",
                "would_call": "PATCH _apis/wit/workitems/{task_id}/relations/-",
            },
        ]
        return jsonify({
            "ok": True,
            "dry_run": True,
            "epic_ado_id": ado_id,
            "task_ado_id": None,
            "task_url": None,
            "attachment_id": None,
            "actions": dry_actions,
            "pending_task_consumed": False,
            "correlation_id": correlation_id,
        })

    # ── [2–7] Ejecución real ───────────────────────────────────────────────────
    actions: list[dict] = []
    task_ado_id: int | None = None
    task_url: str | None = None
    attachment_id: str | None = None
    human_action_required: str | None = None

    # Inicializar cliente ADO
    try:
        ado = AdoClient()
    except _AdoConfigError as exc:
        _audit_create_child_task(
            correlation_id=correlation_id,
            ado_id=ado_id,
            user=user,
            completion_source=completion_source,
            operator_reason=operator_reason,
            pt_path=pending_task_path_str,
            ok=False,
            actions=[],
            error=str(exc),
        )
        return jsonify({
            "ok": False,
            "error": "ADO_CONFIG_MISSING",
            "message": str(exc),
            "correlation_id": correlation_id,
        }), 503

    # ── [2] create_work_item ───────────────────────────────────────────────────
    try:
        wi_result = ado.create_work_item(
            work_item_type="Task",
            fields={
                "System.Title": pt_payload["title"],
                "System.Description": pt_payload.get("description_html", ""),
                "System.State": pt_payload.get("target_state", "Technical review"),
            },
            parent_ado_id=ado_id,
        )
        task_ado_id = int(wi_result["id"])
        task_url = ado.work_item_url(task_ado_id)
        actions.append({
            "action": "create_work_item",
            "ok": True,
            "task_ado_id": task_ado_id,
        })
    except _AdoApiError as exc:
        actions.append({
            "action": "create_work_item",
            "ok": False,
            "reason": "ADO_CREATE_REJECTED_BY_POLICY" if "403" in str(exc) else str(type(exc).__name__),
            "detail": str(exc)[:300],
        })
        _audit_create_child_task(
            correlation_id=correlation_id,
            ado_id=ado_id,
            user=user,
            completion_source=completion_source,
            operator_reason=operator_reason,
            pt_path=pending_task_path_str,
            ok=False,
            actions=actions,
            error=str(exc),
        )
        return jsonify({
            "ok": False,
            "dry_run": False,
            "epic_ado_id": ado_id,
            "task_ado_id": None,
            "task_url": None,
            "attachment_id": None,
            "actions": actions,
            "pending_task_consumed": False,
            "correlation_id": correlation_id,
        })

    # ── [3] upload_attachment ──────────────────────────────────────────────────
    if plan_exists and plan_path is not None:
        try:
            attach_result = ado.upload_attachment(
                file_path=plan_path,
                file_name="plan-de-pruebas.md",
            )
            attachment_id = attach_result.get("id") or attach_result.get("url", "")
            attach_url = attach_result.get("url", "")
            actions.append({
                "action": "upload_attachment",
                "ok": True,
                "attachment_id": attachment_id,
            })

            # ── [4] link_attachment_to_work_item ───────────────────────────────
            try:
                ado.link_attachment_to_work_item(
                    work_item_id=task_ado_id,
                    attachment_url=attach_url,
                    comment=f"Plan de pruebas - {pt_payload.get('rf_id', '')}",
                )
                actions.append({"action": "link_attachment", "ok": True})
            except _AdoApiError as exc:
                actions.append({
                    "action": "link_attachment",
                    "ok": False,
                    "reason": str(exc)[:300],
                })

        except _AdoApiError as exc:
            # Fallo de upload — Task creada pero adjunto no subido (degraded state CA-06)
            attachment_id = None
            attach_url = None
            actions.append({
                "action": "upload_attachment",
                "ok": False,
                "reason": "ATTACHMENT_UPLOAD_FAILED",
                "detail": str(exc)[:300],
            })
            human_action_required = (
                f"Task ADO-{task_ado_id} creada; subida de adjunto falló. "
                f"Reintentar o adjuntar plan-de-pruebas.md manualmente en ADO-{task_ado_id}."
            )
            # Registrar estado parcial en SystemLog con nivel WARNING
            _audit_create_child_task(
                correlation_id=correlation_id,
                ado_id=ado_id,
                user=user,
                completion_source=completion_source,
                operator_reason=operator_reason,
                pt_path=pending_task_path_str,
                ok=False,
                actions=actions,
                error=f"PARTIAL_FAILURE: Task {task_ado_id} creada, adjunto falló",
                level="WARNING",
            )
            return jsonify({
                "ok": False,
                "dry_run": False,
                "epic_ado_id": ado_id,
                "task_ado_id": task_ado_id,
                "task_url": task_url,
                "attachment_id": None,
                "actions": actions,
                "pending_task_consumed": False,
                "human_action_required": human_action_required,
                "correlation_id": correlation_id,
            })
    else:
        # Plan no existe — registrar como omitido
        actions.append({
            "action": "upload_attachment",
            "ok": False,
            "reason": "ATTACHMENT_FILE_NOT_FOUND",
            "detail": f"plan-de-pruebas.md no encontrado en {plan_rel}",
        })

    # ── [5] post_comment con operator_reason ──────────────────────────────────
    if operator_reason:
        try:
            comment_text = (
                f"<p><b>Creado desde Stacky Agents.</b></p>"
                f"<p><b>Motivo del operador:</b> {operator_reason}</p>"
                f"<p><em>correlation_id: {correlation_id}</em></p>"
            )
            ado.post_comment(task_ado_id, comment_text, fmt="html")
            actions.append({"action": "post_comment", "ok": True})
        except Exception as exc:
            logger.warning("create_child_task: post_comment falló (no crítico): %s", exc)
            actions.append({
                "action": "post_comment",
                "ok": False,
                "reason": str(exc)[:200],
            })

    # ── [6] Marcar pending-task.json como consumed ────────────────────────────
    _mark_pending_task_consumed(
        pt_file=pt_file,
        task_ado_id=task_ado_id,
        attachment_id=attachment_id,
        operator_reason=operator_reason,
    )
    actions.append({"action": "mark_consumed", "ok": True})

    # ── [7] Auditoría ─────────────────────────────────────────────────────────
    _audit_create_child_task(
        correlation_id=correlation_id,
        ado_id=ado_id,
        user=user,
        completion_source=completion_source,
        operator_reason=operator_reason,
        pt_path=pending_task_path_str,
        ok=True,
        actions=actions,
        task_ado_id=task_ado_id,
    )

    overall_ok = all(
        a.get("ok") for a in actions
        if a["action"] not in ("upload_attachment",)  # adjunto faltante no bloquea ok general
        or a.get("reason") != "ATTACHMENT_FILE_NOT_FOUND"
    )

    return jsonify({
        "ok": overall_ok,
        "dry_run": False,
        "epic_ado_id": ado_id,
        "task_ado_id": task_ado_id,
        "task_url": task_url,
        "attachment_id": attachment_id,
        "actions": actions,
        "pending_task_consumed": True,
        "idempotent": False,
        "correlation_id": correlation_id,
    })


# ── Helpers privados para create_child_task ───────────────────────────────────

def _mark_pending_task_consumed(
    pt_file: Path,
    task_ado_id: int,
    attachment_id: str | None,
    operator_reason: str,
) -> None:
    """Actualiza el pending-task.json en disco para marcarlo como consumido.

    Usa un threading.Lock a nivel proceso para garantizar exclusión mutua
    en Flask single-process. En multi-proceso (Gunicorn multi-worker) la
    protección es a nivel de OS file lock si portalocker está disponible.
    """
    import threading
    _FILE_LOCK = threading.Lock()

    with _FILE_LOCK:
        # Re-leer para detectar concurrent write (idempotencia defensiva)
        try:
            current = json.loads(pt_file.read_text(encoding="utf-8"))
        except Exception:
            current = {}

        if "consumed_at" in current:
            # Ya fue consumido por otra request concurrente — no sobreescribir
            return

        current["consumed_at"] = datetime.now(timezone.utc).isoformat()
        current["task_ado_id"] = task_ado_id
        current["attachment_id"] = attachment_id
        current["status"] = "consumed"
        if operator_reason:
            current["operator_reason"] = operator_reason

        pt_file.write_text(
            json.dumps(current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _audit_create_child_task(
    *,
    correlation_id: str,
    ado_id: int,
    user: str,
    completion_source: str,
    operator_reason: str,
    pt_path: str,
    ok: bool,
    actions: list[dict],
    task_ado_id: int | None = None,
    error: str | None = None,
    level: str = "INFO",
) -> None:
    """Persiste el evento de create_child_task en SystemLog (CA-07, CA-08)."""
    ctx = {
        "correlation_id": correlation_id,
        "ado_id": ado_id,
        "completion_source": completion_source,
        "operator_reason": operator_reason,
        "pending_task_path": pt_path,
        "task_ado_id": task_ado_id,
        "ok": ok,
        "actions_summary": [
            {"action": a["action"], "ok": a.get("ok")} for a in actions
        ],
    }
    if error:
        ctx["error"] = error[:500]

    tags = ["create_child_task", completion_source]
    if not ok:
        tags.append("partial_failure" if task_ado_id else "failure")
        if error:
            level = level or "WARNING"

    with session_scope() as session:
        log = SystemLog(
            level=level,
            source="create_child_task",
            action="create_child_task_succeeded" if ok else "create_child_task_failed",
            trigger="create_child_task",
            user=user,
            context_json=json.dumps(ctx, ensure_ascii=False, default=str),
            tags_json=json.dumps(tags),
        ) if _system_log_has_trigger() else SystemLog(
            level=level,
            source="create_child_task",
            action="create_child_task_succeeded" if ok else "create_child_task_failed",
            user=user,
            context_json=json.dumps(ctx, ensure_ascii=False, default=str),
            tags_json=json.dumps(tags),
        )
        session.add(log)


def _system_log_has_trigger() -> bool:
    """Detecta si SystemLog tiene el campo 'trigger' (compatibilidad con versiones anteriores)."""
    from models import SystemLog as _SL
    return hasattr(_SL, "trigger")
