"""
Núcleo de ejecución. Recibe (agent_type, ticket_id, context, user) y dispara
la ejecución en thread separado, devolviendo el id de la fila persistida.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime

import agents
from agents.base import RunContext
import contract_validator
import copilot_bridge
import log_streamer
from config import config
from db import session_scope
from models import AgentExecution, Ticket
from services import audit_chain, confidence, egress_policies, embeddings, llm_router, output_cache, pii_masker, webhooks
from services.stacky_logger import logger as stacky_logger


class UnknownAgentError(ValueError):
    pass


def run_agent(
    *,
    agent_type: str,
    ticket_id: int,
    context_blocks: list[dict],
    user: str,
    chain_from: list[int] | None = None,
    pack_run_id: int | None = None,
    pack_step: int | None = None,
    model_override: str | None = None,
    system_prompt_override: str | None = None,
    use_few_shot: bool = True,
    use_anti_patterns: bool = True,
    fingerprint_complexity: str | None = None,
    delta_prefix: str | None = None,
    previous_execution_id: int | None = None,
    runtime: str = "github_copilot",
    vscode_agent_filename: str | None = None,
) -> int:
    agent = agents.get(agent_type)
    if agent is None:
        raise UnknownAgentError(agent_type)

    with session_scope() as session:
        exec_row = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status="running",
            started_by=user,
            started_at=datetime.utcnow(),
            pack_run_id=pack_run_id,
            pack_step=pack_step,
        )
        exec_row.input_context = context_blocks
        exec_row.chain_from = chain_from or []
        session.add(exec_row)
        session.flush()
        execution_id = exec_row.id

    log_streamer.open(execution_id)
    log_streamer.push(execution_id, "info", "▶ start")

    # Registrar estado 'running' en el ticket antes de lanzar el thread
    from services import ticket_status as _ts
    _ts.on_execution_start(
        ticket_id=ticket_id,
        execution_id=execution_id,
        agent_type=agent_type,
        user=user,
    )

    # Log agent start to the centralized system log
    stacky_logger.agent_event(
        "agent_started",
        execution_id=execution_id,
        ticket_id=ticket_id,
        user=user,
        input_data={"agent_type": agent_type, "context_blocks": len(context_blocks)},
        context_data={
            "pack_run_id": pack_run_id,
            "pack_step": pack_step,
            "model_override": model_override,
            "chain_from": chain_from,
            "runtime": runtime,
        },
    )

    import logging as _dispatch_log
    _runner_logger = _dispatch_log.getLogger("stacky_agents.agent_runner")
    _runner_logger.info(
        "agent_run dispatch runtime=%s agent=%s execution_id=%s",
        runtime, agent_type, execution_id,
    )

    # Despachar al runner correcto según el runtime seleccionado por el operador.
    # Regla: NO hay fallback silencioso entre runtimes.
    # - github_copilot / ausente: runner estándar (copilot_bridge + LLM router).
    # - codex_cli: Codex CLI runner. Requiere vscode_agent_filename (validado en endpoint).
    #              Si el CLI no está instalado, el error llega al operador como "error" de ejecución,
    #              no como fallback silencioso.
    # - claude_code_cli: bloqueado en endpoint (HTTP 501). Nunca debería llegar aquí.
    #              Si llega (p.ej. llamada directa al runner), se marca la ejecución como error.
    if runtime == "codex_cli":
        try:
            from services.codex_cli_runner import start_codex_cli_run

            with session_scope() as _cs:
                _ct = _cs.get(Ticket, ticket_id)
                # vscode_agent_filename viene del payload (validado en endpoint).
                # Como fallback defensivo: si el runner se llama sin él (tests directos,
                # packs), intenta resolverlo desde el agente, pero logea warning.
                _vscode_filename = vscode_agent_filename
                if not _vscode_filename:
                    _vscode_filename = (
                        (agent.filename if hasattr(agent, "filename") else None)
                        or f"{agent_type}.agent.md"
                    )
                    _runner_logger.warning(
                        "execution_id=%s: vscode_agent_filename no provisto explícitamente "
                        "para codex_cli; usando '%s' inferido del agente",
                        execution_id, _vscode_filename,
                    )
                _ticket_message = _ct.title if _ct else f"ticket_id={ticket_id}"

            log_streamer.close(execution_id)  # codex_cli_runner abre su propio log_streamer
            _new_exec_id = start_codex_cli_run(
                ticket_id=ticket_id,
                agent_type=agent_type,
                context_blocks=context_blocks,
                user=user,
                vscode_agent_filename=_vscode_filename,
                ticket_message=_ticket_message,
                workspace_root=None,
                model_override=model_override,
            )
            # start_codex_cli_run crea su propia fila de ejecución; la fila
            # original creada aquí queda marcada como reemplazada para evitar
            # rows huérfanas.
            with session_scope() as _cs2:
                _orig = _cs2.get(AgentExecution, execution_id)
                if _orig is not None:
                    _orig.status = "cancelled"
                    _orig.error_message = f"replaced_by={_new_exec_id} (codex_cli)"
                    _orig.completed_at = datetime.utcnow()
            return _new_exec_id
        except Exception as _codex_exc:
            # Sin fallback: cualquier error de codex_cli es error real.
            # Incluye FileNotFoundError (CLI no instalado), NotImplementedError,
            # o cualquier fallo de arranque del runner.
            _runner_logger.error(
                "execution_id=%s: codex_cli runner falló sin fallback: %s",
                execution_id, _codex_exc,
            )
            log_streamer.push(execution_id, "error",
                f"codex_cli runner error: {_codex_exc}")
            _mark_terminal(execution_id, status="error", error=f"codex_cli: {_codex_exc}")
            log_streamer.close(execution_id)
            return execution_id

    elif runtime == "claude_code_cli":
        # Nunca debería llegar aquí: el endpoint /api/agents/run devuelve HTTP 501
        # antes de llamar a run_agent. Si llega (llamada directa al runner, packs),
        # se marca como error explícito sin fallback.
        _runner_logger.error(
            "execution_id=%s: claude_code_cli no implementado — no se acepta esta ejecución",
            execution_id,
        )
        log_streamer.push(execution_id, "error",
            "claude_code_cli runtime no implementado. Usá github_copilot o codex_cli.")
        _mark_terminal(
            execution_id,
            status="error",
            error="claude_code_cli runtime adapter pendiente (not_implemented)",
        )
        log_streamer.close(execution_id)
        return execution_id

    # else: github_copilot → flujo estándar sin cambios.

    thread = threading.Thread(
        target=_run_in_background,
        args=(agent_type, execution_id),
        kwargs={
            "model_override": model_override,
            "system_prompt_override": system_prompt_override,
            "use_few_shot": use_few_shot,
            "use_anti_patterns": use_anti_patterns,
            "fingerprint_complexity": fingerprint_complexity,
            "delta_prefix": delta_prefix,
            "runtime": runtime,
        },
        daemon=True,
    )
    thread.start()

    return execution_id


def cancel(execution_id: int) -> bool:
    copilot_bridge.cancel(execution_id)
    log_streamer.push(execution_id, "warn", "cancel requested")
    return True


def cancel_and_wait(execution_id: int, timeout_seconds: float = 5.0) -> dict:
    """Cancela una ejecución y espera hasta timeout_seconds a que el status deje
    de ser 'running' en la BD.

    Retorna un dict con:
      {
        "cancel_ok": bool,
        "cancel_reason": str | None,   # presente si cancel_ok=False
        "final_status": str | None,    # status de la ejecución al terminar la espera
      }

    Si el timeout se agota y el status sigue en 'running', retorna cancel_ok=False
    con cancel_reason='timeout'. El caller debe continuar el flujo igualmente y
    registrar el fallo.

    Nota: copilot_bridge.cancel() es un flag in-memory. La ejecución puede
    demorar en leer ese flag y actualizar la BD. Este helper da 5s de margen.
    """
    import time

    cancel(execution_id)

    deadline = time.monotonic() + timeout_seconds
    poll_interval = 0.25  # segundos

    while time.monotonic() < deadline:
        try:
            with session_scope() as session:
                row = session.get(AgentExecution, execution_id)
                final_status = row.status if row else None
        except Exception:
            final_status = None

        if final_status != "running":
            return {
                "cancel_ok": True,
                "cancel_reason": None,
                "final_status": final_status,
            }

        time.sleep(poll_interval)

    # Timeout agotado — status aún 'running' (o no pudo leer BD)
    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            final_status = row.status if row else None
    except Exception:
        final_status = None

    return {
        "cancel_ok": False,
        "cancel_reason": "timeout",
        "final_status": final_status,
    }


def _run_in_background(
    agent_type: str,
    execution_id: int,
    *,
    model_override: str | None = None,
    system_prompt_override: str | None = None,
    use_few_shot: bool = True,
    use_anti_patterns: bool = True,
    fingerprint_complexity: str | None = None,
    delta_prefix: str | None = None,
    runtime: str = "github_copilot",
) -> None:
    log = log_streamer.logger_for(execution_id)
    agent = agents.get(agent_type)
    started = datetime.utcnow()
    # Heartbeat thread (Fase 4) — el reaper detecta runs colgados leyendo
    # heartbeat.json. Si el thread del agente muere o se cuelga, el heartbeat
    # deja de actualizarse y el reaper lo marca error.
    _hb_stop = threading.Event()
    _hb_thread: threading.Thread | None = None
    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            raw_blocks = row.input_context
            ticket_id = row.ticket_id
            ticket = session.get(Ticket, ticket_id) if ticket_id else None
            project = ticket.project if ticket else None
            ticket_ado_id = ticket.ado_id if ticket else None

        # Arrancar heartbeat antes del trabajo pesado. Defensive: si la
        # escritura inicial falla, seguimos sin heartbeat (el reaper aplicará
        # timeout absoluto vía EXECUTION_TIMEOUT_MINUTES).
        try:
            from pathlib import Path as _Path
            from services.manifest_watcher import write_heartbeat as _write_hb

            _run_dir = (
                _Path(__file__).resolve().parent / "data" / "codex_runs" / str(execution_id)
            )
            _hb_interval = float(os.getenv("STACKY_HEARTBEAT_INTERVAL_SECONDS", "30"))
            _write_hb(_run_dir, execution_id=execution_id, pid=os.getpid(), phase="started")

            def _hb_loop() -> None:
                while not _hb_stop.wait(timeout=_hb_interval):
                    try:
                        _write_hb(
                            _run_dir,
                            execution_id=execution_id,
                            pid=os.getpid(),
                            phase="running",
                        )
                    except Exception:
                        pass

            _hb_thread = threading.Thread(
                target=_hb_loop,
                daemon=True,
                name=f"agent-runner-hb-{execution_id}",
            )
            _hb_thread.start()
        except Exception as _exc_hb:
            log("warn", f"heartbeat thread no pudo arrancar: {_exc_hb}")

        # Functional agent — Epic structured context injection
        # Cuando el agente es "functional" y el ticket es un Epic, inyecta el
        # context block "ado-epic-structured" con title y description del
        # ticket local (sin llamada a ADO). El agente lo usa como fuente única
        # de requerimientos en Modo A. Si el bloque ya existe (idempotencia),
        # no se re-inyecta.
        with session_scope() as _epic_sess:
            _epic_ticket = _epic_sess.get(Ticket, ticket_id) if ticket_id else None
            _is_epic = (
                _epic_ticket is not None
                and agent_type == "functional"
                and (_epic_ticket.work_item_type or "").strip().lower() == "epic"
            )
            if _is_epic:
                _existing_ids = {b.get("id") for b in (raw_blocks or []) if isinstance(b, dict)}
                if "ado-epic-structured" not in _existing_ids:
                    _epic_block: dict = {
                        "kind": "text",
                        "id": "ado-epic-structured",
                        "title": f"Epic ADO-{_epic_ticket.ado_id}: {_epic_ticket.title}",
                        "content": (
                            f"epic_id: {_epic_ticket.ado_id}\n"
                            f"epic_title: {_epic_ticket.title}\n"
                            f"epic_description:\n{_epic_ticket.description or ''}"
                        ),
                    }
                    raw_blocks = list(raw_blocks or []) + [_epic_block]
                    log("info", f"ado-epic-structured inyectado para Epic ADO-{_epic_ticket.ado_id}")
                else:
                    log("info", "ado-epic-structured ya presente, omitiendo inyección")

        # Filesystem artifacts status — inyecta un bloque informando al agente
        # qué artifacts (comment.html, pending-task.json, MANIFEST de runs
        # previos) ya existen en disco para este ticket. Resuelve Bug #3 del
        # plan de remediación: que el agente no pregunte "¿creo la task?"
        # cuando los archivos ya están generados.
        try:
            from services import artifact_context

            with session_scope() as _art_sess:
                _art_ticket = _art_sess.get(Ticket, ticket_id) if ticket_id else None
                _art_ado_id = _art_ticket.ado_id if _art_ticket else None
                _art_type = _art_ticket.work_item_type if _art_ticket else None
                _exec_rows = (
                    _art_sess.query(AgentExecution.id)
                    .filter(AgentExecution.ticket_id == ticket_id)
                    .order_by(AgentExecution.id.desc())
                    .limit(10)
                    .all()
                    if ticket_id
                    else []
                )
                _exec_ids = [r[0] for r in _exec_rows]
            raw_blocks, _art_info = artifact_context.inject_into_blocks(
                raw_blocks,
                ado_id=_art_ado_id,
                work_item_type=_art_type,
                execution_ids=_exec_ids,
            )
            if _art_info and _art_info.get("injected"):
                log(
                    "info",
                    "filesystem-artifacts-status inyectado "
                    f"(pending={_art_info.get('pending_count')}, "
                    f"consumed={_art_info.get('consumed_count')}, "
                    f"comment_html={_art_info.get('has_comment_html')})",
                )
        except Exception as _exc_art:
            log("warn", f"artifact_context falló (continuando sin bloque): {_exc_art}")

        # ADO similar tickets — inyecta tickets ADO con título parecido para
        # que el agente NO proponga crear duplicados. Solo aplica a agentes
        # que pueden sugerir creación de tickets (functional, technical).
        # Configurable vía STACKY_SIMILAR_TICKETS_ENABLED (default "true").
        if (
            os.getenv("STACKY_SIMILAR_TICKETS_ENABLED", "true").lower() != "false"
            and agent_type in {"functional", "technical"}
            and ticket_ado_id is not None
        ):
            try:
                from services import similar_tickets

                with session_scope() as _sim_sess:
                    _sim_ticket = _sim_sess.get(Ticket, ticket_id) if ticket_id else None
                    _sim_title = _sim_ticket.title if _sim_ticket else ""
                    _sim_project = _sim_ticket.project if _sim_ticket else "Strategist_Pacifico"
                raw_blocks, _sim_info = similar_tickets.inject_into_blocks(
                    raw_blocks,
                    current_ado_id=ticket_ado_id,
                    current_title=_sim_title,
                    project=_sim_project or "Strategist_Pacifico",
                )
                if _sim_info and _sim_info.get("injected"):
                    log(
                        "info",
                        f"ado-similar-tickets inyectado (count={_sim_info.get('count')})",
                    )
            except Exception as _exc_sim:
                log("warn", f"similar_tickets falló (continuando sin bloque): {_exc_sim}")

        # ADO context enrichment — inyecta automáticamente comentarios y
        # adjuntos del ticket desde Azure DevOps al contexto que se envía al
        # chat de Copilot. Por defecto aplica a todos los agentes registrados;
        # configurable vía env ADO_CONTEXT_ENRICH_AGENTS.
        ado_enrich_stats: dict | None = None
        if ticket_ado_id is not None:
            try:
                from services import ado_context
                raw_blocks, ado_enrich_stats = ado_context.enrich(
                    ticket_id=ticket_id,
                    agent_type=agent_type,
                    existing_blocks=raw_blocks or [],
                    ado_id=ticket_ado_id,
                    log=log,
                    return_stats=True,
                )
            except Exception as _exc_ado:
                log("warn", f"ado_context enrich falló (continuando sin enrichment): {_exc_ado}")
                ado_enrich_stats = {"error": str(_exc_ado)}

        # FA-37 — PII masking ANTES de cualquier procesamiento (cache, prompt, etc.)
        masked_blocks, mask_map = pii_masker.mask_blocks(raw_blocks)
        if mask_map:
            log("info", f"PII masking: {len(mask_map)} ocurrencias enmascaradas")

        # FA-31 — Output cache lookup (sobre blocks ya masked → cache key estable)
        cached = output_cache.lookup(agent_type=agent_type, blocks=masked_blocks) if config.CACHE_ENABLED else None
        if cached is not None:
            log("info", f"🔁 cached output (cache_key={cached['cache_key'][:8]}…, hits={cached['hits']})")
            with session_scope() as session:
                row = session.get(AgentExecution, execution_id)
                # Re-hidratar PII en el output cacheado para que el operador vea datos correctos.
                cached_output = pii_masker.unmask(cached["output"] or "", mask_map)
                row.output = cached_output
                row.output_format = cached["output_format"]
                md = dict(cached.get("metadata") or {})
                md["duration_ms"] = int((datetime.utcnow() - started).total_seconds() * 1000)
                md["from_cache"] = True
                md["cache_key"] = cached["cache_key"]
                md["pii_masked"] = bool(mask_map)
                md["runtime"] = runtime
                if ado_enrich_stats is not None:
                    md["ado_context"] = ado_enrich_stats
                # Feature C: persistir agent_filename para el comparador de agentes
                if "agent_filename" not in md and hasattr(agent, "filename"):
                    md["agent_filename"] = agent.filename
                row.metadata_dict = md
                row.contract_result = cached.get("contract_result")
                row.status = "completed"
                row.completed_at = datetime.utcnow()
            log("info", f"✓ done from cache ({md.get('duration_ms')}ms)")
            stacky_logger.agent_event(
                "agent_completed_from_cache",
                execution_id=execution_id,
                ticket_id=ticket_id,
                level="INFO",
                duration_ms=md.get("duration_ms"),
                output_data={"cache_key": cached["cache_key"][:8], "hits": cached.get("hits")},
                tags=["agent", "cache"],
            )
            webhooks.fire_completed_safe(execution_id)
            return

        # FA-04 — Multi-LLM routing
        backend = config.LLM_BACKEND.lower()
        decision = llm_router.decide(
            agent_type=agent_type,
            blocks=masked_blocks,
            fingerprint_complexity=fingerprint_complexity,
            override=model_override,
            backend=backend,
        )
        log("info", f"router → {decision.model} ({decision.reason})")

        # Texto unificado del contexto para matching de decisiones (FA-13) y egress (FA-41)
        # Se construye una vez y se reusa.
        ctx_text_parts: list[str] = []
        for b in masked_blocks or []:
            if b.get("title"):
                ctx_text_parts.append(b["title"])
            if isinstance(b.get("content"), str):
                ctx_text_parts.append(b["content"])
            for it in b.get("items") or []:
                if it.get("selected"):
                    ctx_text_parts.append(it.get("label", ""))
        context_text = "\n".join(ctx_text_parts)

        # FA-41 — Egress policy check (después del router, antes de invocar)
        egress = egress_policies.check(
            project=project, model=decision.model, context_text=context_text
        )
        if not egress.allowed:
            log("error", f"× egress blocked: {egress.reason}")
            _mark_terminal(execution_id, status="error", error=egress.reason)
            log_streamer.close(execution_id)
            return
        if egress.warning_classes:
            log("warn", f"egress warning: detected {egress.detected_classes}")

        with session_scope() as _s2:
            _row2 = _s2.get(AgentExecution, execution_id)
            _user = _row2.started_by if _row2 else ""

        run_ctx = RunContext(
            ticket_id=ticket_id,
            project=project,
            model_override=decision.model,
            system_prompt_override=system_prompt_override,
            use_few_shot=use_few_shot,
            use_anti_patterns=use_anti_patterns,
            use_decisions=True,
            context_text=context_text,
            delta_prefix=delta_prefix,
            started_by=_user,
        )
        result = agent.run(masked_blocks, log=log, execution_id=execution_id, run_ctx=run_ctx)
        # Re-hidratar PII en output antes de mostrarlo / persistir.
        if mask_map:
            result.output = pii_masker.unmask(result.output or "", mask_map)

        # N1 — Contract Validator: valida el output antes de persistir
        log("info", "validando contrato del output…")
        cv_result = contract_validator.validate(agent_type, result.output or "")
        log(
            "info" if cv_result.passed else "warn",
            f"contrato {'OK' if cv_result.passed else 'WARNINGS'} — score {cv_result.score}/100"
            + (f" ({len(cv_result.failures)} errores)" if cv_result.failures else ""),
        )

        # FA-35 — Confidence scoring del output
        conf = confidence.score(result.output or "")
        log(
            "info" if conf.overall >= 70 else "warn",
            f"confidence {conf.overall}/100"
            + (f" (señales: {len(conf.signals)})" if conf.signals else ""),
        )

        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            row.output = result.output
            row.output_format = result.output_format
            md = result.metadata or {}
            md["duration_ms"] = int((datetime.utcnow() - started).total_seconds() * 1000)
            md["from_cache"] = False
            md["confidence"] = conf.to_dict()
            md["routing_reason"] = decision.reason
            md["pii_masked"] = bool(mask_map)
            md["runtime"] = runtime
            if ado_enrich_stats is not None:
                md["ado_context"] = ado_enrich_stats
            # Feature C: persistir agent_filename para el comparador de agentes
            if "agent_filename" not in md and hasattr(agent, "filename"):
                md["agent_filename"] = agent.filename
            row.metadata_dict = md
            row.contract_result = cv_result.to_dict()
            row.status = "completed"
            row.completed_at = datetime.utcnow()
        log("info", f"✓ done ({md.get('duration_ms')}ms)")

        stacky_logger.agent_event(
            "agent_completed",
            execution_id=execution_id,
            ticket_id=ticket_id,
            level="INFO",
            duration_ms=md.get("duration_ms"),
            output_data={
                "output_chars": len(result.output or ""),
                "confidence": conf.overall,
                "contract_passed": cv_result.passed,
                "contract_score": cv_result.score,
                "model": decision.model,
                "from_cache": False,
            },
            tags=["agent"],
        )

        # FA-31 — Persistir en cache solo si pasó el contrato.
        # Importante: cacheamos la versión MASKED del output (re-hidratamos al servir).
        if config.CACHE_ENABLED and cv_result.passed:
            output_cache.store(
                agent_type=agent_type,
                blocks=masked_blocks,
                output=pii_masker.mask(result.output or "", mask_map) if mask_map else (result.output or ""),
                output_format=result.output_format,
                metadata=md,
                contract_result=cv_result.to_dict(),
            )

        # FA-52 — Webhooks out
        webhooks.fire_completed_safe(execution_id)
        # FA-39 — Audit chain seal
        audit_chain.seal(execution_id)
        # FA-01 — Indexar para retrieval
        try:
            embeddings.index_execution(execution_id)
        except Exception as exc:  # noqa: BLE001
            log("warn", f"embeddings index failed: {exc}")
        # Actualizar estado del ticket a 'completed'
        from services import ticket_status as _ts
        _ts.on_execution_end(
            ticket_id=ticket_id,
            execution_id=execution_id,
            final_status="completed",
            agent_type=agent_type,
        )
    except copilot_bridge.CancelledError:
        _mark_terminal(execution_id, status="cancelled")
        log("warn", "× cancelled")
        stacky_logger.agent_event(
            "agent_cancelled",
            execution_id=execution_id,
            ticket_id=ticket_id,
            level="WARNING",
            tags=["agent", "cancelled"],
        )
        from services import ticket_status as _ts
        _ts.on_execution_end(
            ticket_id=ticket_id,
            execution_id=execution_id,
            final_status="cancelled",
            agent_type=agent_type,
        )
    except Exception as exc:  # noqa: BLE001
        _mark_terminal(execution_id, status="error", error=str(exc))
        log("error", f"× {exc}")
        stacky_logger.agent_event(
            "agent_failed",
            execution_id=execution_id,
            ticket_id=ticket_id,
            level="ERROR",
            error_exc=exc,
            tags=["agent", "error"],
        )
        from services import ticket_status as _ts
        _ts.on_execution_end(
            ticket_id=ticket_id,
            execution_id=execution_id,
            final_status="error",
            agent_type=agent_type,
            error=str(exc),
        )
    finally:
        _hb_stop.set()
        if _hb_thread is not None and _hb_thread.is_alive():
            _hb_thread.join(timeout=2)
        log_streamer.close(execution_id)


def _mark_terminal(execution_id: int, *, status: str, error: str | None = None) -> None:
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        row.status = status
        row.error_message = error
        row.completed_at = datetime.utcnow()
