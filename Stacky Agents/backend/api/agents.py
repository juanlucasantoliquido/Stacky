from flask import Blueprint, abort, jsonify, request

import agent_runner
import agents
import contract_validator
from config import config
from services import cost_estimator, delta_prompt, llm_router, next_agent, output_cache, vscode_agents
from ._helpers import current_user

bp = Blueprint("agents", __name__, url_prefix="/agents")


@bp.get("")
def list_agents_route():
    return jsonify(agents.list_agents())


@bp.get("/vscode")
def list_vscode_agents():
    """Devuelve los .agent.md del directorio de prompts de VS Code (GitHub Copilot)."""
    found = vscode_agents.list_agents(config.VSCODE_PROMPTS_DIR)
    return jsonify([a.to_dict() for a in found])


@bp.post("/run")
def run():
    payload = request.get_json(force=True, silent=True) or {}
    agent_type = payload.get("agent_type")
    ticket_id = payload.get("ticket_id")
    context_blocks = payload.get("context_blocks") or []
    chain_from = payload.get("chain_from") or []

    if not agent_type:
        abort(400, "agent_type is required")
    if not ticket_id:
        abort(400, "ticket_id is required")
    if agent_type == "custom" and not payload.get("system_prompt_override"):
        abort(400, "system_prompt_override is required when agent_type=custom")

    # FA-32 — Diff-based re-execution
    delta_system_prefix: str | None = None
    prev_exec_id = payload.get("previous_execution_id")
    if prev_exec_id:
        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            prev = session.get(AgentExecution, int(prev_exec_id))
            if prev and prev.output:
                diff = delta_prompt.compute_diff(prev.input_context, context_blocks)
                if diff.is_delta_eligible:
                    delta_system_prefix = delta_prompt.build_delta_prompt(prev.output, diff)

    try:
        execution_id = agent_runner.run_agent(
            agent_type=agent_type,
            ticket_id=int(ticket_id),
            context_blocks=context_blocks,
            chain_from=chain_from,
            user=current_user(),
            model_override=payload.get("model_override"),
            system_prompt_override=payload.get("system_prompt_override"),
            use_few_shot=payload.get("use_few_shot", True),
            use_anti_patterns=payload.get("use_anti_patterns", True),
            fingerprint_complexity=payload.get("fingerprint_complexity"),
            delta_prefix=delta_system_prefix,                           # FA-32
            previous_execution_id=int(prev_exec_id) if prev_exec_id else None,
        )
    except agent_runner.UnknownAgentError:
        abort(400, f"unknown agent_type: {agent_type}")

    return jsonify({"execution_id": execution_id, "status": "running"}), 202


@bp.post("/route")
def route():
    """FA-04 — Devuelve qué modelo se usaría para los blocks dados (sin ejecutar)."""
    payload = request.get_json(force=True, silent=True) or {}
    agent_type = payload.get("agent_type")
    blocks = payload.get("context_blocks") or []
    if not agent_type:
        abort(400, "agent_type is required")
    decision = llm_router.decide(
        agent_type=agent_type,
        blocks=blocks,
        fingerprint_complexity=payload.get("fingerprint_complexity"),
        override=payload.get("model_override"),
    )
    return jsonify({**decision.to_dict(), "available": llm_router._available_models()})


@bp.get("/models")
def list_models_route():
    """Lista los modelos reales disponibles para el backend LLM activo.

    Para `LLM_BACKEND=copilot` consulta el endpoint `/models` de GitHub Copilot
    con el OAuth token de gh y devuelve la lista filtrada por `model_picker_enabled`.
    Cachea 5 min; pasar `?refresh=true` fuerza una nueva consulta.
    """
    refresh = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
    backend = (config.LLM_BACKEND or "mock").lower()

    if backend == "copilot":
        status = llm_router.get_copilot_models_status(refresh=refresh)
        return jsonify({
            "backend": backend,
            "models": status["models"],
            "error": status["error"],
            "cached_at": status["cached_at"],
            "ttl_sec": status["ttl_sec"],
            "fallback_used": status["fallback"],
        })

    if backend == "mock":
        models = [{"id": m, "name": m, "vendor": "mock"} for m in llm_router.MOCK_MODELS]
    else:
        models = [{"id": m, "name": m, "vendor": "Anthropic"} for m in llm_router.CLAUDE_MODELS]

    return jsonify({
        "backend": backend,
        "models": models,
        "error": None,
        "cached_at": 0,
        "ttl_sec": 0,
        "fallback_used": False,
    })


@bp.get("/<agent_type>/schema")
def schema(agent_type: str):
    """FA-19 — schema (legible) del contrato del agente."""
    return jsonify(contract_validator.schema_for(agent_type))


@bp.get("/<agent_type>/system-prompt")
def system_prompt(agent_type: str):
    """FA-50 — devuelve el system prompt default del agente para que el operador
    pueda copiarlo, editarlo y mandar un override en /run."""
    a = agents.get(agent_type)
    if a is None:
        abort(404)
    return jsonify({"agent_type": agent_type, "system_prompt": a.system_prompt()})


@bp.get("/next-suggestion")
def next_suggestion():
    """FA-42 — sugerencia de siguiente agente después de aprobar uno."""
    after = request.args.get("after_agent")
    if not after:
        abort(400, "after_agent is required")
    suggestions = next_agent.suggest(after_agent=after, k=2)
    return jsonify([s.to_dict() for s in suggestions])


@bp.post("/cancel/<int:execution_id>")
def cancel(execution_id: int):
    agent_runner.cancel(execution_id)
    return jsonify({"ok": True})


@bp.post("/estimate")
def estimate_cost():
    """FA-33 — Cost preview pre-Run.
    Devuelve estimación de tokens, costo USD y latencia para los blocks dados.
    También indica si habría hit en cache (FA-31)."""
    payload = request.get_json(force=True, silent=True) or {}
    agent_type = payload.get("agent_type")
    context_blocks = payload.get("context_blocks") or []
    model = payload.get("model", "claude-sonnet-4-6")

    if not agent_type:
        abort(400, "agent_type is required")

    estimate = cost_estimator.estimate(
        agent_type=agent_type, blocks=context_blocks, model=model
    )

    cache_hit = output_cache.lookup(agent_type=agent_type, blocks=context_blocks) is not None

    return jsonify({
        **estimate.to_dict(),
        "cache_hit": cache_hit,
        "agent_type": agent_type,
    })


@bp.post("/open-chat")
def open_chat():
    """Abre el Chat de GitHub Copilot en VS Code con el agente y contexto pre-cargados.

    El frontend llama a este endpoint cuando el operador hace clic en "↗ Abrir en Chat".
    El bridge de la extensión ejecuta el comando workbench.action.chat.open con:
      - query: el contexto del ticket serializado como markdown
      - isPartialQuery: true  → el mensaje queda en el input sin enviarse
      - agentId: nombre del agente .agent.md (VS Code 1.99+)
    """
    import requests as req_lib

    payload = request.get_json(force=True, silent=True) or {}
    ticket_id = payload.get("ticket_id")
    context_blocks = payload.get("context_blocks") or []
    vscode_agent_filename = payload.get("vscode_agent_filename") or ""
    model_override = payload.get("model_override") or ""

    if not ticket_id:
        abort(400, "ticket_id is required")

    # Construir el mensaje de contexto con los bloques
    import prompt_builder
    context_text = prompt_builder.render_blocks(context_blocks)
    message = f"# Ticket #{ticket_id}\n\n{context_text}" if context_text else f"# Ticket #{ticket_id}"

    # agent_name = filename sin la extensión .agent.md (ej: "TechnicalAnalyst")
    agent_name = vscode_agent_filename
    if agent_name.lower().endswith(".agent.md"):
        agent_name = agent_name[: -len(".agent.md")]

    bridge_url = f"http://127.0.0.1:{config.VSCODE_BRIDGE_PORT}/open-chat"
    try:
        bridge_resp = req_lib.post(
            bridge_url,
            json={"message": message, "agent_name": agent_name, "model": model_override},
            timeout=10,
        )
        bridge_resp.raise_for_status()
        return jsonify({"ok": True})
    except req_lib.exceptions.ConnectionError:
        abort(503, "VS Code bridge no disponible (puerto 5052). Verificá que la extensión Stacky esté activa.")
    except req_lib.exceptions.Timeout:
        abort(504, "VS Code bridge tardó demasiado en responder.")
    except req_lib.exceptions.RequestException as exc:
        abort(502, f"Error contactando VS Code bridge: {exc}")

