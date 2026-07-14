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


@bp.post("/validate-artifact")
def validate_artifact_route():
    """F1.4 — Valida un artifact de agente (pending-task.json / comment.html).

    Lo invoca el hook PostToolUse generado por Stacky (claude_cli_hooks) en el
    momento en que el agente escribe el archivo, para devolverle el error
    exacto de inmediato. Solo lee disco/DB; no muta nada.

    Body: {"path": "<ruta absoluta del archivo escrito>"}
    """
    from services import artifact_validator

    body = request.get_json(silent=True) or {}
    path = (body.get("path") or "").strip()
    if not path:
        return jsonify({"error": "path is required"}), 400
    result = artifact_validator.validate_artifact_path(path)
    logger.info(
        "validate-artifact: path=%s kind=%s valid=%s errors=%d",
        path, result.kind, result.valid, len(result.errors),
    )
    return jsonify(result.to_dict())


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

    H6.3: tras guardar, dispara evals del agent_type inferido en thread daemon
    (gate suave — no bloquea). La respuesta incluye ``evals_warning`` (null si
    todo OK o sin goldens para el tipo).
    """
    from pathlib import Path as _Path
    payload = request.get_json(force=True, silent=True) or {}
    source_path = (payload.get("source_path") or "").strip()
    overwrite = bool(payload.get("overwrite"))
    if not source_path:
        abort(400, "source_path es requerido")
    src = _Path(source_path).expanduser()

    # V2.3 — gate de import endurecible: off | warn (default) | block.
    # En modo block hacemos backup del canonical previo (si existía) para poder
    # revertir si los goldens fallan → "el archivo NO se pisa" (criterio del plan).
    import os as _os
    gate_mode = (_os.getenv("STACKY_EVAL_GATE_MODE", "warn") or "warn").strip().lower()
    if gate_mode not in ("off", "warn", "block"):
        gate_mode = "warn"

    # Backup del canonical previo (solo modo block): para revertir si falla el gate.
    _dest = stacky_agents_svc.stacky_agents_dir() / src.name
    _prev_body: str | None = None
    _prev_existed = False
    if gate_mode == "block" and _dest.exists():
        _prev_existed = True
        try:
            _prev_body = _dest.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            _prev_body = None

    try:
        entry = stacky_agents_svc.import_agent_from_path(src, overwrite=overwrite)
    except FileNotFoundError:
        abort(404, f"no existe: {src}")
    except FileExistsError:
        abort(409, f"ya existe en canonical: {src.name} (usar overwrite=true para reemplazar)")
    except ValueError as exc:
        abort(400, str(exc))

    # V1.1 — versionado: registra el cuerpo importado (idempotente por sha).
    try:
        from services import agent_prompt_registry
        body = _Path(entry.path).read_text(encoding="utf-8")
        agent_prompt_registry.record_version(
            entry.filename, body, source="import_endpoint"
        )
    except Exception:
        logger.debug("V1.1: no se pudo registrar versión del prompt (no crítico)", exc_info=True)

    # V2.3 — gate de evals con modo configurable (endurece el gate suave H6.3):
    #   off   → no corre el gate.
    #   warn  → corre el gate SINCRÓNICO y devuelve el warning (no bloquea).
    #   block → corre el gate; si algún golden falla, revierte el archivo y 409.
    evals_warning: str | None = None
    agent_type = _infer_agent_type_from_filename(entry.filename)

    if gate_mode == "off":
        pass
    elif gate_mode == "warn":
        # Async como H6.3 (no bloquea); además corremos sync para poblar la
        # respuesta cuando el caller quiere el detalle inmediato.
        try:
            from evals.eval_gate import run_evals_for_agent_type
            evals_warning = run_evals_for_agent_type(agent_type)
        except Exception:
            logger.debug("eval_gate(warn): no se pudo correr (no crítico)", exc_info=True)
    elif gate_mode == "block":
        try:
            from evals.eval_gate import run_evals_for_agent_type
            evals_warning = run_evals_for_agent_type(agent_type)
        except Exception:
            logger.debug("eval_gate(block): error corriendo gate (no crítico)", exc_info=True)
            evals_warning = None
        if evals_warning:
            # Revertir: el archivo NO se pisa cuando el gate bloquea.
            try:
                if _prev_existed and _prev_body is not None:
                    _dest.write_text(_prev_body, encoding="utf-8")
                elif not _prev_existed and _dest.exists():
                    _dest.unlink()
            except Exception:  # noqa: BLE001
                logger.warning("eval_gate(block): no se pudo revertir %s", _dest, exc_info=True)
            return jsonify({
                "ok": False,
                "error": "eval_gate_blocked",
                "agent_type": agent_type,
                "detail": evals_warning,
            }), 409

    return jsonify({"ok": True, "agent": entry.to_manifest_dict(), "evals_warning": evals_warning})


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


def _validate_agent_filename(filename: str) -> str:
    safe = (filename or "").strip()
    if not safe or not safe.lower().endswith(".agent.md") or "/" in safe or "\\" in safe:
        abort(400, "filename inválido (esperado: '<nombre>.agent.md')")
    return safe


@bp.get("/<path:filename>/versions")
def agent_prompt_versions(filename: str):
    """V1.1 — Lista las versiones históricas del prompt de un agente."""
    from services import agent_prompt_registry
    safe = _validate_agent_filename(filename)
    return jsonify({
        "filename": safe,
        "versions": agent_prompt_registry.list_versions(safe),
    })


@bp.get("/<path:filename>/versions/diff")
def agent_prompt_version_diff(filename: str):
    """V1.1 — Unified diff entre dos versiones (?from=<id>&to=<id>)."""
    from services import agent_prompt_registry
    from flask import make_response, Response
    _validate_agent_filename(filename)
    from_id = request.args.get("from", type=int)
    to_id = request.args.get("to", type=int)
    if from_id is None or to_id is None:
        abort(400, "se requieren los query params 'from' y 'to' (ids de versión)")
    try:
        diff = agent_prompt_registry.diff_versions(from_id, to_id)
    except ValueError as exc:
        abort(404, str(exc))
    return Response(diff, mimetype="text/plain")


@bp.get("/advise")
def advise_runtime():
    """V1.2 — Recomienda runtime+modelo para un agent_type (sin ejecutar).

    Query: agent_type (req), ticket_id (opt), project (opt).
    Determinista, sin LLM. El frontend pre-carga el formulario; el operador
    siempre puede cambiar.
    """
    from services import run_advisor

    agent_type = (request.args.get("agent_type") or "").strip()
    if not agent_type:
        abort(400, "agent_type es requerido")
    project = (request.args.get("project") or "").strip() or None
    adv = run_advisor.advise(agent_type=agent_type, project=project)
    return jsonify(adv.to_dict())


_VALID_RUNTIMES = {"github_copilot", "codex_cli", "claude_code_cli"}


@bp.post("/run")
def run():
    import json as _json

    payload = request.get_json(force=True, silent=True) or {}
    agent_type = payload.get("agent_type")
    ticket_id = payload.get("ticket_id")
    context_blocks = payload.get("context_blocks") or []
    chain_from = payload.get("chain_from") or []
    # Runtime seleccionado por el operador.
    # Plan 36: registrar si el runtime vino ausente/vacío para que el frontend lo sepa
    # y pueda advertir al operador. NUNCA se cambia el runtime en silencio.
    runtime_raw: str | None = payload.get("runtime")
    runtime_defaulted: bool = runtime_raw is None or str(runtime_raw).strip() == ""
    runtime: str = "github_copilot" if runtime_defaulted else str(runtime_raw)
    if runtime_defaulted:
        logger.warning(
            "runtime ausente en payload de /run; aplicando default EXPLÍCITO '%s' "
            "(ticket=%s, agent=%s). El frontend SIEMPRE debería enviar runtime.",
            runtime, payload.get("ticket_id"), payload.get("agent_type"),
        )
    project_name = (payload.get("project") or "").strip() or None

    # Validación de runtime ANTES de cualquier procesamiento.
    # Reglas:
    #   - runtime ausente o null → github_copilot (retro-compat, marcado con runtime_defaulted=True)
    #   - runtime en _VALID_RUNTIMES → continuar
    #   - cualquier otro valor → 400 explícito, no fallback silencioso
    if not runtime_defaulted and runtime not in _VALID_RUNTIMES:
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

    # Plan 133 F1 — Refresh just-in-time del snapshot local del ticket (best-effort,
    # nunca levanta). Corre ANTES del preflight de negocio F2 para que decida sobre
    # datos frescos del tracker.
    from services.run_ticket_refresh import refresh_ticket_snapshot
    _refresh = refresh_ticket_snapshot(ticket_id)

    # Plan 133 F2 — Preflight de negocio: rechaza con 400 accionable ANTES de gastar
    # el run si el ticket no cumple los prerequisitos deterministas del contrato del
    # agente (p. ej. functional sobre una Task sin bloqueante). Fail-open ante red.
    from services.business_preflight import evaluate as business_preflight
    _bp = business_preflight(ticket_id=ticket_id, agent_type=agent_type)
    if not _bp.ok:
        logger.warning(
            "business_preflight_rejected agent=%s ticket=%s check=%s snapshot_fresh=%s",
            agent_type, ticket_id, _bp.check, _refresh.get("refreshed"),
        )
        from flask import make_response
        return make_response(
            _json.dumps({
                "ok": False,
                "error": "business_preflight_failed",
                "check": _bp.check,
                "message": _bp.reason,
                "agent_type": agent_type,
                "ticket_id": ticket_id,
                "snapshot_fresh": bool(_refresh.get("refreshed")),
            }),
            400,
            {"Content-Type": "application/json"},
        )

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

    # V0.2 — Guard anti-duplicados: no relanzar un run activo del mismo
    # ticket+agente salvo force=true. Estado terminal NO bloquea.
    if payload.get("force") is not True:
        from db import session_scope
        from services.run_guard import find_active_run

        with session_scope() as session:
            active = find_active_run(session, int(ticket_id), agent_type)
            active_id = active.id if active else None
        if active_id is not None:
            return jsonify({
                "ok": False,
                "error": "duplicate_run",
                "active_execution_id": active_id,
                "hint": "reintentar con force=true",
            }), 409

    # V0.3 — Cap de concurrencia: solo aplica a runtimes con subproceso CLI.
    # github_copilot no spawnea proceso → no consume slot.
    _slot_held = False
    if runtime in ("claude_code_cli", "codex_cli"):
        from services import run_slots

        if not run_slots.try_acquire():
            return jsonify({
                "ok": False,
                "error": "max_concurrent_runs",
                "active": run_slots.active_count(),
                "limit": int(getattr(config, "STACKY_MAX_CONCURRENT_RUNS", 0) or 0),
            }), 429
        _slot_held = True

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
        # V0.3 — liberar el slot si el spawn ni siquiera arrancó el runner.
        if _slot_held:
            from services import run_slots
            run_slots.release()
        abort(400, f"unknown agent_type: {agent_type}")
    except Exception:
        if _slot_held:
            from services import run_slots
            run_slots.release()
        raise

    resp_body = {
        "execution_id": execution_id,
        "status": "preparing",
        "runtime": runtime,
        "runtime_defaulted": runtime_defaulted,  # Plan 36: True si el cliente no envió runtime
    }

    # V2.4 — Cache/dedup: si hay un run completado idéntico (mismo prompt_sha +
    # model_override + contexto) dentro de la ventana, ofrecerlo como candidato.
    # NUNCA auto-skip: el run nuevo ya se lanzó; esto es solo una sugerencia para
    # que el frontend ofrezca "reusar #N". Default OFF (STACKY_RUN_CACHE_DAYS=0).
    try:
        cache_days = int(getattr(config, "STACKY_RUN_CACHE_DAYS", 0) or 0)
        if cache_days > 0 and runtime in ("claude_code_cli", "codex_cli") and vscode_agent_filename:
            from services import agent_prompt_registry, run_cache
            from db import session_scope

            versions = agent_prompt_registry.list_versions(vscode_agent_filename)
            prompt_sha = versions[-1]["sha256"] if versions else None
            fingerprint = run_cache.compute_fingerprint(
                prompt_sha=prompt_sha,
                model=payload.get("model_override"),
                context_blocks=context_blocks,
            )
            if fingerprint:
                with session_scope() as session:
                    candidate = run_cache.find_cached_candidate(
                        session=session,
                        fingerprint=fingerprint,
                        days=cache_days,
                        exclude_execution_id=execution_id,
                    )
                if candidate is not None:
                    resp_body["cached_candidate"] = candidate
    except Exception:  # noqa: BLE001 — la sugerencia de cache jamás bloquea el launch
        logger.debug("V2.4 cached_candidate lookup falló (no crítico)", exc_info=True)

    return jsonify(resp_body), 202


def _clamp_effort_for_model(effort: str, model_id: str | None) -> str:
    """Plan 43 F0 — Degrada effort al máximo soportado por el modelo.

    Matriz modelo x effort (oficial Claude CLI):
      claude-haiku-*   : low/medium/high            → xhigh→high, max→high
      claude-sonnet-*  : low/medium/high/max        → xhigh→high (xhigh es Opus 4.7+)
      claude-opus-4-5+ : low/medium/high/xhigh/max  → todo
    """
    if not model_id:
        return effort
    m = model_id.lower()
    if "haiku" in m:
        return effort if effort in ("low", "medium", "high") else "high"
    if "sonnet" in m:
        # sonnet no soporta xhigh (es Opus 4.7+); max sí en sonnet-4-6
        return "high" if effort == "xhigh" else effort
    # opus: todo soportado
    return effort


@bp.post("/run-brief")
def run_brief():
    """Plan 38 B2 — Lanza el BusinessAgent con un brief como contexto (sin ticket real).

    Crea o reutiliza un "Brief Pool Ticket" local (ado_id=-1, por proyecto) para
    anclar la ejecución y delega a run_agent con agent_type="business".
    El vscode_agent_filename se auto-resuelve a "BusinessAgent.agent.md" para
    runtimes CLI si no se envía explícitamente.
    """
    from db import session_scope
    from models import Ticket

    payload = request.get_json(force=True, silent=True) or {}
    brief = (payload.get("brief") or "").strip()
    if not brief:
        abort(400, "brief is required")

    runtime_raw = payload.get("runtime") or "github_copilot"
    project_name = (payload.get("project") or "").strip() or None
    vscode_agent_filename: str | None = payload.get("vscode_agent_filename") or None

    # Plan 45 F2 — tipo de work item destino (Epic por default; Issue opt-in).
    # La validación normaliza None/"" → "Epic" (backward-compatible) y rechaza
    # valores fuera de la allowlist. Issue solo se admite con el flag ON.
    from api.tickets import validate_brief_work_item_type
    try:
        work_item_type = validate_brief_work_item_type(payload.get("work_item_type"))
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_work_item_type"}), 400
    if work_item_type == "Issue" and not config.STACKY_ISSUE_FROM_BRIEF_ENABLED:
        return jsonify({"ok": False, "error": "issue_from_brief_disabled"}), 400
    # Plan 52 F0 — Paridad de runtimes: el autopublish (Epic/Issue) SOLO lo ejecuta
    # el finalizador de claude_code_cli_runner (_maybe_autopublish_epic). Codex CLI y
    # GitHub Copilot NO autopublican → degradación controlada: rechazo explícito y
    # temprano (antes de gastar tokens) para no dar falsa sensación de éxito.
    _AUTOPUBLISH_RUNTIME = "claude_code_cli"
    if work_item_type in ("Epic", "Issue") and runtime_raw != _AUTOPUBLISH_RUNTIME:
        return jsonify({
            "ok": False,
            "error": "autopublish_requires_claude_cli",
            "detail": (
                f"work_item_type={work_item_type!r} requiere runtime "
                f"{_AUTOPUBLISH_RUNTIME!r}; recibido {runtime_raw!r}."
            ),
        }), 400
    # Plan 42 F3 / Plan 53 F2 — modelo y effort por-run con selector adaptativo.
    # Cap duro vía llm_router.clamp_model (nunca Opus/Fable salvo allowlist).
    from services import llm_router as _llm_router
    from services import adaptive_selector  # Plan 53

    # --- Extracción de override del operador (C3: empty string == ausente) ---
    _requested_model_raw = (payload.get("model") or "").strip()
    _requested_model: str | None = _requested_model_raw or None  # None si vacío

    _requested_effort_raw = (payload.get("effort") or "").strip().lower()

    # Override explícito: solo si el operador envió algo no-vacío y válido.
    _operator_explicitly_set_model = _requested_model is not None
    _operator_explicitly_set_effort = _requested_effort_raw in {"low", "medium", "high", "xhigh", "max"}

    # Base inicial: override del operador si lo envió, si no, defaults.
    _base_model: str | None = _requested_model if _operator_explicitly_set_model else None
    _base_effort: str = _requested_effort_raw if _operator_explicitly_set_effort else "high"

    # --- Plan 53 F2: propuesta adaptativa (solo flag ON y sin override manual total) ---
    _adaptive_trace: dict | None = None
    if (
        config.STACKY_ADAPTIVE_SELECTOR_ENABLED
        and not (_operator_explicitly_set_model and _operator_explicitly_set_effort)
    ):
        # G4 fino: si el operador NO fijó ambos, el selector propone los que faltan.
        _conf = adaptive_selector._load_last_project_confidence(project_name)
        _sel = adaptive_selector.select(_conf, base_model=_base_model, base_effort=_base_effort)

        # G4: respetar CADA override por separado (si el operador fijó solo uno, respetarlo).
        if not _operator_explicitly_set_model:
            _base_model = _sel.model
        if not _operator_explicitly_set_effort:
            _base_effort = _sel.effort
        logger.info("run_brief: selector adaptativo conf=%s -> %s", _conf, _sel.reason)
        # F5 — traza opcional para auditar K1/K2 (se adjunta a metadata más abajo).
        _adaptive_trace = {
            "enabled": True,
            "input_confidence": _conf,
            "reason": _sel.reason,
            "proposed_model": _sel.model,
            "proposed_effort": _sel.effort,
        }

    # --- Plan 43 F1 — brief→épica permite Opus 4.8 de primera clase, siempre (sin flag).
    # Clamp duro SIEMPRE (G3 — red de seguridad final).
    model_override: str | None = (
        _llm_router.clamp_model(_base_model, allow_opus=True) if _base_model else None
    )
    effort_override: str = _base_effort if _base_effort in {"low", "medium", "high", "xhigh", "max"} else "high"
    effort_override = _clamp_effort_for_model(effort_override, model_override)

    # Completar la traza con los valores efectivos post-clamp.
    if _adaptive_trace is not None:
        _adaptive_trace["final_model"] = model_override
        _adaptive_trace["final_effort"] = effort_override

    logger.info("run_brief: modelo efectivo=%s effort=%s", model_override, effort_override)

    # Plan 41 — Pre-vuelo de Intención (dos pasos, sin estado server-side).
    # Paso 1: con flag ON y preflight:true (y NO aprobado aún) → generar el Brief
    # de Intención y devolverlo SIN arrancar el run. Si el runtime no puede
    # pre-volar, generate_intent_brief devuelve None → se cae al camino normal.
    from services import intent_preflight
    preflight_requested = bool(payload.get("preflight"))
    approved = bool(payload.get("approved"))
    corrections = (payload.get("corrections") or "").strip() or None

    if config.INTENT_PREFLIGHT_ENABLED and preflight_requested and not approved:
        intent = intent_preflight.generate_intent_brief(
            brief_text=brief,
            context_summary=_short_context_summary(project_name),
            runtime=runtime_raw,
            project_name=project_name,
            invoke_short_llm=_make_short_llm_invoker(),
            log=logger.info,
        )
        if intent is not None:
            intent = intent_preflight.rank_and_flag(intent)
            auto_approvable = (
                config.INTENT_PREFLIGHT_AUTO_APPROVE
                and not intent.open_questions
                and intent.confidence >= config.INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF
            )
            return jsonify({
                "stage": "preflight",
                "intent": intent_preflight.to_payload(intent),
                "auto_approvable": auto_approvable,
            }), 200
        # intent is None → runtime no disponible → cae al camino normal (arranca).
        logger.info(
            "run_brief: pre-vuelo no disponible para runtime=%s; se procede sin pre-vuelo",
            runtime_raw,
        )

    # Auto-resolve el .agent.md del BusinessAgent para runtimes CLI.
    if runtime_raw in ("codex_cli", "claude_code_cli") and not vscode_agent_filename:
        vscode_agent_filename = "BusinessAgent.agent.md"

    # Obtener o crear el Brief Pool Ticket para este proyecto (ado_id=-1).
    pool_project = project_name or "default"
    with session_scope() as session:
        pool_ticket = (
            session.query(Ticket)
            .filter_by(ado_id=-1, project=pool_project)
            .first()
        )
        if pool_ticket is None:
            pool_ticket = Ticket(
                ado_id=-1,
                external_id=-1,
                project=pool_project,
                stacky_project_name=pool_project,
                title="[Stacky] Brief Pool",
                work_item_type="Task",
                ado_state="Active",
            )
            session.add(pool_ticket)
            session.flush()
        pool_ticket_id = pool_ticket.id

    context_blocks = [
        {
            "id": "brief",
            "kind": "raw-conversation",
            "title": "Brief del operador",
            "content": brief,
            "source": {"type": "brief_modal"},
        }
    ]
    # Plan 41 paso 2 — las correcciones del operador mandan sobre cualquier
    # supuesto; se anteponen como bloque de máxima prioridad (id registrado en
    # context_enrichment._BLOCK_PRIORITY con valor 110).
    if corrections:
        context_blocks = intent_preflight.build_corrections_block(corrections) + context_blocks

    user = current_user()

    # Plan 57 F4 — Claim hook especulativo (latencia-cero si spec completado).
    # Ocurre DESPUÉS de validar runtime+autopublish, ANTES de spawnear ejecutor.
    # Si STACKY_SPECULATIVE_ENABLED=false, claim() retorna None inmediatamente (miss).
    # Si hay spec completado con el mismo hash → se usa su output directamente.
    # Auto-publish posterior ocurre igual: el runner confirmado lo maneja.
    _spec_claimed: dict | None = None
    try:
        from services import speculative as _speculative
        _spec_claimed = _speculative.claim(
            agent_type="business",
            context_blocks=context_blocks,
            runtime=runtime_raw,
            model=model_override or "",
            effort=effort_override,
        )
    except Exception as _spec_exc:  # noqa: BLE001 — claim nunca bloquea el run
        logger.debug("run_brief: spec claim falló (ignorado): %s", _spec_exc)

    try:
        execution_id = agent_runner.run_agent(
            agent_type="business",
            ticket_id=pool_ticket_id,
            context_blocks=context_blocks,
            user=user,
            runtime=runtime_raw,
            vscode_agent_filename=vscode_agent_filename,
            project_name=project_name,
            use_few_shot=False,
            use_anti_patterns=False,
            model_override=model_override,
            effort_override=effort_override,
            work_item_type=work_item_type,
        )
    except agent_runner.UnknownAgentError:
        abort(400, "agent_type 'business' no está registrado")
    except Exception as exc:  # noqa: BLE001 — Plan 39 B1: nunca 500 genérico
        logger.exception(
            "run_brief: fallo al lanzar agente runtime=%s project=%s",
            runtime_raw, project_name,
        )
        return jsonify({
            "ok": False,
            "error": "agent_launch_failed",
            "runtime": runtime_raw,
            "message": str(exc),
        }), 502

    logger.info(
        "run_brief: execution_id=%s runtime=%s project=%s",
        execution_id, runtime_raw, project_name,
    )

    # Plan 53 F5 — Traza opcional del selector adaptativo en metadata del run.
    # Solo se persiste con flag ON; con flag OFF la metadata no cambia (G5 byte-identidad).
    if _adaptive_trace is not None:
        try:
            from db import session_scope as _sc53
            from models import AgentExecution as _AE53
            with _sc53() as _s53:
                _ex53 = _s53.get(_AE53, execution_id)
                if _ex53 is not None:
                    _md53 = dict(_ex53.metadata_dict or {})
                    _md53["adaptive_selector"] = _adaptive_trace
                    _ex53.metadata_dict = _md53
        except Exception as _e53:  # noqa: BLE001 — traza es opcional; nunca bloquea el run
            logger.warning("run_brief: no se pudo persistir traza adaptive_selector: %s", _e53)

    # Plan 57 F4 — Anotar si el run proviene de spec completado (solo informativo).
    # Con flag OFF, _spec_claimed siempre es None → metadata byte-idéntica.
    if _spec_claimed is not None:
        try:
            from db import session_scope as _sc57
            from models import AgentExecution as _AE57
            with _sc57() as _s57:
                _ex57 = _s57.get(_AE57, execution_id)
                if _ex57 is not None:
                    _md57 = dict(_ex57.metadata_dict or {})
                    _md57["from_speculative"] = True
                    _md57["spec_id"] = _spec_claimed.get("id")
                    _ex57.metadata_dict = _md57
        except Exception as _e57:  # noqa: BLE001 — traza es opcional; nunca bloquea el run
            logger.debug("run_brief: no se pudo persistir traza from_speculative: %s", _e57)

    return jsonify({"execution_id": execution_id, "status": "running"}), 202


@bp.get("/autoprofile/<project>")
def project_autoprofile(project: str):
    """Plan 42 F5 — Deriva un perfil de proyecto desde los docs locales (determinista, sin LLM).

    Gated por STACKY_PROJECT_AUTOPROFILE_ENABLED (default false).
    Devuelve 404 si el flag está OFF o si no hay docs configurados para el proyecto.
    """
    import os as _os
    if _os.getenv("STACKY_PROJECT_AUTOPROFILE_ENABLED", "false").lower() not in {"1", "true", "on"}:
        return jsonify({"ok": False, "error": "feature_disabled"}), 404

    if not project:
        abort(400, "project es requerido")

    try:
        from project_manager import get_project_config
        proj_cfg = get_project_config(project)
        docs_root_str = (proj_cfg or {}).get("docs_root") or ""
    except Exception:  # noqa: BLE001
        docs_root_str = ""

    if not docs_root_str:
        return jsonify({"ok": False, "error": "docs_root no configurado para este proyecto"}), 404

    from pathlib import Path as _Path
    from services.project_autoprofile import draft_profile_from_docs
    docs_root = _Path(docs_root_str)
    if not docs_root.is_dir():
        return jsonify({"ok": False, "error": f"docs_root no existe: {docs_root_str}"}), 404

    profile = draft_profile_from_docs(docs_root)
    return jsonify({"ok": True, "project": project, "draft_profile": profile})


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
            "No se incluye el contenido del `.agent.md` en este mensaje: "
            "leé el archivo indicado arriba antes de empezar.\n"
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

    # Plan 79 F2 — estado-en-progreso determinista al iniciar (paridad 3
    # runtimes: GitHub Copilot). No crítico: nunca debe romper el arranque.
    if created_new_execution and ado_id_for_enrich is not None:
        try:
            from harness.task_states import apply_task_start_state
            from services.tracker_provider import get_tracker_provider

            _provider = get_tracker_provider(project_ctx.stacky_project_name)
            apply_task_start_state(
                project_name=project_ctx.stacky_project_name,
                agent_type=inferred_type,
                ado_id=ado_id_for_enrich,
                provider=_provider,
            )
        except Exception:
            logger.debug("apply_task_start_state falló (no crítico)", exc_info=True)

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


# ── Plan 44 — Observatorio de Grounding + Sugeridor de Diccionario ────────────

def _collect_epic_summaries(project: str | None) -> tuple[list[dict], list[str]]:
    """Recolecta los epic_summary persistidos en metadata, en orden cronológico.

    Devuelve (summaries, runtimes) en paralelo. AgentExecution no tiene campo de
    proyecto propio; cuando se pide filtrar por proyecto se usa el
    `stacky_project_name` del ticket asociado (best-effort). Runs con metadata
    corrupta o sin epic_summary se omiten (degradación segura).
    """
    from db import session_scope
    from models import AgentExecution, Ticket

    summaries: list[dict] = []
    runtimes: list[str] = []
    with session_scope() as session:
        q = (
            session.query(AgentExecution)
            .filter(AgentExecution.metadata_json.isnot(None))
            .filter(AgentExecution.metadata_json.like('%epic_summary%'))
            .order_by(AgentExecution.started_at.asc())
        )
        for ex in q:
            try:
                md = ex.metadata_dict
            except Exception:  # noqa: BLE001 — metadata corrupta → omitir
                continue
            summary = md.get("epic_summary")
            if not isinstance(summary, dict):
                continue
            if project:
                # Filtro best-effort por el proyecto del ticket asociado.
                ticket = session.get(Ticket, ex.ticket_id) if ex.ticket_id else None
                proj_name = getattr(ticket, "stacky_project_name", None) if ticket else None
                if proj_name and proj_name != project:
                    continue
            summaries.append(summary)
            runtimes.append(str(md.get("runtime") or ""))
    return summaries, runtimes


def _load_process_catalog(project: str | None) -> list[dict]:
    """Carga el process_catalog del client-profile del proyecto (o [])."""
    if not project:
        return []
    try:
        from services.client_profile import load_client_profile
        profile = load_client_profile(project) or {}
        catalog = profile.get("process_catalog")
        return catalog if isinstance(catalog, list) else []
    except Exception:  # noqa: BLE001 — sin perfil → degradación: todo se sugiere
        return []


@bp.get("/epics/grounding-observatory")
def grounding_observatory_route():
    """Plan 44 F2 — Métricas agregadas de grounding de épicas (solo-lectura).

    URL final: GET /api/agents/epics/grounding-observatory[?project=NAME]
    Gated por STACKY_GROUNDING_OBSERVATORY_ENABLED (default true). OFF → 404.
    """
    if not config.STACKY_GROUNDING_OBSERVATORY_ENABLED:
        return jsonify({"error": "feature_disabled"}), 404
    project = (request.args.get("project") or "").strip() or None
    summaries, runtimes = _collect_epic_summaries(project)
    from services.grounding_observatory import aggregate_grounding
    result = aggregate_grounding(summaries, runtimes)
    result["project"] = project
    return jsonify(result), 200


@bp.get("/projects/<project>/process-catalog-suggestions")
def process_catalog_suggestions_route(project: str):
    """Plan 44 F3 — Procesos citados en épicas que faltan en el catálogo.

    URL final: GET /api/agents/projects/<project>/process-catalog-suggestions
    Gated por STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED (default true). OFF → 404.
    Solo sugiere; nunca escribe (human-in-the-loop).
    """
    if not config.STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED:
        return jsonify({"error": "feature_disabled"}), 404
    proj = (project or "").strip() or None
    summaries, _ = _collect_epic_summaries(proj)
    existing = _load_process_catalog(proj)
    from services.grounding_observatory import suggest_process_catalog_entries
    suggestions = suggest_process_catalog_entries(summaries, existing)
    return jsonify({"project": proj, "suggestions": suggestions}), 200


# ── Plan 41 — Helpers del Pre-vuelo de Intención ──────────────────────────────

def _short_context_summary(project_name: str | None) -> str:
    """Resumen barato del client-profile para el pre-vuelo (sin secretos).

    Best-effort: si no hay perfil, devuelve "". Reusa el bloque client-profile
    existente (ya redacta y respeta el flag); recorta para mantener el prompt corto.
    """
    if not project_name:
        return ""
    try:
        from services.context_enrichment import build_client_profile_block
        block = build_client_profile_block(project_name)
        if not block:
            return ""
        content = block.get("content") or ""
        return content[:1500]  # acotado: el pre-vuelo es barato por diseño
    except Exception:  # noqa: BLE001
        return ""


def _make_short_llm_invoker():
    """Devuelve un callable(system, user, runtime, project) -> str para el pre-vuelo.

    La pasada corta usa el LLM backend interno de Stacky (copilot_bridge), que es
    server-side y agnóstico al runtime del agente. Si el backend no está disponible
    o falla, lanza PreflightRuntimeUnavailable → el caller cae al camino normal
    (comportamiento idéntico a flag OFF). Nunca bloquea el run.
    """
    from services.intent_preflight import PreflightRuntimeUnavailable

    def _invoke(system: str, user: str, runtime: str, project_name: str | None) -> str:
        try:
            import copilot_bridge
            resp = copilot_bridge.invoke(
                agent_type="business",
                system=system,
                user=user,
                on_log=lambda *a, **k: None,
                project_name=project_name,
            )
        except NotImplementedError as exc:
            raise PreflightRuntimeUnavailable(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — bridge caído/no configurado
            raise PreflightRuntimeUnavailable(f"bridge no disponible: {exc}") from exc
        return getattr(resp, "text", "") or ""

    return _invoke

