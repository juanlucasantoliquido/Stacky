import logging

from flask import Blueprint, abort, jsonify, request

import agent_runner
import agents
import contract_validator
from config import config
from services import (
    agent_history,
    cost_estimator,
    delta_prompt,
    llm_router,
    next_agent,
    output_cache,
    vscode_agents,
)
from ._helpers import current_user

logger = logging.getLogger("stacky_agents.api.agents")

bp = Blueprint("agents", __name__, url_prefix="/agents")


@bp.get("")
def list_agents_route():
    return jsonify(agents.list_agents())


@bp.get("/vscode")
def list_vscode_agents():
    """Devuelve los .agent.md del directorio de prompts de VS Code (GitHub Copilot)."""
    found = vscode_agents.list_agents(config.VSCODE_PROMPTS_DIR)
    return jsonify([a.to_dict() for a in found])


@bp.get("/vscode/<path:filename>/history")
def vscode_agent_history(filename: str):
    """Historial de tickets asociados a un agente VS Code (.agent.md).

    Mapea `filename` → `agent_type` legado mediante heurística (mismo criterio
    que el frontend usa en EmployeeCard) y devuelve los tickets que tuvieron
    ejecuciones de ese tipo, agrupados por ticket con la última ejecución de
    cada uno.

    Query params
    ------------
    limit : int (default 50) — máximo de tickets a devolver.

    Forma del payload
    -----------------
        {
          "agent_filename": "DevPacifico.agent.md",
          "inferred_agent_type": "developer",
          "mapping_note": "...",
          "tickets": [
            {
              "ticket_id": int, "ado_id": int, "title": str, "project": str|None,
              "ado_state": str|None, "ado_url": str|None,
              "last_execution_id": int, "last_execution_status": str,
              "last_execution_verdict": str|None,
              "last_execution_started_at": iso|None,
              "last_execution_completed_at": iso|None,
              "last_execution_duration_ms": int|None,
              "executions_count": int
            },
            ...
          ],
          "total_executions": int
        }

    Devuelve `tickets: []` (con `mapping_note`) si el agente no mapea a un
    `agent_type` conocido o si no hay ejecuciones registradas.

    Respeta el flujo humano-en-el-loop: read-only, no modifica nada y no
    dispara ejecuciones.
    """
    from db import session_scope

    safe = (filename or "").strip()
    # Mismo guard que `vscode_agents.get_agent_by_filename`: evita path traversal.
    if not safe or not safe.lower().endswith(".agent.md") or "/" in safe or "\\" in safe:
        abort(400, "filename inválido (esperado: '<nombre>.agent.md')")

    limit = request.args.get("limit", default=50, type=int)
    if limit <= 0 or limit > 500:
        limit = 50

    with session_scope() as session:
        result = agent_history.history_for_filename(session, filename=safe, limit=limit)
        return jsonify(result)


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
    from db import session_scope
    from models import Ticket

    payload = request.get_json(force=True, silent=True) or {}
    ticket_id = payload.get("ticket_id")
    context_blocks = payload.get("context_blocks") or []
    vscode_agent_filename = payload.get("vscode_agent_filename") or ""
    model_override = payload.get("model_override") or ""

    if not ticket_id:
        abort(400, "ticket_id is required")

    # Buscar el ticket en la DB para armar un encabezado completo
    import prompt_builder
    ticket_header_parts: list[str] = []
    ado_id_for_enrich: int | None = None
    with session_scope() as _s:
        ticket = _s.query(Ticket).filter_by(id=int(ticket_id)).first()
        if ticket is None:
            # Intentar buscar por ado_id en caso de que se haya pasado el ADO id
            ticket = _s.query(Ticket).filter_by(ado_id=int(ticket_id)).first()

        if ticket:
            ado_label = f"ADO-{ticket.ado_id}" if ticket.ado_id else f"Ticket #{ticket_id}"
            header = f"# {ado_label} — {ticket.title}"
            meta_parts: list[str] = []
            if ticket.ado_state:
                meta_parts.append(f"Estado: **{ticket.ado_state}**")
            if ticket.priority is not None:
                meta_parts.append(f"Prioridad: **{ticket.priority}**")
            if ticket.ado_url:
                meta_parts.append(f"[Ver en Azure DevOps]({ticket.ado_url})")
            ticket_header_parts.append(header)
            if meta_parts:
                ticket_header_parts.append(" | ".join(meta_parts))
            if ticket.description and ticket.description.strip():
                ticket_header_parts.append(f"\n## Descripción del ticket\n{ticket.description.strip()}")
            ado_id_for_enrich = ticket.ado_id
        else:
            ticket_header_parts.append(f"# Ticket #{ticket_id}")

    # Enriquecimiento ADO on-demand: comentarios + adjuntos del work item.
    # Mismo patrón que api/tickets.py — silencia errores para no romper el flujo.
    if ado_id_for_enrich:
        ado_sections = _build_ado_enrichment_sections(int(ado_id_for_enrich))
        if ado_sections:
            ticket_header_parts.extend(ado_sections)

    context_text = prompt_builder.render_blocks(context_blocks)
    if context_text:
        ticket_header_parts.append(f"\n## Contexto adicional\n{context_text}")

    message = "\n\n".join(ticket_header_parts)

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


def _build_ado_enrichment_sections(ado_id: int) -> list[str]:
    """Construye secciones markdown con comentarios + adjuntos del work item ADO.

    Misma lógica que `api/tickets.py` (`get_comments` / `get_attachments`):
    consulta on-demand al `AdoClient`, sin tocar la BD ni cachear.
    Silencia errores: si ADO no responde o la config está incompleta, devuelve
    lista vacía y deja log de warning. El `open_chat` sigue funcionando sin
    estas secciones.

    Retorna lista de strings markdown listos para insertar en `ticket_header_parts`.
    Cada string es una sección completa (encabezado `## ...` + cuerpo).
    """
    sections: list[str] = []

    # Cliente ADO — si no se puede instanciar (config faltante), salir limpio.
    try:
        from services.ado_client import AdoClient
        from services.ado_sync import _html_to_text
        client = AdoClient()
    except Exception as exc:
        logger.warning("open_chat — AdoClient no disponible para ADO-%s: %s", ado_id, exc)
        return sections

    # ── Comentarios ──────────────────────────────────────────────────────────
    try:
        raw_comments = client.fetch_comments(ado_id, top=30)
        comments_md: list[str] = []
        for c in raw_comments:
            text_html = c.get("text") or ""
            if not text_html.strip():
                continue
            text = _html_to_text(text_html).strip()
            if not text:
                continue
            author = c.get("author") or "?"
            date = c.get("date") or ""
            sep = " — " if date else ""
            comments_md.append(f"### {author}{sep}{date}\n{text}")
        if comments_md:
            sections.append("\n## Comentarios ADO\n" + "\n\n".join(comments_md))
    except Exception as exc:
        logger.warning("open_chat — fetch_comments(%s) falló: %s", ado_id, exc)

    # ── Adjuntos ─────────────────────────────────────────────────────────────
    try:
        attachments = client.fetch_attachments(ado_id)
        if attachments:
            attach_lines: list[str] = []
            text_blocks: list[str] = []
            for att in attachments:
                name = att.get("name") or "(sin nombre)"
                size = int(att.get("size") or 0)
                url = att.get("url") or ""
                size_str = _format_attachment_size(size)
                line_parts = [f"**{name}**", size_str]
                line = "- " + "  ·  ".join(line_parts)
                if url:
                    line += f"\n  {url}"
                attach_lines.append(line)
                text_content = att.get("text_content")
                if text_content and text_content.strip():
                    text_blocks.append(
                        f"### Adjunto: {name}\n```\n{text_content.strip()}\n```"
                    )
            if attach_lines:
                body_parts = ["\n".join(attach_lines)]
                if text_blocks:
                    body_parts.append("\n\n".join(text_blocks))
                sections.append("\n## Adjuntos\n" + "\n\n".join(body_parts))
    except Exception as exc:
        logger.warning("open_chat — fetch_attachments(%s) falló: %s", ado_id, exc)

    return sections


def _format_attachment_size(size: int) -> str:
    """Formatea bytes en una etiqueta humana (B / KB / MB)."""
    if not size:
        return "tamaño desconocido"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"

