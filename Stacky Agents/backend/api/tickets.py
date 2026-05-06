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
