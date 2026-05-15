import logging

from flask import Blueprint, abort, jsonify, request

import fingerprint
from db import session_scope
from models import AgentExecution, Ticket
from services import glossary
from services.ado_sync import (
    AdoApiError,
    AdoConfigError,
    get_last_sync_at,
    sync_tickets,
)
from services.pipeline_status import get_pipeline_status, get_pipeline_summary
from services.ado_pipeline_inference import infer_pipeline, invalidate_cache

logger = logging.getLogger("stacky_agents.api.tickets")

bp = Blueprint("tickets", __name__, url_prefix="/tickets")


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

    # ── Auto-publish server-side ──────────────────────────────────────────────
    # Decisión arquitectónica: el agente NO controla si se publica.
    # Stacky publica automáticamente cuando se cumplen TODAS las precondiciones:
    #   1. status == "completed"
    #   2. html_output_path presente en el body (el agente siempre lo manda)
    #   3. AgentExecution válida encontrada en BD
    #   4. STACKY_LEGACY_AUTO_PUBLISH != "off" (default "on")
    #
    # Si STACKY_LEGACY_AUTO_PUBLISH="off" → publish.skipped(reason="legacy_auto_publish_disabled")
    # Si falla → publish.failed registrado, PATCH response sigue siendo OK.
    publish_result: dict

    if new_status != "completed":
        publish_result = {"skipped": True, "reason": "status_not_completed"}
    elif legacy_auto_publish == "off":
        publish_result = {"skipped": True, "reason": "legacy_auto_publish_disabled"}
        logger.info(
            "set_stacky_status_by_ado: publish.skipped(legacy_auto_publish_disabled) — "
            "ADO-%s corr=%s",
            ado_id, correlation_id,
        )
    elif not html_output_path:
        publish_result = {"skipped": True, "reason": "html_output_path_missing"}
    elif last_exec is None:
        publish_result = {"skipped": True, "reason": "no_execution_found"}
        logger.warning(
            "set_stacky_status_by_ado: publish.skipped(no_execution_found) — "
            "ADO-%s html_output_path=%s corr=%s",
            ado_id, html_output_path, correlation_id,
        )
    else:
        logger.info(
            "set_stacky_status_by_ado: publish.attempted — "
            "ADO-%s exec=%d html=%s corr=%s",
            ado_id, last_exec.id, html_output_path, correlation_id,
        )
        try:
            from services.ado_publisher import publish_from_execution
            pr = publish_from_execution(last_exec.id, triggered_by="legacy_auto_publish")
            if pr.ok:
                publish_result = {
                    "ok": True,
                    "status": pr.status,
                    "ado_id": pr.ado_id,
                    "execution_id": pr.execution_id,
                    "html_sha256": pr.html_sha256,
                    "ado_response": pr.ado_response,
                    "record_id": pr.record_id,
                    "event": "publish.succeeded",
                }
                logger.info(
                    "set_stacky_status_by_ado: publish.succeeded — "
                    "ADO-%s exec=%d status=%s corr=%s",
                    ado_id, last_exec.id, pr.status, correlation_id,
                )
            else:
                publish_result = {
                    "ok": False,
                    "status": pr.status,
                    "reason": pr.reason,
                    "execution_id": pr.execution_id,
                    "event": "publish.failed",
                }
                logger.warning(
                    "set_stacky_status_by_ado: publish.failed — "
                    "ADO-%s exec=%d reason=%s corr=%s",
                    ado_id, last_exec.id, pr.reason, correlation_id,
                )
        except Exception as pub_exc:
            publish_result = {
                "ok": False,
                "reason": str(pub_exc),
                "type": type(pub_exc).__name__,
                "event": "publish.failed",
            }
            logger.exception(
                "set_stacky_status_by_ado: publish raised exception — "
                "ADO-%s exec=%d corr=%s",
                ado_id, last_exec.id if last_exec else "?", correlation_id,
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
        exec_hint = last_exec.html_output_path if last_exec else None

    if current_stacky == "completed":
        return jsonify({
            "ok": False,
            "error": "ticket ya está en stacky_status='completed'",
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
