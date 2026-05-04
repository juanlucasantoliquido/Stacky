"""
Núcleo de ejecución. Recibe (agent_type, ticket_id, context, user) y dispara
la ejecución en thread separado, devolviendo el id de la fila persistida.
"""
from __future__ import annotations

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
        },
        daemon=True,
    )
    thread.start()

    return execution_id


def cancel(execution_id: int) -> bool:
    copilot_bridge.cancel(execution_id)
    log_streamer.push(execution_id, "warn", "cancel requested")
    return True


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
) -> None:
    log = log_streamer.logger_for(execution_id)
    agent = agents.get(agent_type)
    started = datetime.utcnow()
    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            raw_blocks = row.input_context
            ticket_id = row.ticket_id
            ticket = session.get(Ticket, ticket_id) if ticket_id else None
            project = ticket.project if ticket else None
            ticket_ado_id = ticket.ado_id if ticket else None

        # ADO context enrichment — para agentes technical y developer inyecta
        # comentarios y adjuntos del ticket desde Azure DevOps.
        if ticket_ado_id is not None:
            try:
                from services import ado_context
                raw_blocks = ado_context.enrich(
                    ticket_id=ticket_id,
                    agent_type=agent_type,
                    existing_blocks=raw_blocks or [],
                    ado_id=ticket_ado_id,
                    log=log,
                )
            except Exception as _exc_ado:
                log("warn", f"ado_context enrich falló (continuando sin enrichment): {_exc_ado}")

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
                row.metadata_dict = md
                row.contract_result = cached.get("contract_result")
                row.status = "completed"
                row.completed_at = datetime.utcnow()
            log("info", f"✓ done from cache ({md.get('duration_ms')}ms)")
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
            row.metadata_dict = md
            row.contract_result = cv_result.to_dict()
            row.status = "completed"
            row.completed_at = datetime.utcnow()
        log("info", f"✓ done ({md.get('duration_ms')}ms)")

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
    except copilot_bridge.CancelledError:
        _mark_terminal(execution_id, status="cancelled")
        log("warn", "× cancelled")
    except Exception as exc:  # noqa: BLE001
        _mark_terminal(execution_id, status="error", error=str(exc))
        log("error", f"× {exc}")
    finally:
        log_streamer.close(execution_id)


def _mark_terminal(execution_id: int, *, status: str, error: str | None = None) -> None:
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        row.status = status
        row.error_message = error
        row.completed_at = datetime.utcnow()
