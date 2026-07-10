"""api/pr_review.py — Plan 110. Revisor de PRs (Haiku solo-lectura + modelo local).

url_prefix SIN /api (patrón devops_production.py:9). Gate por STACKY_PR_REVIEWER_ENABLED.
Endpoints:
  GET  /api/pr-review/list          → lista PRs abiertas del tracker activo (F2)
  GET  /api/pr-review/detail        → detalle + diff SANEADO (F3)
  POST /api/pr-review/review/haiku  → revisión Haiku solo-lectura (F4)
  GET  /api/pr-review/models        → catálogo de modelos Copilot (F4bis)
  POST /api/pr-review/review/local  → revisión con modelo local, contexto completo (F5)
  GET  /api/pr-review/actions       → acciones soportadas por el tracker (F6)
  POST /api/pr-review/execute       → ejecuta la acción confirmada por el humano (F6)

Guardarraíles: nunca 500 (patrón _call_provider), el diff crudo NUNCA se persiste
(solo metadatos), y el modelo SOLO propone (HITL).
"""
from __future__ import annotations

import json
from datetime import datetime

from flask import Blueprint, abort, request, jsonify
from werkzeug.exceptions import HTTPException

import config as _config
from services.merge_request_provider import get_merge_request_provider
from services.tracker_provider import TrackerConfigError, TrackerApiError
from services.pr_review_sanitize import sanitize_diff

bp = Blueprint("pr_review", __name__, url_prefix="/pr-review")

# Discriminador de ticket interno (patrón local_llm_analysis.py:28). -5 es del Plan 106.
_PR_REVIEW_ADO_ID = -6

_REVIEW_HITL = (
    "\n\nREGLA ABSOLUTA (solo-lectura):\n"
    "- NUNCA ejecutes comandos, no edites archivos, no commitees, no mergees.\n"
    "- Vos SOLO analizás y recomendás UNA acción; el humano decide y aprieta el botón.\n"
    "- La acción recomendada DEBE ser una de: approve, comment, request_changes, merge, close, none.\n"
)

_ALWAYS_ACTIONS = ("none", "comment", "request_changes", "merge", "close")


def _flag_off() -> bool:
    return not getattr(_config.config, "STACKY_PR_REVIEWER_ENABLED", False)


def _guard():
    if _flag_off():
        abort(404)
    if request.method in ("POST", "PUT", "DELETE") and not request.is_json:
        abort(400, description="Content-Type application/json requerido")


def _call_provider(fn):
    try:
        return fn()
    except TrackerConfigError as e:
        return {"error": str(e), "kind": "tracker_config"}, 400
    except TrackerApiError as e:
        return {"error": str(e), "kind": e.kind}, e.status or 502
    except HTTPException:
        raise
    except Exception:
        return {"error": "error interno del revisor de PRs"}, 500


# ── Persistencia (solo metadatos; NUNCA el diff crudo — guardarraíl 7) ──────────
def _ensure_internal_ticket(session, project: str):
    from models import Ticket  # noqa: PLC0415
    existing = (
        session.query(Ticket)
        .filter(Ticket.ado_id == _PR_REVIEW_ADO_ID, Ticket.project == project)
        .first()
    )
    if existing:
        return existing
    ticket = Ticket(
        ado_id=_PR_REVIEW_ADO_ID,
        project=project,
        stacky_project_name=project,
        title=f"[interno] Revisor de PRs — {project}",
        work_item_type="Task",
        ado_state="Active",
    )
    session.add(ticket)
    session.flush()
    ticket.external_id = -ticket.id
    session.flush()
    return ticket


def _create_execution(session, ticket_id: int, agent_type: str, payload: dict) -> int:
    from models import AgentExecution  # noqa: PLC0415
    exec_row = AgentExecution(
        ticket_id=ticket_id,
        agent_type=agent_type,
        status="running",
        input_context_json=json.dumps(payload, ensure_ascii=False),  # SOLO metadatos
        started_by="pr_review_api",
        started_at=datetime.utcnow(),
    )
    exec_row.metadata_dict = {"backend": "pr_review"}
    session.add(exec_row)
    session.flush()
    return exec_row.id


def _finish_execution(execution_id: int, *, status: str, output: str = "", error: str = "") -> None:
    from db import session_scope  # noqa: PLC0415
    from models import AgentExecution  # noqa: PLC0415
    with session_scope() as session:
        exec_row = session.query(AgentExecution).filter_by(id=execution_id).first()
        if not exec_row:
            return
        exec_row.status = status
        exec_row.completed_at = datetime.utcnow()
        if output:
            exec_row.output = output[:10000]
        if error:
            exec_row.error_message = error[:500]


def _build_review_context(meta: dict, files: list, diff_text: str, title: str, description: str) -> str:
    lines = [
        f"Título: {title}",
        f"Descripción: {description or '(sin descripción)'}",
        f"Rama origen → destino: {meta.get('source_branch','?')} → {meta.get('target_branch','?')}",
        f"Estado: {meta.get('state','?')} | Pipeline: {meta.get('pipeline_status','?')} | Mergeable: {meta.get('mergeable', '?')}",
        "Archivos cambiados:",
    ] + [f"  - {f['path']} ({f['change_type']})" for f in files]
    lines.append("\n== DIFF (saneado, puede estar truncado) ==\n" + (diff_text or "(no disponible)"))
    return "\n".join(lines)


def _parse_review_json(text: str) -> dict:
    """Parser defensivo: quita fence ```; coerce acción inválida → 'none'."""
    _valid = {"approve", "comment", "request_changes", "merge", "close", "none"}
    raw = (text or "").strip()
    if raw.startswith("```"):
        parts = raw.split("\n")
        raw = "\n".join(parts[1:-1]) if len(parts) >= 3 else raw
    try:
        review = json.loads(raw)
        if not isinstance(review, dict):
            raise ValueError("no es objeto")
    except (ValueError, TypeError):
        return {
            "summary": (text or "")[:2000],
            "findings": [],
            "recommended_action": {"type": "none", "label": "Revisar manualmente", "params": {}},
            "confidence": 0.0,
        }
    action = review.get("recommended_action") or {}
    if not isinstance(action, dict) or action.get("type") not in _valid:
        review["recommended_action"] = {"type": "none", "label": "Revisar manualmente", "params": {}}
    review.setdefault("summary", "")
    review.setdefault("findings", [])
    review.setdefault("confidence", 0.0)
    return review


@bp.get("/list")
def list_prs():
    """GET /pr-review/list?project=<name>&state=<open|merged|closed|all>."""
    _guard()

    def _do():
        project = request.args.get("project")
        state = request.args.get("state", "open")
        provider = get_merge_request_provider(project)
        return {"provider": provider.name, "merge_requests": provider.list_merge_requests(state)}

    return _call_provider(_do)


@bp.get("/detail")
def detail_pr():
    """GET /pr-review/detail?project=<name>&mr_id=<id>. Devuelve meta + diff saneado."""
    _guard()

    def _do():
        project = request.args.get("project")
        mr_id = request.args.get("mr_id")
        if not mr_id:
            abort(400, description="mr_id requerido")
        provider = get_merge_request_provider(project)
        meta = provider.get_merge_request(mr_id)
        diff = provider.get_merge_request_diff(mr_id)
        cap = int(getattr(_config.config, "STACKY_PR_REVIEW_DIFF_MAX_CHARS", 60000))
        sanitized, truncated = sanitize_diff(diff.get("diff_text", ""), cap)
        return {
            "id": str(mr_id),
            "meta": meta,
            "files": diff.get("files", []),
            "diff_text": sanitized,  # SANEADO
            "diff_truncated": truncated,
            "diff_available": diff.get("diff_available", False),
            "note": diff.get("note", ""),
        }

    return _call_provider(_do)


@bp.post("/review/haiku")
def review_haiku():
    """POST /pr-review/review/haiku  Body: {project, mr_id}."""
    _guard()
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    mr_id = body.get("mr_id")
    if not mr_id:
        return jsonify({"error": "mr_id_required"}), 400

    model = getattr(_config.config, "STACKY_PR_REVIEW_HAIKU_MODEL", "")
    if "haiku" not in (model or "").lower():
        return jsonify({"error": "model_not_haiku",
                        "message": "El modelo configurado no es un Haiku. Corregilo en el panel del Arnés."}), 400

    def _fetch():
        provider = get_merge_request_provider(project)
        meta = provider.get_merge_request(mr_id)
        diff = provider.get_merge_request_diff(mr_id)
        cap = int(getattr(_config.config, "STACKY_PR_REVIEW_DIFF_MAX_CHARS", 60000))
        sanitized, truncated = sanitize_diff(diff.get("diff_text", ""), cap)
        return meta, diff, sanitized, truncated

    fetched = _call_provider(_fetch)
    if isinstance(fetched, tuple) and len(fetched) == 2 and isinstance(fetched[1], int):
        return fetched  # (error_dict, status)
    meta, diff, sanitized, truncated = fetched

    system = (
        "Sos un revisor de código senior. Tu ÚNICA tarea es revisar el pedido de "
        "cambios y responder EXCLUSIVAMENTE con un objeto JSON (sin markdown)." + _REVIEW_HITL +
        '\nFormato EXACTO: {"summary": str, '
        '"findings": [{"severity": "info"|"warning"|"critical", "title": str, "detail": str}], '
        '"recommended_action": {"type": "approve"|"comment"|"request_changes"|"merge"|"close"|"none", '
        '"label": str, "params": {}}, "confidence": 0..1}'
    )
    user = _build_review_context(meta, diff.get("files", []), sanitized,
                                 body.get("title") or "", body.get("description") or "")

    from db import session_scope  # noqa: PLC0415
    with session_scope() as session:
        ticket = _ensure_internal_ticket(session, project or "__pr_review__")
        execution_id = _create_execution(session, ticket.id, "pr_review_haiku",
            {"mr_id": str(mr_id), "diff_chars": len(sanitized), "diff_truncated": truncated, "model": model})

    from copilot_bridge import invoke_haiku  # noqa: PLC0415
    try:
        _timeout = int(getattr(_config.config, "STACKY_PR_REVIEW_TIMEOUT_SEC", 120))
        resp = invoke_haiku(agent_type="pr_review_haiku", system=system, user=user,
                            on_log=lambda level, msg: None, execution_id=execution_id,
                            model=model, timeout=_timeout)
    except Exception as e:
        _finish_execution(execution_id, status="error", error=str(e))
        return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502

    review = _parse_review_json(resp.text)
    _finish_execution(execution_id, status="completed", output=json.dumps(review, ensure_ascii=False))
    return jsonify({"ok": True, "review": review, "model": model,
                    "diff_truncated": truncated, "diff_available": diff.get("diff_available", False),
                    "execution_id": execution_id})


@bp.get("/models")
def copilot_models():
    """GET /pr-review/models — catálogo de modelos Copilot (para elegir el id Haiku). Gateado."""
    _guard()

    def _do():
        import copilot_bridge  # noqa: PLC0415  (import diferido, patrón pm.py)
        try:
            raw = copilot_bridge.list_copilot_models()
        except Exception as e:  # noqa: BLE001
            return {"error": "copilot_models_unavailable",
                    "message": f"No se pudo listar modelos de Copilot: {e}"}, 502
        models = [{"id": m.get("id") or "",
                   "name": m.get("name") or (m.get("id") or ""),
                   "is_haiku": "haiku" in (m.get("id") or "").lower()}
                  for m in (raw or []) if m.get("id")]
        return {"models": models,
                "configured": getattr(_config.config, "STACKY_PR_REVIEW_HAIKU_MODEL", "")}

    return _call_provider(_do)


@bp.post("/review/local")
def review_local():
    """POST /pr-review/review/local  Body: {project, mr_id, question?}."""
    _guard()
    if not getattr(_config.config, "LOCAL_LLM_ENABLED", False):
        return jsonify({"error": "local_llm_disabled",
                        "message": "Activá el modelo local en el panel del Arnés para usar esta revisión."}), 400
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    mr_id = body.get("mr_id")
    if not mr_id:
        return jsonify({"error": "mr_id_required"}), 400
    question = (body.get("question") or "").strip()

    def _fetch():
        provider = get_merge_request_provider(project)
        meta = provider.get_merge_request(mr_id)
        diff = provider.get_merge_request_diff(mr_id)
        # v2.1 — camino SOLO-LOCAL: cap propio (velocidad/ventana), NO el de privacidad
        # de Haiku. 0 = sin límite → contexto COMPLETO. sanitize_diff sigue redactando
        # secretos; truncate() con cap<=0 NO trunca (services/pr_review_sanitize.py).
        cap = int(getattr(_config.config, "STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS", 200000))
        sanitized, truncated = sanitize_diff(diff.get("diff_text", ""), cap)
        return meta, diff, sanitized, truncated

    fetched = _call_provider(_fetch)
    if isinstance(fetched, tuple) and len(fetched) == 2 and isinstance(fetched[1], int):
        return fetched
    meta, diff, sanitized, truncated = fetched

    system = ("Sos un revisor de código senior. Analizá el pedido de cambios y respondé "
              "en markdown claro." + _REVIEW_HITL)
    context = _build_review_context(meta, diff.get("files", []), sanitized,
                                    body.get("title") or "", body.get("description") or "")
    user = (context + "\n\n== PREGUNTA DEL OPERADOR ==\n" +
            (question or "Dame un resumen de lo que hace esta PR, riesgos y qué acción recomendás "
                         "(approve/comment/request_changes/merge/close/none)."))

    from db import session_scope  # noqa: PLC0415
    with session_scope() as session:
        ticket = _ensure_internal_ticket(session, project or "__pr_review__")
        execution_id = _create_execution(session, ticket.id, "pr_review_local",
            {"mr_id": str(mr_id), "diff_chars": len(sanitized), "diff_truncated": truncated,
             "has_question": bool(question)})

    from copilot_bridge import invoke_local_llm  # noqa: PLC0415
    try:
        resp = invoke_local_llm(agent_type="pr_review_local", system=system, user=user,
                                on_log=lambda level, msg: None, execution_id=execution_id,
                                model=body.get("model"))
    except Exception as e:
        _finish_execution(execution_id, status="error", error=str(e))
        return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502
    _finish_execution(execution_id, status="completed", output=resp.text)
    return jsonify({"ok": True, "answer": resp.text,
                    "model": (resp.metadata or {}).get("model") or getattr(_config.config, "LOCAL_LLM_MODEL", ""),
                    "diff_truncated": truncated, "diff_available": diff.get("diff_available", False),
                    "execution_id": execution_id})


@bp.get("/actions")
def available_actions():
    """GET /pr-review/actions?project= — qué acciones soporta el tracker activo (capability)."""
    _guard()

    def _do():
        provider = get_merge_request_provider(request.args.get("project"))
        actions = list(_ALWAYS_ACTIONS)
        if hasattr(provider, "approve_merge_request"):
            actions.append("approve")
        return {"provider": provider.name, "actions": actions}

    return _call_provider(_do)


@bp.post("/execute")
def execute_action():
    """POST /pr-review/execute Body: {project, mr_id, action, body?, confirm, confirm_merge?}."""
    _guard()
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    mr_id = body.get("mr_id")
    action = body.get("action")
    if not mr_id:
        return jsonify({"error": "mr_id_required"}), 400
    if action == "none":
        return jsonify({"ok": True, "action": "none", "result": {"noop": True}})
    if action not in ("comment", "request_changes", "merge", "close", "approve"):
        return jsonify({"error": "action_not_allowed", "message": f"Acción no permitida: {action}"}), 400
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm_required", "message": "confirm=true requerido"}), 400
    if action == "merge" and body.get("confirm_merge") is not True:
        return jsonify({"error": "confirm_merge_required",
                        "message": "Para mergear tenés que marcar la casilla de confirmación fuerte."}), 400
    if action in ("comment", "request_changes") and not (body.get("body") or "").strip():
        return jsonify({"error": "body_required", "message": "El comentario no puede estar vacío"}), 400

    def _do():
        provider = get_merge_request_provider(project)
        if action == "comment":
            return {"ok": True, "action": action, "result": provider.comment_merge_request(mr_id, body["body"])}
        if action == "request_changes":
            return {"ok": True, "action": action,
                    "result": provider.comment_merge_request(mr_id, "Cambios solicitados:\n" + body["body"])}
        if action == "merge":
            return {"ok": True, "action": action, "result": provider.merge_merge_request(mr_id)}
        if action == "close":
            return {"ok": True, "action": action, "result": provider.close_merge_request(mr_id)}
        if action == "approve":
            if not hasattr(provider, "approve_merge_request"):
                abort(400, description="El tracker activo no soporta aprobar PRs")
            return {"ok": True, "action": action, "result": provider.approve_merge_request(mr_id)}
        abort(400, description="acción no soportada")

    return _call_provider(_do)
