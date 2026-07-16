"""api/local_llm_analysis.py — Plan 106 F3/F4 + Playground. Endpoints del modelo local (HITL, sin tools).

GET  /api/llm/local-health     → ping barato al servidor local (A1).
GET  /api/llm/local-models     → lista los modelos instalados en el server local.
POST /api/llm/analyze-code     → análisis de código (markdown).
POST /api/llm/suggest-pipeline → sugerencias de pipeline (F4).
POST /api/llm/playground       → prompt libre para probar el modelo local + selector de modelo.

analyze-code, suggest-pipeline y playground aceptan un `model` OPCIONAL en el body
que se reenvía a invoke_local_llm; si no viene, se usa el default de la flag LOCAL_LLM_MODEL.
"""
from __future__ import annotations

import json
from datetime import datetime

import requests
from flask import Blueprint, jsonify, request

import config as _config
from db import session_scope
from models import AgentExecution, Ticket

bp = Blueprint("local_llm_analysis", __name__, url_prefix="/llm")

# Discriminador de identidad del ticket interno (sin ADO real), patrón
# api/devops_agent.py:63-75: ado_id negativo compartido + external_id=-ticket.id único.
_LOCAL_LLM_ADO_ID = -5

_HITL_RULES = (
    "\n\nREGLA ABSOLUTA (HITL):\n"
    "- NUNCA ejecutes comandos.\n"
    "- NUNCA edites archivos.\n"
    "- NUNCA commitees cambios.\n"
    "- NUNCA sugieras comandos que muten el estado del repo.\n"
    "- Solo analizá, explicá y proponé; el operador humano decide qué aplicar.\n"
)


def _flag_off() -> bool:
    return not getattr(_config.config, "LOCAL_LLM_ENABLED", False)


def _guard():
    """404 si flag OFF; 503 si endpoint vacío; 400 si POST sin JSON."""
    if _flag_off():
        return jsonify({"error": "local_llm_disabled"}), 404
    if not getattr(_config.config, "LOCAL_LLM_ENDPOINT", ""):
        return jsonify({"error": "local_llm_endpoint_not_configured"}), 503
    if request.method == "POST" and not request.is_json:
        return jsonify({"error": "body_required_json"}), 400
    return None


def _ensure_internal_ticket(session, project: str) -> Ticket:
    """Busca/crea el ticket interno del modelo local para este proyecto.

    Copia el patrón de api/devops_agent.py:63-75: ado_id=-5 discriminador (sin unique),
    external_id negativo único (=-ticket.id, seteado post-flush) para no chocar con el
    UNIQUE ux_tickets_stacky_tracker_external ni con el backfill de db.py.
    """
    existing = (
        session.query(Ticket)
        .filter(Ticket.ado_id == _LOCAL_LLM_ADO_ID, Ticket.project == project)
        .first()
    )
    if existing:
        return existing
    ticket = Ticket(
        ado_id=_LOCAL_LLM_ADO_ID,
        project=project,
        stacky_project_name=project,
        title=f"[interno] Modelo local — {project}",
        work_item_type="Task",
        ado_state="Active",
    )
    session.add(ticket)
    session.flush()
    ticket.external_id = -ticket.id
    session.flush()
    return ticket


def _create_execution(session, ticket_id: int, agent_type: str, payload: dict) -> int:
    exec_row = AgentExecution(
        ticket_id=ticket_id,                       # NOT NULL (models.py:211)
        agent_type=agent_type,
        status="running",
        input_context_json=json.dumps(payload, ensure_ascii=False),  # NOT NULL (models.py:215)
        started_by="local_llm_api",                # NOT NULL (models.py:222)
        started_at=datetime.utcnow(),
    )
    exec_row.metadata_dict = {
        "backend": "local_llm",
        "model": getattr(_config.config, "LOCAL_LLM_MODEL", ""),
    }
    session.add(exec_row)
    session.flush()
    return exec_row.id


def _finish_execution(execution_id: int, *, status: str, output: str = "", error: str = "") -> None:
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


@bp.get("/local-health")
def local_health_route():
    """Ping barato (3s) al servidor local para que la UI muestre el estado. [A1]"""
    guard = _guard()
    if guard:
        return guard
    endpoint = _config.config.LOCAL_LLM_ENDPOINT
    # Derivar la base del server: para .../v1/chat/completions probamos .../v1/models.
    base = endpoint.split("/v1/")[0] if "/v1/" in endpoint else endpoint
    try:
        resp = requests.get(f"{base}/v1/models", timeout=3)
        reachable = resp.status_code == 200
    except requests.RequestException:
        reachable = False
    return jsonify({
        "ok": True,
        "reachable": reachable,
        "endpoint": endpoint,
        "model": _config.config.LOCAL_LLM_MODEL,
    })


def _parse_model_ids(raw) -> list[str]:
    """Parsea defensivamente la respuesta OpenAI-compatible de /v1/models.

    Ollama/LM Studio/vLLM devuelven {"data": [{"id": "..."}]}. Toleramos:
    - dict con "data" lista de dicts con "id" (forma OpenAI)
    - una lista directa de dicts con "id" o de strings
    Cualquier otra forma → [] (nunca lanza).
    """
    items = None
    if isinstance(raw, dict):
        items = raw.get("data")
    elif isinstance(raw, list):
        items = raw
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for it in items:
        if isinstance(it, dict):
            mid = it.get("id") or it.get("name")
        elif isinstance(it, str):
            mid = it
        else:
            mid = None
        if isinstance(mid, str) and mid.strip():
            out.append(mid.strip())
    return out


@bp.get("/local-models")
def local_models_route():
    """Lista los modelos instalados en el servidor local (OpenAI-compatible /v1/models).

    Nunca 500: si el server no responde o el JSON no tiene la forma esperada,
    devuelve models vacíos con reachable=false. `current` = el modelo default de la flag.
    """
    guard = _guard()
    if guard:
        return guard
    endpoint = _config.config.LOCAL_LLM_ENDPOINT
    base = endpoint.split("/v1/")[0] if "/v1/" in endpoint else endpoint
    models: list[str] = []
    reachable = False
    try:
        resp = requests.get(f"{base}/v1/models", timeout=5)
        reachable = resp.status_code == 200
        if reachable:
            try:
                models = _parse_model_ids(resp.json())
            except (ValueError, TypeError):
                models = []
    except requests.RequestException:
        reachable = False
    return jsonify({
        "ok": True,
        "reachable": reachable,
        "models": models,
        "current": _config.config.LOCAL_LLM_MODEL,
    })


@bp.post("/analyze-code")
def analyze_code_route():
    """Analiza código con el modelo local (sin tool use).

    Body: {"project": str (required), "stack": str (optional, default "generic"),
           "files": [{"path": str, "content": str}] (optional), "prompt": str (optional)}
    200: {"ok": true, "analysis": str, "model": str, "execution_id": int}
    """
    guard = _guard()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    if not project:
        return jsonify({"error": "project_required"}), 400
    stack = body.get("stack", "generic")
    files = body.get("files") or []
    custom_prompt = body.get("prompt") or ""

    system = (
        "Sos un ingeniero senior experto en análisis de código estático. "
        "Tu ÚNICA tarea es analizar y explicar en markdown." + _HITL_RULES
    )
    files_context = ""
    for f in files:
        files_context += f"\n--- {f.get('path', '')} ---\n{f.get('content', '')}\n"
    if files_context:
        files_context = "\n\n== ARCHIVOS ==\n" + files_context
    question = custom_prompt or "¿Qué observaciones tenés sobre este código?"
    user_prompt = (
        f'Analizá el código del proyecto "{project}" (stack: {stack}).'
        f"{files_context}\nPregunta del operador: {question}\n\n"
        "Respondé en markdown con secciones:\n"
        "1. Hallazgos (bugs, smells, riesgos)\n"
        "2. Sugerencias (refactors, patrones, mejores prácticas)\n"
        "3. Preguntas (para el operador)\n"
    )

    from copilot_bridge import invoke_local_llm  # import lazy (patrón del repo)

    with session_scope() as session:
        ticket = _ensure_internal_ticket(session, project)
        execution_id = _create_execution(
            session, ticket.id, "local_llm_analyzer",
            {"project": project, "stack": stack, "files": len(files)},
        )
    try:
        response = invoke_local_llm(
            agent_type="local_llm_analyzer",
            system=system,
            user=user_prompt,
            on_log=lambda level, msg: None,  # firma LogFn real (level, msg) — C3
            execution_id=execution_id,
            model=body.get("model"),  # opcional: selector por request (None = default flag)
        )
    except Exception as e:
        _finish_execution(execution_id, status="error", error=str(e))
        return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502
    _finish_execution(execution_id, status="completed", output=response.text)
    return jsonify({
        "ok": True,
        "analysis": response.text,
        "model": _config.config.LOCAL_LLM_MODEL,
        "execution_id": execution_id,
    })


@bp.post("/suggest-pipeline")
def suggest_pipeline_route():
    """Sugiere campos de pipeline con el modelo local (sin tool use).

    Body: {"project": str (required), "stack": str (required),
           "spec_partial": dict (optional)}
    200: {"ok": true, "suggestions": {working_directory, condition,
          environment_variables, justification}, "model": str, "execution_id": int}
    """
    guard = _guard()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    stack = body.get("stack")
    if not project or not stack:
        return jsonify({"error": "project_and_stack_required"}), 400
    spec_partial = body.get("spec_partial") or {}

    system = (
        "Sos un ingeniero DevOps senior experto en pipelines CI/CD. "
        "Tu ÚNICA tarea es sugerir campos de pipeline en formato JSON." + _HITL_RULES
    )
    spec_context = json.dumps(spec_partial, ensure_ascii=False, indent=2)
    user_prompt = (
        f'Dado el proyecto "{project}" (stack: {stack}) y el spec parcial:\n'
        f"== SPEC PARCIAL ==\n{spec_context}\n\n"
        "Sugerí valores para estos campos del pipeline:\n"
        "1. working_directory: directorio de trabajo relativo a la raíz del repo\n"
        "2. condition: condición (branch/tag) que dispara el pipeline\n"
        "3. environment_variables: variables de entorno sugeridas (dict JSON)\n\n"
        "Respondé EXCLUSIVAMENTE con un objeto JSON (sin markdown) con las keys:\n"
        '{"working_directory": "...", "condition": "...", '
        '"environment_variables": {"VAR": "valor"}, '
        '"justification": "explicación breve en castellano"}\n'
        "Si no estás seguro de un campo, dejalo vacío (string vacío o dict vacío).\n"
    )

    from copilot_bridge import invoke_local_llm

    with session_scope() as session:
        ticket = _ensure_internal_ticket(session, project)
        execution_id = _create_execution(
            session, ticket.id, "local_llm_pipeline_suggester",
            {"project": project, "stack": stack, "spec_partial": spec_partial},
        )
    try:
        response = invoke_local_llm(
            agent_type="local_llm_pipeline_suggester",
            system=system,
            user=user_prompt,
            on_log=lambda level, msg: None,
            execution_id=execution_id,
            model=body.get("model"),  # opcional: selector por request (None = default flag)
        )
    except Exception as e:
        _finish_execution(execution_id, status="error", error=str(e))
        return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502

    text = response.text.strip()
    if text.startswith("```"):
        # Quitar fence markdown (```json ... ```)
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) >= 3 else text
    try:
        suggestions = json.loads(text)
    except json.JSONDecodeError as e:
        _finish_execution(execution_id, status="error", error=f"JSON parse error: {e}")
        return jsonify({
            "ok": False,
            "error": "json_parse_error",
            "message": "El modelo no devolvió JSON válido; reintentá.",
            "raw_response": response.text[:500],
            "execution_id": execution_id,
        }), 502
    _finish_execution(execution_id, status="completed", output=text)
    return jsonify({
        "ok": True,
        "suggestions": suggestions,
        "model": _config.config.LOCAL_LLM_MODEL,
        "execution_id": execution_id,
    })


_PLAYGROUND_PROJECT = "__local_llm_playground__"

_PLAYGROUND_DEFAULT_SYSTEM = (
    "Sos un asistente técnico útil que responde en markdown claro y conciso."
    + _HITL_RULES
)


@bp.post("/playground")
def playground_route():
    """Prompt libre para PROBAR el modelo local (HITL, sin tool use).

    Body: {"prompt": str (required), "model": str (optional), "system": str (optional)}
    200: {"ok": true, "response": str, "model": str, "execution_id": int}
    Errores del endpoint local → 502 con mensaje accionable (patrón analyze-code).
    """
    guard = _guard()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt_required"}), 400
    system = (body.get("system") or "").strip() or _PLAYGROUND_DEFAULT_SYSTEM
    model = body.get("model")

    from copilot_bridge import invoke_local_llm  # import lazy (patrón del repo)

    with session_scope() as session:
        ticket = _ensure_internal_ticket(session, _PLAYGROUND_PROJECT)
        execution_id = _create_execution(
            session, ticket.id, "local_llm_playground",
            {"prompt_chars": len(prompt), "model": model or _config.config.LOCAL_LLM_MODEL},
        )
    try:
        response = invoke_local_llm(
            agent_type="local_llm_playground",
            system=system,
            user=prompt,
            on_log=lambda level, msg: None,
            execution_id=execution_id,
            model=model,
        )
    except Exception as e:
        _finish_execution(execution_id, status="error", error=str(e))
        return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502
    _finish_execution(execution_id, status="completed", output=response.text)
    resolved_model = (response.metadata or {}).get("model") or model or _config.config.LOCAL_LLM_MODEL
    return jsonify({
        "ok": True,
        "response": response.text,
        "model": resolved_model,
        "execution_id": execution_id,
    })


# ── Análisis de estado de ticket con IA local ────────────────────────────────
# Reúne TODO el contexto del ticket (épica padre, tasks hijas, comentarios del
# tracker y outputs de agentes) y le pide al modelo local un diagnóstico:
# resumen de estado, puntos débiles e incoherencias entre agentes. HITL puro.

_TICKET_INSIGHT_MAX_DESC = 3000
_TICKET_INSIGHT_MAX_COMMENTS = 15
_TICKET_INSIGHT_MAX_COMMENT_CHARS = 800
_TICKET_INSIGHT_MAX_EXECUTIONS = 10
_TICKET_INSIGHT_MAX_OUTPUT_CHARS = 1500

_TICKET_INSIGHT_SYSTEM = (
    "Sos un PM técnico senior y auditor de calidad de un equipo de agentes IA. "
    "Analizás el estado real de tickets con mirada crítica: detectás huecos, "
    "riesgos y contradicciones entre lo que dicen los distintos agentes, los "
    "comentarios y el estado del ticket. Respondés en castellano, en markdown."
    + _HITL_RULES
)


def _clip(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + " …[truncado]"


def _fetch_ticket_comments_safe(ticket) -> list[dict]:
    """Comentarios del tracker, best-effort: cualquier error → [] (nunca rompe)."""
    if (ticket.ado_id or 0) <= 0:
        return []
    try:
        from api.tickets import _ado_client_for_ticket, _provider_for_ticket
        from services.ado_sync import _html_to_text

        provider = _provider_for_ticket(ticket=ticket)
        if provider is not None:
            raw = provider.fetch_comments(str(ticket.ado_id))
        else:
            raw = _ado_client_for_ticket(ticket=ticket).fetch_comments(ticket.ado_id)
        return [
            {
                "author": c.get("author", ""),
                "date": c.get("date", ""),
                "text": _html_to_text(c.get("text", "")),
            }
            for c in raw
            if c.get("text")
        ]
    except Exception:
        return []


def _ticket_line(t) -> str:
    return (
        f"- [{t.work_item_type or 'Item'} ADO-{t.ado_id}] \"{t.title}\" · "
        f"estado ADO: {t.ado_state or '—'} · estado Stacky: {t.stacky_status or 'idle'}"
        + (f" · asignado: {t.assigned_to_ado}" if t.assigned_to_ado else "")
    )


def _build_ticket_insight_context(session, ticket) -> tuple[str, dict]:
    """Arma el contexto textual (épica + ticket + hijas + comentarios + agentes).

    Devuelve (texto, stats) con truncados defensivos para no reventar la ventana
    de contexto del modelo local.
    """
    parts: list[str] = []

    parts.append("== TICKET ==")
    parts.append(_ticket_line(ticket))
    if ticket.description:
        parts.append(f"Descripción:\n{_clip(ticket.description, _TICKET_INSIGHT_MAX_DESC)}")

    epic = None
    if ticket.parent_ado_id:
        epic = (
            session.query(Ticket)
            .filter(Ticket.ado_id == ticket.parent_ado_id, Ticket.project == ticket.project)
            .first()
        )
    if epic is not None:
        parts.append("\n== ÉPICA / PADRE ==")
        parts.append(_ticket_line(epic))
        if epic.description:
            parts.append(f"Descripción:\n{_clip(epic.description, _TICKET_INSIGHT_MAX_DESC // 2)}")

    children = []
    if (ticket.ado_id or 0) > 0:
        children = (
            session.query(Ticket)
            .filter(Ticket.parent_ado_id == ticket.ado_id, Ticket.project == ticket.project)
            .order_by(Ticket.ado_id)
            .all()
        )
    if children:
        parts.append(f"\n== TASKS/HIJAS ({len(children)}) ==")
        for child in children:
            parts.append(_ticket_line(child))

    comments = _fetch_ticket_comments_safe(ticket)
    if comments:
        recent = comments[:_TICKET_INSIGHT_MAX_COMMENTS]
        parts.append(f"\n== COMENTARIOS DEL TRACKER ({len(recent)} de {len(comments)}) ==")
        for c in recent:
            parts.append(
                f"- [{c['date']}] {c['author']}: {_clip(c['text'], _TICKET_INSIGHT_MAX_COMMENT_CHARS)}"
            )
    else:
        parts.append("\n== COMENTARIOS DEL TRACKER ==\n(sin comentarios o tracker no accesible)")

    scope_ids = [ticket.id] + [c.id for c in children]
    executions = (
        session.query(AgentExecution)
        .filter(AgentExecution.ticket_id.in_(scope_ids))
        .order_by(AgentExecution.started_at.desc())
        .limit(_TICKET_INSIGHT_MAX_EXECUTIONS)
        .all()
    )
    if executions:
        parts.append(f"\n== EJECUCIONES DE AGENTES ({len(executions)} más recientes) ==")
        for ex in reversed(executions):  # cronológico para que el modelo siga la historia
            started = ex.started_at.isoformat() if ex.started_at else "—"
            header = (
                f"--- Ejecución #{ex.id} · agente: {ex.agent_type} · estado: {ex.status}"
                + (f" · veredicto: {ex.verdict}" if ex.verdict else "")
                + f" · {started} ---"
            )
            parts.append(header)
            if ex.error_message:
                parts.append(f"Error: {_clip(ex.error_message, 500)}")
            if ex.output:
                parts.append(_clip(ex.output, _TICKET_INSIGHT_MAX_OUTPUT_CHARS))
    else:
        parts.append("\n== EJECUCIONES DE AGENTES ==\n(sin ejecuciones registradas)")

    stats = {
        "has_epic": epic is not None,
        "children": len(children),
        "comments": len(comments),
        "executions": len(executions),
    }
    return "\n".join(parts), stats


@bp.post("/ticket-insight/<int:ticket_id>")
def ticket_insight_route(ticket_id: int):
    """Analiza el estado de un ticket con el modelo local (HITL, sin tools).

    Body opcional: {"model": str, "question": str}
    200: {"ok": true, "analysis": str, "model": str, "execution_id": int,
          "context_stats": {...}} | 404 ticket inexistente | 502 fallo del modelo.
    """
    guard = _guard()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()

    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            return jsonify({"error": "ticket_not_found"}), 404
        context_text, stats = _build_ticket_insight_context(session, ticket)
        execution_id = _create_execution(
            session, ticket.id, "local_llm_ticket_insight",
            {"ticket_id": ticket.id, "ado_id": ticket.ado_id, **stats},
        )

    user_prompt = (
        "Analizá el estado REAL del siguiente ticket usando TODO su contexto "
        "(épica padre, tasks hijas, comentarios del tracker y resultados de los "
        "agentes que trabajaron sobre él).\n\n"
        f"{context_text}\n\n"
        + (f"Pregunta puntual del operador: {question}\n\n" if question else "")
        + "Respondé en markdown con EXACTAMENTE estas secciones:\n"
        "## Resumen del estado\n"
        "(2-5 oraciones: dónde está parado el ticket hoy)\n"
        "## Puntos débiles y riesgos\n"
        "(lista concreta; si un agente dejó algo a medias o sin verificar, nombralo)\n"
        "## Incoherencias detectadas\n"
        "(contradicciones entre outputs de agentes, comentarios y estados; "
        "si no encontrás ninguna, decilo explícitamente)\n"
        "## Próximos pasos sugeridos\n"
        "(acciones concretas priorizadas; el operador decide)\n"
    )

    from copilot_bridge import invoke_local_llm  # import lazy (patrón del repo)

    try:
        response = invoke_local_llm(
            agent_type="local_llm_ticket_insight",
            system=_TICKET_INSIGHT_SYSTEM,
            user=user_prompt,
            on_log=lambda level, msg: None,
            execution_id=execution_id,
            model=body.get("model"),
        )
    except Exception as e:
        _finish_execution(execution_id, status="error", error=str(e))
        return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502
    _finish_execution(execution_id, status="completed", output=response.text)
    resolved_model = (response.metadata or {}).get("model") or _config.config.LOCAL_LLM_MODEL
    return jsonify({
        "ok": True,
        "analysis": response.text,
        "model": resolved_model,
        "execution_id": execution_id,
        "context_stats": stats,
    })


@bp.post("/insights/<int:execution_id>/generate")
def generate_insight_route(execution_id: int):
    """Plan 117 — Genera/regenera el insight local de UNA ejecución (acción HITL).

    Ruta: POST /api/llm/insights/<id>/generate. 404 flag master OFF | 404 execution
    inexistente | 409 excluida | 502 fallo del modelo | 400 POST sin body JSON (_guard).
    """
    guard = _guard()  # 404 LOCAL_LLM_ENABLED OFF / 503 endpoint vacío / 400 sin JSON
    if guard:
        return guard
    if not getattr(_config.config, "STACKY_LOCAL_INSIGHTS_ENABLED", False):
        return jsonify({"error": "local_insights_disabled"}), 404

    from services.local_insights import generate_insight_for_execution

    result = generate_insight_for_execution(execution_id, force=True)
    if result.get("ok"):
        return jsonify(result)
    err = result.get("error")
    if err == "execution_not_found":
        return jsonify(result), 404
    if err == "insight_excluded":
        return jsonify(result), 409
    # Plan 148 F5(a) — degradacion explicita: si la generacion fallo porque el
    # modelo local esta caido/no instalado, NO 502 (rompe la UI). Responder 200
    # available:false. `_config` en este archivo es el MODULO (`import config as
    # _config`, :20) -> se lee por `_config.config` (mismo patron ya usado en
    # este archivo, ver :626/:41/:48).
    if getattr(_config.config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True):
        from services.local_insights import _local_llm_reachable
        if not _local_llm_reachable():
            from services import integration_breaker as _brk
            _brk.record_failure(
                "local_llm", None, _brk.REASON_LOCAL_LLM_DOWN,
                "El modelo local no está disponible (servidor caído o modelo no instalado).",
            )
            return jsonify({
                "ok": False, "available": False, "reason": _brk.REASON_LOCAL_LLM_DOWN,
                "message": "El modelo local no está disponible. Verificá que Ollama/servidor local esté corriendo.",
                "execution_id": execution_id,
            }), 200
    return jsonify(result), 502
