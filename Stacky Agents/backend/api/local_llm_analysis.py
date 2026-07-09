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
