"""
Núcleo de ejecución. Recibe (agent_type, ticket_id, context, user) y dispara
la ejecución en thread separado, devolviendo el id de la fila persistida.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path

import agents
from agents.base import RunContext
import contract_validator
import copilot_bridge
import log_streamer
from config import config
from db import session_scope
from models import AgentExecution, Ticket
from services import audit_chain, confidence, desktop_notifier, egress_policies, embeddings, llm_router, output_cache, pii_masker, webhooks
from services.project_context import ensure_project_vscode, resolve_project_context
from services.stacky_logger import logger as stacky_logger


class UnknownAgentError(ValueError):
    pass


# ── Plan 38 C0 — Helpers de trazabilidad ─────────────────────────────────────

def _build_trace_metadata(
    *,
    prompt_blocks: list,
    agent_type: str,
    agent_name: str,
    prompt_text_enabled: bool = False,
) -> dict:
    """Construye el dict de trazabilidad que se fusiona con setdefault en metadata.

    - prompt_sha: SHA256 del JSON de los context_blocks (inputs del prompt).
    - prompt_len: longitud en bytes del JSON serializado.
    - agent_type / agent_name: identidad del agente.
    - prompt_text: solo si prompt_text_enabled=True (privacidad: default OFF).
    """
    serialized = json.dumps(prompt_blocks, sort_keys=True, ensure_ascii=False)
    sha = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    meta: dict = {
        "prompt_sha": sha,
        "prompt_len": len(serialized.encode("utf-8")),
        "agent_type": agent_type,
        "agent_name": agent_name,
    }
    if prompt_text_enabled:
        meta["prompt_text"] = serialized
    return meta


def _collect_produced_files(output_dir: Path | None) -> list[str]:
    """Retorna paths relativos de archivos bajo output_dir (vacío si no existe)."""
    if output_dir is None:
        return []
    try:
        p = Path(output_dir)
        if not p.exists():
            return []
        return [
            str(f.relative_to(p)).replace("\\", "/")
            for f in sorted(p.rglob("*"))
            if f.is_file()
        ]
    except Exception:
        return []


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
    effort_override: str | None = None,
    system_prompt_override: str | None = None,
    use_few_shot: bool = True,
    use_anti_patterns: bool = True,
    fingerprint_complexity: str | None = None,
    delta_prefix: str | None = None,
    previous_execution_id: int | None = None,
    runtime: str = "github_copilot",
    vscode_agent_filename: str | None = None,
    project_name: str | None = None,
    work_item_type: str = "Epic",
) -> int:
    agent = agents.get(agent_type)
    if agent is None:
        raise UnknownAgentError(agent_type)

    # G0.1 — Gate de precondiciones determinista (solo si flag ON).
    # Con flag OFF: no-op, byte-idéntico al comportamiento anterior.
    try:
        from services.run_preflight import check as _preflight_check
        with session_scope() as _pf_session:
            _ticket_obj = _pf_session.query(Ticket).filter_by(id=ticket_id).first()
        _pf_result = _preflight_check(
            ticket=_ticket_obj, runtime=runtime, project=project_name
        )
        if not _pf_result.ok:
            with session_scope() as _pf_fail_session:
                _pf_exec = AgentExecution(
                    ticket_id=ticket_id,
                    agent_type=agent_type,
                    status="failed",
                    started_by=user,
                    started_at=datetime.utcnow(),
                )
                _pf_exec.input_context = context_blocks
                _pf_exec.chain_from = chain_from or []
                _pf_exec_meta = _pf_result.to_metadata()
                _pf_exec_meta["runtime"] = runtime
                _pf_exec.metadata_dict = _pf_exec_meta
                _pf_fail_session.add(_pf_exec)
                _pf_fail_session.flush()
                _pf_exec_id = _pf_exec.id
            import logging as _log_mod
            _log_mod.getLogger("stacky.agent_runner").warning(
                "G0.1 preflight gate bloqueó run: ticket=%d runtime=%s check=%s detail=%s",
                ticket_id, runtime, _pf_result.failure_check, _pf_result.failure_detail,
            )
            return _pf_exec_id
    except Exception as _pf_exc:  # noqa: BLE001
        # Fallos del propio gate no bloquean el run (fail-open seguro).
        import logging as _log_mod2
        _log_mod2.getLogger("stacky.agent_runner").warning(
            "G0.1 preflight gate lanzó excepción (ignorada, continúa run): %s", _pf_exc
        )

    if runtime in {"codex_cli", "claude_code_cli"}:
        return _start_cli_runtime(
            runtime=runtime,
            agent=agent,
            agent_type=agent_type,
            ticket_id=ticket_id,
            context_blocks=context_blocks,
            user=user,
            vscode_agent_filename=vscode_agent_filename,
            model_override=model_override,
            effort_override=effort_override,
            project_name=project_name,
            work_item_type=work_item_type,
        )

    with session_scope() as session:
        exec_row = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status="preparing",
            started_by=user,
            started_at=datetime.utcnow(),
            pack_run_id=pack_run_id,
            pack_step=pack_step,
        )
        exec_row.input_context = context_blocks
        exec_row.chain_from = chain_from or []
        # Plan 36 — F4: persistir runtime en metadata desde el inicio.
        # Los runners CLI (codex/claude) ya lo hacen; este path (github_copilot)
        # faltaba. setdefault garantiza que no se sobreescriba si ya fue puesto.
        md = dict(exec_row.metadata_dict or {})
        md.setdefault("runtime", runtime)
        # Plan 45 F2 — sellar el tipo de work item destino (Epic/Issue) desde el
        # inicio para que el frontend pueda mostrarlo. La autopublicación de Issue
        # vive en el finalizador del runner CLI; este path (github_copilot) no
        # autopublica, pero igual deja la trazabilidad.
        md.setdefault("work_item_type", work_item_type)
        exec_row.metadata_dict = md
        session.add(exec_row)
        session.flush()
        execution_id = exec_row.id

    log_streamer.open(execution_id)
    log_streamer.push(
        execution_id,
        "info",
        "preparando ejecucion",
        group="pre_run",
        event_type="pre_run",
    )
    log_streamer.push(execution_id, "info", "▶ start")

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

            workspace_root: str | None = None
            stacky_project_name: str | None = project_name
            with session_scope() as _cs:
                _ct = _cs.get(Ticket, ticket_id)
                _project_ctx = resolve_project_context(project_name=project_name, ticket=_ct)
                if _project_ctx:
                    workspace_root = _project_ctx.workspace_root
                    stacky_project_name = _project_ctx.stacky_project_name
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
                workspace_root=workspace_root,
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
                    md = dict(_orig.metadata_dict or {})
                    md["runtime"] = runtime
                    md["stacky_project_name"] = stacky_project_name
                    md["workspace_root"] = workspace_root
                    _orig.metadata_dict = md
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
            # V0.3 — el spawn falló antes del _run_in_background (cuyo finally
            # libera el slot); liberar acá para no filtrar la cuota.
            try:
                from services import run_slots
                run_slots.release()
            except Exception:  # noqa: BLE001
                pass
            log_streamer.close(execution_id)
            return execution_id

    elif runtime == "claude_code_cli":
        try:
            from services.claude_code_cli_runner import start_claude_code_cli_run

            workspace_root: str | None = None
            stacky_project_name: str | None = project_name
            with session_scope() as _cs:
                _ct = _cs.get(Ticket, ticket_id)
                _project_ctx = resolve_project_context(project_name=project_name, ticket=_ct)
                if _project_ctx:
                    workspace_root = _project_ctx.workspace_root
                    stacky_project_name = _project_ctx.stacky_project_name
                # vscode_agent_filename viene del payload (validado en endpoint).
                # Fallback defensivo para llamadas directas (tests, packs).
                _vscode_filename = vscode_agent_filename
                if not _vscode_filename:
                    _vscode_filename = (
                        (agent.filename if hasattr(agent, "filename") else None)
                        or f"{agent_type}.agent.md"
                    )
                    _runner_logger.warning(
                        "execution_id=%s: vscode_agent_filename no provisto explícitamente "
                        "para claude_code_cli; usando '%s' inferido del agente",
                        execution_id, _vscode_filename,
                    )
                _ticket_message = _ct.title if _ct else f"ticket_id={ticket_id}"

            log_streamer.close(execution_id)  # claude_code_cli_runner abre su propio log_streamer
            _new_exec_id = start_claude_code_cli_run(
                ticket_id=ticket_id,
                agent_type=agent_type,
                context_blocks=context_blocks,
                user=user,
                vscode_agent_filename=_vscode_filename,
                ticket_message=_ticket_message,
                workspace_root=workspace_root,
                model_override=model_override,
            )
            # start_claude_code_cli_run crea su propia fila de ejecución; la fila
            # original creada aquí queda marcada como reemplazada para evitar
            # rows huérfanas.
            with session_scope() as _cs2:
                _orig = _cs2.get(AgentExecution, execution_id)
                if _orig is not None:
                    _orig.status = "cancelled"
                    _orig.error_message = f"replaced_by={_new_exec_id} (claude_code_cli)"
                    _orig.completed_at = datetime.utcnow()
                    md = dict(_orig.metadata_dict or {})
                    md["runtime"] = runtime
                    md["stacky_project_name"] = stacky_project_name
                    md["workspace_root"] = workspace_root
                    _orig.metadata_dict = md
            return _new_exec_id
        except Exception as _claude_exc:
            # Sin fallback: cualquier error de claude_code_cli es error real.
            # Incluye FileNotFoundError (CLI no instalado) o fallo de arranque.
            _runner_logger.error(
                "execution_id=%s: claude_code_cli runner falló sin fallback: %s",
                execution_id, _claude_exc,
            )
            log_streamer.push(execution_id, "error",
                f"claude_code_cli runner error: {_claude_exc}")
            _mark_terminal(execution_id, status="error", error=f"claude_code_cli: {_claude_exc}")
            # V0.3 — el spawn falló antes del _run_in_background (cuyo finally
            # libera el slot); liberar acá para no filtrar la cuota.
            try:
                from services import run_slots
                run_slots.release()
            except Exception:  # noqa: BLE001
                pass
            log_streamer.close(execution_id)
            return execution_id

    # else: github_copilot → flujo estándar sin cambios.

    thread = threading.Thread(
        target=_pre_run_then_run_in_background,
        args=(agent_type, execution_id),
        kwargs={
            "ticket_id": ticket_id,
            "user": user,
            "model_override": model_override,
            "system_prompt_override": system_prompt_override,
            "use_few_shot": use_few_shot,
            "use_anti_patterns": use_anti_patterns,
            "fingerprint_complexity": fingerprint_complexity,
            "delta_prefix": delta_prefix,
            "runtime": runtime,
            "project_name": project_name,
        },
        daemon=True,
    )
    thread.start()

    return execution_id


def _start_cli_runtime(
    *,
    runtime: str,
    agent,
    agent_type: str,
    ticket_id: int,
    context_blocks: list[dict],
    user: str,
    vscode_agent_filename: str | None,
    model_override: str | None,
    effort_override: str | None = None,
    project_name: str | None,
    work_item_type: str = "Epic",
) -> int:
    workspace_root: str | None = None
    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        project_ctx = resolve_project_context(project_name=project_name, ticket=ticket)
        if project_ctx:
            workspace_root = project_ctx.workspace_root
        resolved_filename = vscode_agent_filename
        if not resolved_filename:
            resolved_filename = (
                (agent.filename if hasattr(agent, "filename") else None)
                or f"{agent_type}.agent.md"
            )
        ticket_message = ticket.title if ticket else f"ticket_id={ticket_id}"

    if runtime == "codex_cli":
        from services.codex_cli_runner import start_codex_cli_run

        return start_codex_cli_run(
            ticket_id=ticket_id,
            agent_type=agent_type,
            context_blocks=context_blocks,
            user=user,
            vscode_agent_filename=resolved_filename,
            ticket_message=ticket_message,
            workspace_root=workspace_root,
            model_override=model_override,
        )

    if runtime == "claude_code_cli":
        from services.claude_code_cli_runner import start_claude_code_cli_run

        return start_claude_code_cli_run(
            ticket_id=ticket_id,
            agent_type=agent_type,
            context_blocks=context_blocks,
            user=user,
            vscode_agent_filename=resolved_filename,
            ticket_message=ticket_message,
            workspace_root=workspace_root,
            model_override=model_override,
            effort_override=effort_override,
            work_item_type=work_item_type,
        )

    raise ValueError(f"unsupported cli runtime: {runtime}")


def _pre_run_then_run_in_background(
    agent_type: str,
    execution_id: int,
    *,
    ticket_id: int,
    user: str,
    project_name: str | None = None,
    **kwargs,
) -> None:
    if not _run_pre_run_checks(execution_id, project_name=project_name):
        return

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            log_streamer.close(execution_id)
            return
        if row.status == "cancelled":
            log_streamer.push(execution_id, "warn", "ejecucion cancelada durante preparacion")
            log_streamer.close(execution_id)
            return
        row.status = "running"

    log_streamer.push(execution_id, "info", "pre-run completo; iniciando agente")
    from services import ticket_status as _ts
    _ts.on_execution_start(
        ticket_id=ticket_id,
        execution_id=execution_id,
        agent_type=agent_type,
        user=user,
    )
    _run_in_background(agent_type, execution_id, project_name=project_name, **kwargs)


def _run_pre_run_checks(execution_id: int, *, project_name: str | None = None) -> bool:
    from services.pre_run_git import run_pull_check

    def log(level: str, message: str) -> None:
        log_streamer.push(
            execution_id,
            level,
            message,
            group="pre_run",
            event_type="pre_run",
        )

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            log_streamer.close(execution_id)
            return False
        ticket = session.get(Ticket, row.ticket_id) if row.ticket_id else None
        project_ctx = resolve_project_context(project_name=project_name, ticket=ticket)
        workspace_root = project_ctx.workspace_root if project_ctx else None

    result = run_pull_check(workspace_root, project=project_name, log=log)
    md = {"pre_run": {"git_pull_check": result.to_dict()}}
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            log_streamer.close(execution_id)
            return False
        current_md = row.metadata_dict
        current_md.update(md)
        row.metadata_dict = current_md

    if not result.ok:
        error = "; ".join(result.errors or result.warnings or ["pre-run git check failed"])
        log("error", "pre-run bloqueado: " + error)
        _mark_terminal(execution_id, status="error", error=error)
        log_streamer.close(execution_id)
        return False

    for warning in result.warnings:
        log("warn", warning)
    return True


def cancel(execution_id: int) -> bool:
    copilot_bridge.cancel(execution_id)
    log_streamer.push(execution_id, "warn", "cancel requested")
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is not None and row.status == "preparing":
            row.status = "cancelled"
            row.completed_at = datetime.utcnow()
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

        if final_status not in {"preparing", "running"}:
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
    project_name: str | None = None,
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
            project_ctx = resolve_project_context(project_name=project_name, ticket=ticket)

        if (
            (config.LLM_BACKEND or "").lower() == "vscode_bridge"
            and runtime == "github_copilot"
            and project_ctx is not None
        ):
            try:
                project_ctx = ensure_project_vscode(project_ctx.stacky_project_name)
                log(
                    "info",
                    "vscode bridge listo "
                    f"(project={project_ctx.stacky_project_name}, "
                    f"workspace_root={project_ctx.workspace_root}, "
                    f"bridge_port={project_ctx.vscode_port})",
                )
            except Exception as exc:  # noqa: BLE001
                log("error", f"no se pudo preparar VS Code del proyecto: {exc}")
                _mark_terminal(execution_id, status="error", error=str(exc))
                log_streamer.close(execution_id)
                return

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

        # Pipeline de enriquecimiento de contexto (épica + artifacts + similares
        # + comentarios/adjuntos ADO). Extraído a services/context_enrichment.py
        # para que los runtimes CLI (codex_cli / claude_code_cli) inyecten el mismo
        # contexto. El comportamiento aquí es idéntico al histórico inline.
        from services import context_enrichment

        raw_blocks, ado_enrich_stats = context_enrichment.enrich_blocks(
            ticket_id=ticket_id,
            agent_type=agent_type,
            raw_blocks=raw_blocks,
            project_ctx=project_ctx,
            log=log,
        )

        # Plan 133 F5 — garantía pre-spawn de stacky_required_blocks. Este path
        # (github_copilot) no tiene vscode_agent_filename en su firma —
        # enforce() es no-op con filename None (copilot puede correr sin
        # agente VS Code, C5).
        try:
            from services import agent_contract

            agent_contract.enforce(vscode_agent_filename=None, blocks=raw_blocks)
        except agent_contract.AgentContractError as _ac_exc:
            log("error", f"contrato de contexto incumplido: {_ac_exc}")
            with session_scope() as _ac_session:
                _ac_row = _ac_session.get(AgentExecution, execution_id)
                if _ac_row is not None:
                    _ac_md = dict(_ac_row.metadata_dict or {})
                    _ac_md["context_contract_failure"] = {
                        "agent": None, "detail": str(_ac_exc),
                    }
                    _ac_row.metadata_dict = _ac_md
            _mark_terminal(execution_id, status="error", error=str(_ac_exc))
            if ticket_id is not None:
                from services import ticket_status as _ts

                _ts.on_execution_end(
                    ticket_id=ticket_id,
                    execution_id=execution_id,
                    final_status="error",
                    agent_type=agent_type,
                    error=str(_ac_exc),
                )
            log_streamer.close(execution_id)
            return

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
            webhooks.fire_for_execution(execution_id)
            try:
                if config.STACKY_DESKTOP_NOTIFY_ENABLED:
                    desktop_notifier.notify(
                        title=f"Stacky · {agent_type} completed",
                        message=f"Ticket {ticket_id} · github_copilot",
                    )
            except Exception:  # noqa: BLE001
                logger.debug("desktop notify failed on completed", exc_info=True)
            return

        # I0.2 — Cómputo de fingerprint_complexity si no viene del caller y el flag está ON.
        # El caller puede pasar un valor explícito (fingerprint_complexity != None);
        # en ese caso se respeta y no se recalcula.
        _effective_complexity = fingerprint_complexity
        if _effective_complexity is None and config.STACKY_COMPLEXITY_ESTIMATION_ENABLED:
            try:
                from harness.complexity import estimate_complexity as _est_complexity
                _ticket_obj = None
                _title = ""
                _description = ""
                try:
                    with session_scope() as _sess_c:
                        _ticket_obj = _sess_c.get(Ticket, ticket_id)
                        if _ticket_obj is not None:
                            _title = _ticket_obj.title or ""
                            _description = _ticket_obj.description or ""
                except Exception:
                    pass
                _effective_complexity = _est_complexity(
                    agent_type=agent_type or "",
                    ticket_title=_title,
                    ticket_description=_description,
                    blocks=masked_blocks,
                )
                log("info", f"complexity estimation → {_effective_complexity} (I0.2)")
            except Exception as _exc_c:  # noqa: BLE001 — estimación nunca bloquea el run
                log("warn", f"complexity estimation falló (no crítico): {_exc_c}")

        # FA-04 — Multi-LLM routing
        backend = config.LLM_BACKEND.lower()
        decision = llm_router.decide(
            agent_type=agent_type,
            blocks=masked_blocks,
            fingerprint_complexity=_effective_complexity,
            override=model_override,
            backend=backend,
            project_name=project_name,
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
            stacky_project_name=project_ctx.stacky_project_name if project_ctx else project_name,
            workspace_root=project_ctx.workspace_root if project_ctx else None,
            bridge_port=project_ctx.vscode_port if project_ctx else None,
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

        # Plan 77 F3 (Copilot) — Postea análisis de fase del Issue (si aplica).
        # No-fatal: devuelve None o dict; nunca lanza.
        try:
            from api.tickets import publish_issue_phase_from_run as _pub_issue_phase  # noqa: PLC0415
            _issue_phase_meta = _pub_issue_phase(
                ticket_id=ticket_id,
                agent_type=agent_type,
                output=result.output or "",
                project_name=None,  # el helper lo lee de la Ticket
            )
        except Exception:  # noqa: BLE001
            _issue_phase_meta = None

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
            # Plan 38 C0 — Trazabilidad: prompt_sha, agent_type, produced_files
            if config.STACKY_EXECUTION_TRACE_ENABLED:
                _trace = _build_trace_metadata(
                    prompt_blocks=masked_blocks or [],
                    agent_type=agent_type or getattr(agent, "type", ""),
                    agent_name=getattr(agent, "name", ""),
                    prompt_text_enabled=config.STACKY_TRACE_PROMPT_TEXT_ENABLED,
                )
                for k, v in _trace.items():
                    md.setdefault(k, v)
                # produced_files: resolver directorio de output del ticket
                if "produced_files" not in md:
                    try:
                        from api.executions import _resolve_ticket_output_dir_ws1
                        _ticket_for_trace = session.get(Ticket, ticket_id) if ticket_id else None
                        _out_dir = _resolve_ticket_output_dir_ws1(row, _ticket_for_trace)
                    except Exception:
                        _out_dir = None
                    md["produced_files"] = _collect_produced_files(_out_dir)
            # Plan 77 F3 — persiste metadatos de fase del Issue en execution row.
            if _issue_phase_meta is not None:
                md["issue_phase"] = _issue_phase_meta
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

        # FA-52/U0.3 — Webhooks out
        webhooks.fire_for_execution(execution_id)
        try:
            if config.STACKY_DESKTOP_NOTIFY_ENABLED:
                desktop_notifier.notify(
                    title=f"Stacky · {agent_type} completed",
                    message=f"Ticket {ticket_id} · github_copilot",
                )
        except Exception:  # noqa: BLE001
            logger.debug("desktop notify failed on completed", exc_info=True)
        # FA-39 — Audit chain seal
        audit_chain.seal(execution_id)
        # FA-01 — Indexar para retrieval
        try:
            embeddings.index_execution(execution_id)
        except Exception as exc:  # noqa: BLE001
            log("warn", f"embeddings index failed: {exc}")
        try:
            from services import post_run_memory

            memory_id = post_run_memory.capture_on_completion(execution_id)
            if memory_id:
                log("info", f"stacky-memory draft capturado: {memory_id}")
        except Exception as exc:  # noqa: BLE001
            log("warn", f"post_run_memory completion hook falló: {exc}")
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
        try:
            if config.STACKY_DESKTOP_NOTIFY_ENABLED:
                desktop_notifier.notify(
                    title=f"Stacky · {agent_type} cancelled",
                    message=f"Ticket {ticket_id} · github_copilot",
                )
        except Exception:  # noqa: BLE001
            logger.debug("desktop notify failed on cancelled", exc_info=True)
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
        webhooks.fire_for_execution(execution_id)
        try:
            if config.STACKY_DESKTOP_NOTIFY_ENABLED:
                desktop_notifier.notify(
                    title=f"Stacky · {agent_type} error",
                    message=f"Ticket {ticket_id} · github_copilot",
                )
        except Exception:  # noqa: BLE001
            logger.debug("desktop notify failed on error", exc_info=True)
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
