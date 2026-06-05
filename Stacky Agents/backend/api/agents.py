import logging
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

import agent_runner
import agents
import contract_validator
from config import config
from services.project_context import build_ado_client, ensure_project_vscode, resolve_project_context
from services import (
    agent_history,
    cost_estimator,
    delta_prompt,
    llm_router,
    next_agent,
    output_cache,
    stacky_agents as stacky_agents_svc,
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


@bp.get("/stacky/manifest")
def stacky_manifest():
    """Devuelve el manifest canónico ``<stacky_home>/agents/manifest.json``.

    Si no existe lo materializa primero (idempotente). Útil para que la UI
    muestre qué `.agent.md` salen del canonical, su `@mention`, ruta absoluta,
    checksum y `source` (bundled, imported, legacy).

    Plan: plan-agentes-bundled-en-stacky-2026-05-29.md §3.3 + §4.
    """
    from pathlib import Path as _Path
    from runtime_paths import stacky_agents_dir as _stacky_agents_dir
    from runtime_paths import stacky_home as _stacky_home

    manifest = stacky_agents_svc.read_manifest()
    if manifest is None:
        # primera vez o se borró: materializar y reintentar
        stacky_agents_svc.materialize_agents()
        manifest = stacky_agents_svc.read_manifest() or {}
    entries = stacky_agents_svc.list_canonical_agents()
    effective_agents_dir = config.VSCODE_PROMPTS_DIR
    return jsonify({
        "stacky_home": str(_stacky_home()),
        "agents_dir": str(_stacky_agents_dir()),
        "effective_agents_dir": effective_agents_dir,
        "manifest_path": str(_Path(_stacky_agents_dir()) / "manifest.json"),
        "manifest": manifest,
        "agents": [e.to_manifest_dict() for e in entries],
        "count": len(entries),
    })


@bp.post("/stacky/materialize")
def stacky_materialize():
    """Refresca ``<stacky_home>/agents`` desde las fuentes externas.

    Body opcional::

        { "force": true }

    Si ``force=true`` sobrescribe los archivos existentes; por defecto se
    preservan ediciones del operador en el deploy. Devuelve el manifest
    actualizado.
    """
    payload = request.get_json(force=True, silent=True) or {}
    force = bool(payload.get("force"))
    entries = stacky_agents_svc.materialize_agents(force=force)
    return jsonify({
        "ok": True,
        "force": force,
        "count": len(entries),
        "agents": [e.to_manifest_dict() for e in entries],
    })


@bp.post("/stacky/import")
def stacky_import_agent():
    """Importa un ``.agent.md`` arbitrario al canonical.

    Body::

        {
          "source_path": "C:/ruta/Externa/Foo.agent.md",
          "overwrite": false
        }

    Devuelve la entry materializada. 404 si la fuente no existe; 409 si ya
    existe en el canonical y ``overwrite`` es ``false``.
    """
    from pathlib import Path as _Path
    payload = request.get_json(force=True, silent=True) or {}
    source_path = (payload.get("source_path") or "").strip()
    overwrite = bool(payload.get("overwrite"))
    if not source_path:
        abort(400, "source_path es requerido")
    src = _Path(source_path).expanduser()
    try:
        entry = stacky_agents_svc.import_agent_from_path(src, overwrite=overwrite)
    except FileNotFoundError:
        abort(404, f"no existe: {src}")
    except FileExistsError:
        abort(409, f"ya existe en canonical: {src.name} (usar overwrite=true para reemplazar)")
    except ValueError as exc:
        abort(400, str(exc))
    return jsonify({"ok": True, "agent": entry.to_manifest_dict()})


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


_VALID_RUNTIMES = {"github_copilot", "codex_cli", "claude_code_cli"}


@bp.post("/run")
def run():
    import json as _json

    payload = request.get_json(force=True, silent=True) or {}
    agent_type = payload.get("agent_type")
    ticket_id = payload.get("ticket_id")
    context_blocks = payload.get("context_blocks") or []
    chain_from = payload.get("chain_from") or []
    # Runtime seleccionado por el operador — default github_copilot para retrocompatibilidad
    runtime_raw: str | None = payload.get("runtime")
    runtime: str = runtime_raw or "github_copilot"
    project_name = (payload.get("project") or "").strip() or None

    # Validación de runtime ANTES de cualquier procesamiento.
    # Reglas:
    #   - runtime ausente o null → github_copilot (retro-compat)
    #   - runtime en _VALID_RUNTIMES → continuar
    #   - cualquier otro valor → 400 explícito, no fallback silencioso
    if runtime_raw is not None and runtime not in _VALID_RUNTIMES:
        logger.warning(
            "runtime desconocido '%s' rechazado (válidos: %s)",
            runtime_raw,
            sorted(_VALID_RUNTIMES),
        )
        from flask import make_response
        return make_response(
            _json.dumps({
                "ok": False,
                "error": "unknown_runtime",
                "message": (
                    f"runtime '{runtime_raw}' no es válido. "
                    f"Valores permitidos: {sorted(_VALID_RUNTIMES)}"
                ),
            }),
            400,
            {"Content-Type": "application/json"},
        )

    # codex_cli y claude_code_cli: requieren vscode_agent_filename en el payload.
    # Ambos runtimes CLI ejecutan el system prompt del agente .agent.md seleccionado.
    vscode_agent_filename: str | None = payload.get("vscode_agent_filename") or None
    if runtime in ("codex_cli", "claude_code_cli") and not vscode_agent_filename:
        logger.warning(
            "runtime=%s rechazado: vscode_agent_filename ausente en payload", runtime
        )
        from flask import make_response
        return make_response(
            _json.dumps({
                "ok": False,
                "error": "missing_vscode_agent_filename",
                "message": (
                    f"runtime={runtime} requiere vscode_agent_filename en el payload "
                    "(ej: 'DevPacifico.agent.md')."
                ),
            }),
            400,
            {"Content-Type": "application/json"},
        )

    logger.info(
        "agent_run dispatch runtime=%s agent=%s ticket=%s",
        runtime, agent_type, ticket_id,
    )

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

    # B3 — Auto-asignar el ticket al operador si está sin responsable. Best-effort:
    # nunca bloquea el lanzamiento del agente (el helper traga sus excepciones).
    try:
        from services.ticket_assigner import auto_assign_on_run
        auto_assign_on_run(int(ticket_id), project_name=project_name)
    except Exception:  # noqa: BLE001
        logger.warning("auto_assign_on_run falló (no bloquea el run)", exc_info=True)

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
            runtime=runtime,
            vscode_agent_filename=vscode_agent_filename,
            project_name=project_name,
        )
    except agent_runner.UnknownAgentError:
        abort(400, f"unknown agent_type: {agent_type}")

    return jsonify({"execution_id": execution_id, "status": "running", "runtime": runtime}), 202


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
    """FA-42 — sugerencia de siguiente agente después de aprobar uno.

    DEPRECATED — Feature #4 FlowConfig (SDD-2026-05-19).
    La recomendación del botón "Run Sugerido" en TicketBoard ya no consume
    este endpoint. Fue reemplazada por GET /api/flow-config/resolve que
    devuelve la regla determinística configurada por el operador.
    Este endpoint se preserva para rollback y para NextAgentSuggestion.tsx
    (sugerencias post-aprobación en OutputPanel). No eliminar en v1.
    Response incluye header Deprecation: true.
    """
    after = request.args.get("after_agent")
    if not after:
        abort(400, "after_agent is required")
    suggestions = next_agent.suggest(after_agent=after, k=2)
    resp = jsonify([s.to_dict() for s in suggestions])
    resp.headers["Deprecation"] = "true"
    resp.headers["Sunset"] = "Feature #4 FlowConfig — ver SDD-2026-05-19"
    return resp


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
    project_name = (payload.get("project") or "").strip() or None

    if not ticket_id:
        abort(400, "ticket_id is required")

    # Buscar el ticket en la DB para armar un encabezado completo
    import prompt_builder
    ticket_header_parts: list[str] = []
    ado_id_for_enrich: int | None = None
    local_ticket_id: int | None = None
    resolved_project_name = project_name
    resolved_ticket = None
    with session_scope() as _s:
        ticket = _s.query(Ticket).filter_by(id=int(ticket_id)).first()
        if ticket is None:
            # Intentar buscar por ado_id en caso de que se haya pasado el ADO id
            ticket = _s.query(Ticket).filter_by(ado_id=int(ticket_id)).first()
        resolved_ticket = ticket

        if ticket:
            local_ticket_id = ticket.id
            resolved_project_name = ticket.stacky_project_name or resolved_project_name
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

    project_ctx = resolve_project_context(project_name=resolved_project_name, ticket=resolved_ticket)
    if project_ctx is None:
        abort(400, "No se pudo resolver el proyecto para abrir GitHub Copilot.")

    # B3 — Auto-asignar el ticket al operador si está sin responsable (path GitHub
    # Copilot). Best-effort: nunca bloquea la apertura del chat.
    if local_ticket_id is not None:
        try:
            from services.ticket_assigner import auto_assign_on_run
            auto_assign_on_run(int(local_ticket_id), project_name=project_ctx.stacky_project_name)
        except Exception:  # noqa: BLE001
            logger.warning("open_chat — auto_assign_on_run falló (no bloquea)", exc_info=True)

    try:
        project_ctx = ensure_project_vscode(project_ctx.stacky_project_name)
    except Exception as exc:  # noqa: BLE001
        abort(503, f"No se pudo preparar VS Code del proyecto '{project_ctx.stacky_project_name}': {exc}")

    # Client-profile: el flujo interactivo (open_chat) NO pasa por
    # `context_enrichment.enrich_blocks`, así que históricamente el bloque
    # `client-profile` no llegaba al prompt. Los agentes cliente-agnósticos
    # (p.ej. Developer) dependen de ese bloque para conocer rutas/build/estados;
    # sin él arrancaban "a ciegas" (el Técnico no lo notaba porque su .agent.md
    # tiene los datos de Pacífico hardcodeados). Inyectamos el MISMO bloque que
    # arma el pipeline batch, usando el seam único `build_client_profile_block`,
    # para que ambos caminos entreguen idéntico perfil. Best-effort: si no hay
    # proyecto/perfil o el flag está OFF, se omite sin romper el flujo.
    try:
        from services.context_enrichment import build_client_profile_block

        cp_block = build_client_profile_block(
            project_ctx.stacky_project_name,
            log=lambda _lvl, _msg: logger.info("open_chat client-profile: %s", _msg),
        )
        if cp_block:
            ticket_header_parts.append(
                f"## {cp_block['title']}\n\n{cp_block['content']}"
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "open_chat — no se pudo inyectar client-profile (continuando): %s", exc
        )

    # Enriquecimiento ADO on-demand: comentarios + adjuntos del work item.
    # Mismo patrón que api/tickets.py — silencia errores para no romper el flujo.
    if ado_id_for_enrich:
        ado_sections = _build_ado_enrichment_sections(
            int(ado_id_for_enrich),
            project_name=project_ctx.stacky_project_name,
            tracker_project=project_ctx.tracker_project,
            ticket=resolved_ticket,
        )
        if ado_sections:
            ticket_header_parts.extend(ado_sections)

    context_text = prompt_builder.render_blocks(context_blocks)
    if context_text:
        ticket_header_parts.append(f"\n## Contexto adicional\n{context_text}")

    message = "\n\n".join(ticket_header_parts)

    selected_agent = None
    selected_agent_path = None
    if vscode_agent_filename:
        selected_agent = vscode_agents.get_agent_by_filename(
            config.VSCODE_PROMPTS_DIR,
            vscode_agent_filename,
        )
        selected_agent_path = Path(config.VSCODE_PROMPTS_DIR) / Path(vscode_agent_filename).name
        if selected_agent is None:
            abort(
                400,
                "No se encontró el .agent.md seleccionado en la fuente efectiva "
                f"({config.VSCODE_PROMPTS_DIR}): {vscode_agent_filename}",
            )

    # Importante: no mandamos `@Developer` al chat de VS Code. Ese prefijo hace
    # que GitHub Copilot use su agente propio por nombre, saltándose el archivo
    # .agent.md que Stacky acaba de resolver. El mensaje solo declara dónde está
    # el .agent.md elegido; el contenido no se inyecta en el chat.
    bridge_agent_name = ""
    if selected_agent is not None and selected_agent_path is not None:
        entry = stacky_agents_svc.build_entry_from_path(selected_agent_path)
        invocation = ""
        if entry is not None:
            invocation = stacky_agents_svc.build_invocation_block(
                entry=entry,
                workspace_root=project_ctx.workspace_root,
            )
        else:
            agents_dir = selected_agent_path.parent
            invocation = (
                "## Agente Stacky seleccionado\n"
                "\n"
                f"- Nombre: {selected_agent.name}\n"
                f"- Archivo agent.md: {selected_agent.filename}\n"
                f"- Ruta agent.md: {selected_agent_path}\n"
                f"- Carpeta de agentes configurada: {agents_dir}\n"
                f"- Workspace de trabajo: {project_ctx.workspace_root or '(no resuelto)'}\n"
                "\n"
                f"Regla: tomá como prompt/persona únicamente el archivo `{selected_agent_path}`.\n"
                "No uses otro `.agent.md` aunque exista en rutas externas. Si el archivo\n"
                "no existe, detené la ejecución y reportá el bloqueo.\n"
            )
        message = (
            f"{invocation}\n"
            "## Agente Stacky\n"
            "\n"
            "No se incluye el contenido del `.agent.md` en este mensaje. "
            "Usá únicamente el archivo indicado arriba como fuente de rol, "
            "criterio, tono, restricciones y forma de trabajo.\n"
            "\n"
            "## Tarea\n"
            "\n"
            f"{message}"
        )

    bridge_url = f"http://127.0.0.1:{project_ctx.vscode_port}/open-chat"
    logger.info(
        "open_chat launch project_name=%s workspace_root=%s bridge_port=%s ticket_id=%s ado_id=%s agent_file=%s agent_path=%s",
        project_ctx.stacky_project_name,
        project_ctx.workspace_root,
        project_ctx.vscode_port,
        local_ticket_id or ticket_id,
        ado_id_for_enrich,
        vscode_agent_filename,
        selected_agent_path,
    )
    try:
        bridge_resp = req_lib.post(
            bridge_url,
            json={"message": message, "agent_name": bridge_agent_name, "model": model_override},
            timeout=10,
        )
        bridge_resp.raise_for_status()
    except req_lib.exceptions.ConnectionError:
        abort(
            503,
            "VS Code bridge no disponible "
            f"(proyecto={project_ctx.stacky_project_name}, puerto={project_ctx.vscode_port}). "
            "Verificá que la extensión Stacky esté activa.",
        )
    except req_lib.exceptions.Timeout:
        abort(504, "VS Code bridge tardó demasiado en responder.")
    except req_lib.exceptions.RequestException as exc:
        abort(502, f"Error contactando VS Code bridge: {exc}")

    # Registrar la sesión en la DB para que el tablero de tickets muestre
    # el ticket como "en ejecución". El operador puede cerrarla desde el workbench
    # con Aprobar / Descartar. Si ya hay una ejecución running para este ticket
    # no creamos otra para evitar duplicados.
    import json as _json
    from datetime import datetime as _dt
    from models import AgentExecution
    exec_id: int | None = None
    created_new_execution = False
    inferred_type = _infer_agent_type_from_filename(vscode_agent_filename)
    if local_ticket_id is not None:
        try:
            with session_scope() as _s2:
                already_running = (
                    _s2.query(AgentExecution)
                    .filter_by(ticket_id=int(local_ticket_id), status="running")
                    .first()
                )
                if not already_running:
                    exec_record = AgentExecution(
                        ticket_id=int(local_ticket_id),
                        agent_type=inferred_type,
                        status="running",
                        input_context_json=_json.dumps(context_blocks, ensure_ascii=False),
                        started_by="open_chat",
                        started_at=_dt.utcnow(),
                    )
                    exec_record.metadata_dict = {
                        "runtime": "github_copilot",
                        "stacky_project_name": project_ctx.stacky_project_name,
                        "workspace_root": project_ctx.workspace_root,
                        "bridge_port": project_ctx.vscode_port,
                    }
                    _s2.add(exec_record)
                    _s2.flush()
                    exec_id = exec_record.id
                    created_new_execution = True
                else:
                    exec_id = already_running.id
        except Exception as _track_exc:
            logger.warning("open_chat — no se pudo registrar ejecución: %s", _track_exc)

    # Transicionar stacky_status del ticket a 'running' cuando arrancamos una
    # nueva ejecución. Sin esto, un ticket que quedó en 'completed' por un run
    # anterior se sigue mostrando como completed; combinado con la execution
    # activa, el frontend lo marca como INCONSISTENTE en lugar de "en ejecución".
    if created_new_execution and exec_id is not None and local_ticket_id is not None:
        try:
            from services import ticket_status as _ticket_status
            _ticket_status.set_status(
                int(local_ticket_id),
                "running",
                changed_by="open_chat",
                execution_id=exec_id,
                agent_type=inferred_type,
                reason="open_chat: nueva ejecución vía VS Code bridge",
            )
        except Exception as _status_exc:
            logger.warning(
                "open_chat — no se pudo transicionar stacky_status a 'running': %s",
                _status_exc,
            )

    return jsonify({
        "ok": True,
        "execution_id": exec_id,
        "project_name": project_ctx.stacky_project_name,
        "workspace_root": project_ctx.workspace_root,
        "bridge_port": project_ctx.vscode_port,
    })


def _infer_agent_type_from_filename(filename: str) -> str:
    """Infiere el AgentType (business/functional/technical/developer/qa/custom)
    a partir del nombre del archivo .agent.md — misma lógica que el frontend."""
    f = (filename or "").lower()
    if "business" in f or "negocio" in f:
        return "business"
    if "functional" in f or "funcional" in f:
        return "functional"
    if "technical" in f or "tecnic" in f:
        return "technical"
    if "dev" in f or "desarrollador" in f:
        return "developer"
    if "qa" in f or "test" in f:
        return "qa"
    return "custom"


def _build_ado_enrichment_sections(
    ado_id: int,
    *,
    project_name: str | None = None,
    tracker_project: str | None = None,
    ticket=None,
) -> list[str]:
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
        from services.ado_sync import _html_to_text
        client = build_ado_client(
            project_name=project_name,
            tracker_project=tracker_project,
            ticket=ticket,
        )
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

