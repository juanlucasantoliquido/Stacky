"""Codex CLI runtime for Stacky Agents.

This runner lets the same GitHub Copilot custom-agent prompts be launched
through `codex exec`. It keeps Stacky in control by creating an execution row,
streaming CLI stdout/stderr into the execution log buffer, and marking the run
terminal when the process exits.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import log_streamer
from config import config
from db import session_scope
from models import AgentExecution, Ticket
from services import (
    context_enrichment,
    desktop_notifier,
    pii_masker,
    stacky_agents as stacky_agents_svc,
    ticket_status,
    vscode_agents,
    webhooks,
)
from services.agent_env import build_agent_env
from services.manifest_watcher import append_event, write_heartbeat, write_manifest
from services.project_context import resolve_project_context
from services.stacky_logger import logger as stacky_logger

logger = logging.getLogger("stacky_agents.codex_cli")

RUNTIME = "codex_cli"

_PROCESSES: dict[int, subprocess.Popen[str]] = {}
_PROCESSES_LOCK = threading.Lock()
_RESUME_LOCKS: dict[int, threading.Lock] = {}


def _push(
    execution_id: int,
    level: str,
    message: str,
    group: str | None = None,
    indent: int = 0,
) -> None:
    """Push to Stacky SSE logs and mirror the same line to the backend console."""
    log_streamer.push(execution_id, level, message, group=group, indent=indent)
    backend_level = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }.get(level, logging.INFO)
    logger.log(backend_level, "[exec=%s] %s", execution_id, message)


def _notify_outcome(
    *, execution_id: int, ticket_id: int | None, agent_type: str | None, status: str
) -> None:
    try:
        webhooks.fire_for_execution(execution_id)
    except Exception:  # noqa: BLE001
        logger.debug("[exec=%s] webhook fire_for_execution failed", execution_id, exc_info=True)

    if not config.STACKY_DESKTOP_NOTIFY_ENABLED:
        return
    try:
        desktop_notifier.notify(
            title=f"Stacky · {agent_type or 'agent'} {status}",
            message=f"Ticket {ticket_id or 'N/A'} · {RUNTIME}",
        )
    except Exception:  # noqa: BLE001
        logger.debug("[exec=%s] desktop notify failed", execution_id, exc_info=True)


def start_codex_cli_run(
    *,
    ticket_id: int,
    agent_type: str,
    context_blocks: list[dict],
    user: str,
    vscode_agent_filename: str,
    ticket_message: str,
    workspace_root: str | None = None,
    model_override: str | None = None,
) -> int:
    """Create an execution row and launch Codex CLI in the background."""
    with session_scope() as session:
        exec_row = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status="preparing",
            started_by=user,
            started_at=datetime.utcnow(),
        )
        exec_row.input_context = context_blocks
        exec_row.metadata_dict = {
            "runtime": RUNTIME,
            "vscode_agent_filename": vscode_agent_filename,
            "workspace_root": workspace_root,
            "model_override": model_override,
        }
        session.add(exec_row)
        session.flush()
        execution_id = exec_row.id

        # Plan 79 F2 — estado-en-progreso determinista al iniciar (paridad 3
        # runtimes). No crítico: nunca debe romper el arranque del run.
        try:
            from harness.task_states import apply_task_start_state
            from services.tracker_provider import get_tracker_provider

            _ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
            if _ticket is not None and _ticket.ado_id is not None:
                _provider = get_tracker_provider(_ticket.stacky_project_name)
                apply_task_start_state(
                    project_name=_ticket.stacky_project_name,
                    agent_type=agent_type,
                    ado_id=_ticket.ado_id,
                    provider=_provider,
                )
        except Exception:
            logger.debug("apply_task_start_state falló (no crítico)", exc_info=True)

    log_streamer.open(execution_id)
    log_streamer.push(
        execution_id,
        "info",
        "preparando ejecucion codex cli",
        group="pre_run",
        event_type="pre_run",
    )
    ticket_status.on_execution_start(
        ticket_id=ticket_id,
        execution_id=execution_id,
        agent_type=agent_type,
        user=user,
    )

    stacky_logger.agent_event(
        "agent_started",
        execution_id=execution_id,
        ticket_id=ticket_id,
        user=user,
        input_data={
            "agent_type": agent_type,
            "context_blocks": len(context_blocks),
            "runtime": RUNTIME,
        },
        context_data={
            "vscode_agent_filename": vscode_agent_filename,
            "workspace_root": workspace_root,
            "model_override": model_override,
        },
        tags=["agent", RUNTIME],
    )

    thread = threading.Thread(
        target=_run_in_background,
        args=(execution_id,),
        kwargs={
            "ticket_message": ticket_message,
            "vscode_agent_filename": vscode_agent_filename,
            "workspace_root": workspace_root,
            "model_override": model_override,
        },
        daemon=True,
        name=f"codex-cli-{execution_id}",
    )
    thread.start()
    return execution_id


def cancel(execution_id: int) -> bool:
    """Terminate a Codex CLI process if Stacky owns one for this execution."""
    with _PROCESSES_LOCK:
        proc = _PROCESSES.get(execution_id)
    if proc is None:
        return False
    _push(execution_id, "warn", "codex cli cancel requested")
    try:
        proc.terminate()
        return True
    except Exception as exc:  # noqa: BLE001
        _push(execution_id, "error", f"codex cli cancel failed: {exc}")
        return False


def send_input(execution_id: int, text: str, *, user: str | None = None) -> dict[str, Any]:
    """Send operator text to a Codex CLI execution.

    Codex `exec -` consumes stdin for the initial prompt and usually closes that
    channel once the run starts. When the live process no longer accepts stdin,
    we continue the same Codex conversation via `codex exec resume <session>`.
    """
    message = (text or "").strip()
    if not message:
        raise ValueError("text is required")

    _push(
        execution_id,
        "info",
        f"operator input queued ({len(message)} chars)",
        group="operator",
    )

    with _PROCESSES_LOCK:
        proc = _PROCESSES.get(execution_id)
    if proc is not None and proc.poll() is None and proc.stdin is not None and not proc.stdin.closed:
        try:
            proc.stdin.write(message + "\n")
            proc.stdin.flush()
            _push(execution_id, "info", "operator input sent to codex stdin", group="operator")
            return {"ok": True, "mode": "stdin", "execution_id": execution_id}
        except (BrokenPipeError, OSError) as exc:
            _push(
                execution_id,
                "warn",
                f"codex stdin unavailable, falling back to resume: {exc}",
                group="operator",
            )

    session_id, cwd, model = _input_resume_context(execution_id)
    if not session_id:
        raise RuntimeError(
            "Codex session_id is not available yet; wait for Codex to start or check CLI JSON logs."
        )

    lock = _RESUME_LOCKS.setdefault(execution_id, threading.Lock())
    if lock.locked():
        raise RuntimeError("another Codex input is already being processed for this execution")

    thread = threading.Thread(
        target=_resume_with_input,
        args=(execution_id, session_id, message),
        kwargs={"cwd": cwd, "model_override": model, "user": user},
        daemon=True,
        name=f"codex-cli-input-{execution_id}",
    )
    thread.start()
    return {"ok": True, "mode": "resume", "execution_id": execution_id, "session_id": session_id}


def _run_in_background(
    execution_id: int,
    *,
    ticket_message: str,
    vscode_agent_filename: str,
    workspace_root: str | None,
    model_override: str | None,
) -> None:
    started = datetime.utcnow()

    def log(level: str, message: str, group: str | None = None, indent: int = 0) -> None:
        _push(execution_id, level, message, group=group, indent=indent)

    output_file: Path | None = None
    prompt_file: Path | None = None
    run_dir: Path | None = None
    stdout_tail: list[str] = []
    stderr_tail: list[str] = []  # Plan 68 AD-1 — tail dedicado para stderr (paridad con claude)
    return_code: int | None = None
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    agent_type: str | None = None
    ticket_id: int | None = None
    mask_map: dict[str, str] = {}
    _stream_telemetry_sink: dict = {}  # H2.2 — acumula eventos JSONL con uso

    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                raise RuntimeError(f"execution_id={execution_id} not found")
            ticket_id = row.ticket_id
            agent_type = row.agent_type
            raw_blocks = list(row.input_context or [])
            ticket = session.get(Ticket, ticket_id) if ticket_id else None
            t_ado_id = ticket.ado_id if ticket else None
            t_title = ticket.title if ticket else None
            t_desc = ticket.description if ticket else None
            t_wit = ticket.work_item_type if ticket else None
            project_ctx = resolve_project_context(ticket=ticket)

        if not _run_pre_run_checks(execution_id, workspace_root, ticket_id, agent_type):
            return
        _mark_status(execution_id, "running")
        log("info", "start codex cli runtime")

        selected_agent = vscode_agents.get_agent_by_filename(
            config.VSCODE_PROMPTS_DIR, vscode_agent_filename
        )
        all_agents = vscode_agents.list_agents(config.VSCODE_PROMPTS_DIR)
        if selected_agent is None:
            # Fail-fast con el contexto del canonical para diagnosticar deploys
            # que llegan sin Stacky/agents materializado.
            raise RuntimeError(
                f"agent prompt not found: {vscode_agent_filename} "
                f"(VSCODE_PROMPTS_DIR={config.VSCODE_PROMPTS_DIR}, "
                f"stacky_agents_dir={stacky_agents_svc.stacky_agents_dir()})"
            )

        selected_path = Path(config.VSCODE_PROMPTS_DIR) / vscode_agent_filename
        agent_entry = stacky_agents_svc.build_entry_from_path(selected_path)
        if agent_entry is None:
            raise RuntimeError(
                f"agent prompt not found on disk: {selected_path}"
            )

        cwd = _resolve_cwd(workspace_root)
        run_dir = Path(__file__).resolve().parents[1] / "data" / "codex_runs" / str(execution_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        output_file = run_dir / "last_message.md"
        agent_bundle_dir, agent_manifest_file = _materialize_agent_prompts(run_dir, all_agents)

        # Fase B — enriquecimiento de contexto (paridad con claude_code_cli /
        # github_copilot). Corre acá, en background, para no bloquear el lanzamiento.
        log("info", "enriqueciendo contexto del ticket…")
        enriched_blocks, _ado_stats = context_enrichment.enrich_blocks(
            ticket_id=ticket_id,
            agent_type=agent_type or "",
            raw_blocks=raw_blocks,
            project_ctx=project_ctx,
            log=log,
        )
        # Plan 133 F5 — garantía pre-spawn de stacky_required_blocks: si el
        # .agent.md declara bloques obligatorios y el enriquecimiento no los
        # produjo, el run falla ANTES de spawnear el CLI (cero tokens).
        try:
            from services import agent_contract

            agent_contract.enforce(
                vscode_agent_filename=vscode_agent_filename, blocks=enriched_blocks
            )
        except agent_contract.AgentContractError as _ac_exc:
            log("error", f"contrato de contexto incumplido: {_ac_exc}")
            _mark_terminal(
                execution_id,
                status="error",
                error=str(_ac_exc),
                metadata={
                    "context_contract_failure": {
                        "agent": vscode_agent_filename, "detail": str(_ac_exc),
                    }
                },
            )
            if ticket_id is not None:
                ticket_status.on_execution_end(
                    ticket_id=ticket_id,
                    execution_id=execution_id,
                    final_status="error",
                    agent_type=agent_type,
                    error=str(_ac_exc),
                )
            return
        rich_message = context_enrichment.build_ticket_context_text(
            ado_id=t_ado_id,
            title=t_title,
            description=t_desc,
            work_item_type=t_wit,
            blocks=enriched_blocks,
        )
        if not rich_message.strip():
            rich_message = ticket_message
        # Fase B — PII masking antes de mandar el prompt; se re-hidrata el output.
        masked_message, mask_map = pii_masker.mask_text(rich_message)
        if mask_map:
            log("info", f"PII masking: {len(mask_map)} ocurrencias enmascaradas")

        invocation_block = stacky_agents_svc.build_invocation_block(
            entry=agent_entry,
            workspace_root=cwd,
        )
        # H4.3 — Stacky Skills injection en codex (sin rama MCP: siempre body top-1).
        _codex_skills_block = ""
        _codex_project_name = project_ctx.stacky_project_name if project_ctx else None
        try:
            from services.cli_feature_flags import skills_enabled as _skills_on  # noqa: PLC0415
            from services import stacky_skills as _ss  # noqa: PLC0415
            if _skills_on(_codex_project_name):
                _matched = _ss.select_for_run(
                    agent_type=agent_type or "",
                    project=_codex_project_name,
                    context_text=rich_message,
                    max_skills=3,
                )
                if _matched:
                    _index = _ss.render_index(_matched)
                    _top = _matched[0]
                    _codex_skills_block = (
                        "## Stacky Skills disponibles\n\n"
                        + _index
                        + f"\n\n### Skill activa: {_top.name}\n\n"
                        + _ss.cap_body(_top.body)
                    )
                    log("info", f"H4: skills inyectadas ({len(_matched)})", group="operator")
        except Exception as _exc:  # noqa: BLE001
            log("warn", f"H4: no se pudo inyectar skills en codex: {_exc}")
        # Plan 54 F3 — inyección rejection_lessons en codex_cli (paridad FA-11).
        _mem_prefix_codex: str = ""
        _mem_meta_codex: dict = {}
        try:
            from services.memory_prefix import build_memory_prefix as _bmp_codex  # noqa: PLC0415
            _mem_prefix_codex, _mem_meta_codex = _bmp_codex(
                project=_codex_project_name,
                agent_type=agent_type or "",
            )
            if _mem_prefix_codex:
                log("info", "Plan 54: rejection_lessons inyectadas en prompt (Codex)", group="operator")
        except Exception as _exc_mp_codex:  # noqa: BLE001
            log("warn", f"Plan 54: memory_prefix falló en codex (no crítico): {_exc_mp_codex}")
        # Plan 80 — MCP externo: Codex no auto-inyecta. Ver plan 80b y guía install-codex.md.
        from services import cli_feature_flags as _cff_codex  # noqa: PLC0415
        if _cff_codex.codebase_memory_mcp_enabled(_codex_project_name):
            log("info", "Codex: MCP externo activado (flag ON) pero requiere config manual. Ver install-codex.md (Plan 76/80).")
        prompt = _build_codex_prompt(
            selected_agent=selected_agent,
            all_agents=all_agents,
            ticket_message=masked_message,
            agent_bundle_dir=agent_bundle_dir,
            agent_manifest_file=agent_manifest_file,
            invocation_block=invocation_block,
            skills_section=_codex_skills_block,
        )
        if _mem_prefix_codex:
            prompt = (_mem_prefix_codex.strip() + "\n\n" + prompt).strip()
        prompt_file = run_dir / "prompt.md"
        prompt_file.write_text(prompt, encoding="utf-8")

        # I0.2 — Cómputo de fingerprint_complexity en codex.
        # Solo se calcula si el flag está ON. OFF → None (routing byte-idéntico).
        _codex_complexity: str | None = None
        if config.STACKY_COMPLEXITY_ESTIMATION_ENABLED:
            try:
                from harness.complexity import estimate_complexity as _est_cx
                _cx_title = ""
                _cx_desc = ""
                try:
                    with session_scope() as _sess_cx:
                        _tobj_cx = _sess_cx.get(Ticket, ticket_id)
                        if _tobj_cx is not None:
                            _cx_title = _tobj_cx.title or ""
                            _cx_desc = _tobj_cx.description or ""
                except Exception:
                    pass
                _codex_complexity = _est_cx(
                    agent_type=agent_type or "",
                    ticket_title=_cx_title,
                    ticket_description=_cx_desc,
                    blocks=raw_blocks,
                )
                log("info", f"complexity estimation → {_codex_complexity} (I0.2)")
            except Exception as _exc_cx:  # noqa: BLE001
                log("warn", f"complexity estimation falló (no crítico): {_exc_cx}")

        # H2.4 — política de modelo para codex
        from harness.model_policy import resolve_model as _resolve_model
        _resolved_model, _model_reason = _resolve_model("codex_cli", model_override)

        # H3.3 — Egress check antes del spawn (STACKY_CLI_EGRESS_ENABLED, OFF default).
        egress_decision = _check_cli_egress(
            prompt=prompt,
            project=project_name if "project_name" in dir() else None,
            model=_resolved_model or "",
        )
        if egress_decision is not None and not egress_decision.allowed:
            reason = egress_decision.reason
            log("error", f"egress bloqueado antes de spawn codex: {reason}")
            with session_scope() as s:
                row = s.query(AgentExecution).filter(AgentExecution.id == execution_id).first()
                if row:
                    row.status = "error"
                    row.output = f"[egress] run bloqueado: {reason}"
            return

        # H7.1 — Re-run con exec resume + delta prompt (por proyecto, OFF default).
        # Paridad con claude F2.3. Usa harness.resume.resolve (dueño único).
        _codex_resume_ref: str | None = None
        try:
            from harness.resume import resolve as _resume_resolve
            _codex_resume_ref, _codex_delta = _resume_resolve(
                runtime=RUNTIME,
                ticket_id=ticket_id,
                agent_type=agent_type,
                project=_codex_project_name,
                current_blocks=enriched_blocks,
                execution_id=execution_id,
            )
            if _codex_delta:
                prompt = _codex_delta + "\n\n" + prompt
                prompt_file.write_text(prompt, encoding="utf-8")
                log("info", f"codex resume: delta prompt aplicado (H7.1)")
            if _codex_resume_ref:
                log("info", f"codex resume: sesión previa={_codex_resume_ref[:12]}… (H7.1)")
        except Exception as _resume_exc:  # noqa: BLE001
            log("warn", f"codex resume resolve falló (arranque en frío): {_resume_exc}")
            _codex_resume_ref = None

        if _codex_resume_ref:
            cmd = _build_resume_command(
                session_id=_codex_resume_ref,
                prompt=prompt,
                output_file=output_file,
                model_override=_resolved_model,
            )
        else:
            cmd = _build_command(
                cwd=cwd,
                output_file=output_file,
                model_override=_resolved_model,
            )
        log("info", f"codex cli cwd={cwd}")
        log("info", "codex cli command: " + _display_command(cmd))
        log(
            "info",
            f"loaded {len(all_agents)} Stacky agent prompt(s); selected {selected_agent.filename}",
        )

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
            # Fase 3c: el agente NO debe heredar credenciales ADO/GitHub.
            env=build_agent_env(extra={"STACKY_EXECUTION_ID": str(execution_id)}),
        )
        log("info", f"codex cli process started pid={proc.pid}")
        with _PROCESSES_LOCK:
            _PROCESSES[execution_id] = proc

        # Heartbeat — el reconciler/Fase 4 lo consume para detectar runs colgados.
        write_heartbeat(run_dir, execution_id=execution_id, pid=proc.pid, phase="started")
        append_event(
            run_dir,
            execution_id=execution_id,
            event_type="process_started",
            payload={"pid": proc.pid, "agent_type": agent_type},
        )
        hb_interval = float(os.getenv("STACKY_HEARTBEAT_INTERVAL_SECONDS", "30"))

        def _heartbeat_loop() -> None:
            while not heartbeat_stop.wait(timeout=hb_interval):
                try:
                    write_heartbeat(run_dir, execution_id=execution_id, pid=proc.pid, phase="running")
                except Exception:
                    logger.debug("heartbeat write failed", exc_info=True)

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            daemon=True,
            name=f"codex-cli-hb-{execution_id}",
        )
        heartbeat_thread.start()

        # Q0.2 — Esfuerzo adaptativo por dificultad estimada (solo codex, OFF default).
        # Codex no tiene --effort; se ajusta el presupuesto de turnos bajo el cap.
        _codex_adaptive_turns = config.STACKY_RUNAWAY_MAX_TURNS
        if getattr(config, "STACKY_ADAPTIVE_EFFORT_ENABLED", False) and _codex_complexity:
            _floor = (getattr(config, "STACKY_EFFORT_FLOOR", "medium") or "medium").strip().lower()
            _ORDER_EFFORT = {"low": 0, "medium": 1, "high": 2}
            _mapped_effort_codex = {"S": "low", "M": "medium", "L": "high", "XL": "high"}.get(
                _codex_complexity, "medium"
            )
            if _ORDER_EFFORT.get(_mapped_effort_codex, 1) < _ORDER_EFFORT.get(_floor, 1):
                _mapped_effort_codex = _floor
            # S/low → 50% del cap; M/medium → 100%; L/XL/high → 100%
            if _codex_adaptive_turns > 0 and _mapped_effort_codex == "low":
                _codex_adaptive_turns = max(1, _codex_adaptive_turns // 2)
            log(
                "info",
                f"adaptive effort (codex) → {_mapped_effort_codex} "
                f"(complexity={_codex_complexity}, max_turns={_codex_adaptive_turns}, Q0.2)",
            )

        # H5 — Runaway guard: solo turnos (costo no disponible en codex stream hasta H2.2).
        from harness.runaway_guard import RunLimits, RunawayGuard as _RunawayGuard
        _codex_runaway_guard = _RunawayGuard(
            RunLimits(
                max_turns=_codex_adaptive_turns,
                max_cost_usd=0.0,  # codex no reporta costo en stream
            )
        )
        _codex_runaway_triggered: list[str] = []

        def _codex_on_runaway(event_count: int, _line: str) -> None:
            if _codex_runaway_triggered:
                return
            reason = _codex_runaway_guard.observe(num_turns=event_count)
            if reason:
                _codex_runaway_triggered.append(reason)
                log("warn", f"codex runaway detectado — {reason} — terminando proceso")
                try:
                    proc.terminate()
                except Exception:
                    pass

        readers = [
            threading.Thread(
                target=_read_stream,
                args=(execution_id, proc.stdout, "info", "codex", stdout_tail),
                kwargs={"telemetry_sink": _stream_telemetry_sink,
                        "on_runaway": _codex_on_runaway},
                daemon=True,
            ),
            threading.Thread(
                target=_read_stream,
                args=(execution_id, proc.stderr, "warn", "codex-stderr", stderr_tail),  # Plan 68 AD-1 — tail dedicado (era stdout_tail)
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()

        _write_prompt_to_stdin(execution_id, proc, prompt)

        # R1.1 — espera acotada con terminate→kill espejando la secuencia de claude.
        # Con STACKY_STALL_WATCHDOG_SECONDS=0 (default) el bucle es equivalente
        # al proc.wait() original (byte-identico al comportamiento previo).
        import time as _time
        _codex_stall_watchdog_sec = config.STACKY_STALL_WATCHDOG_SECONDS
        _codex_last_event_mono: list[float] = [_time.monotonic()]
        _codex_stall_fired: list[bool] = [False]

        # Compartir ultimo evento con los readers via lista mutable.
        _codex_event_notifier: list[float] = _codex_last_event_mono

        # Parchar el telemetry_sink para actualizar _codex_last_event_mono.
        _orig_codex_on_runaway = _codex_on_runaway

        def _codex_on_runaway_with_stall(event_count: int, line: str) -> None:
            _codex_last_event_mono[0] = _time.monotonic()
            _orig_codex_on_runaway(event_count, line)

        # NOTE: los readers ya arrancaron; _codex_on_runaway_with_stall no se puede
        # pasar retroactivamente. Rastreamos inactividad en el bucle de espera
        # con el timestamp del ultimo reader alive.
        while True:
            try:
                return_code = proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                if _codex_stall_watchdog_sec > 0 and not _codex_stall_fired[0]:
                    elapsed_no_event = _time.monotonic() - _codex_last_event_mono[0]
                    if elapsed_no_event >= _codex_stall_watchdog_sec:
                        log("warn",
                            f"R1.1 stall watchdog codex: {elapsed_no_event:.0f}s sin actividad — terminando")
                        if config.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED:
                            try:
                                log_streamer.flush(execution_id)
                            except Exception:  # noqa: BLE001
                                pass
                        proc.terminate()
                        try:
                            return_code = proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            return_code = proc.wait()
                        _codex_stall_fired[0] = True
                        break
                continue

        heartbeat_stop.set()
        for reader in readers:
            reader.join(timeout=5)
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=2)

        with _PROCESSES_LOCK:
            _PROCESSES.pop(execution_id, None)

        duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
        output = _read_output(output_file, stdout_tail)
        # Re-hidratar PII enmascarada antes de persistir / mostrar.
        if output and mask_map:
            output = pii_masker.unmask(output, mask_map)
        invocation_meta = stacky_agents_svc.invocation_metadata(
            entry=agent_entry,
            workspace_root=cwd,
        )
        metadata = {
            "runtime": RUNTIME,
            "vscode_agent_filename": vscode_agent_filename,
            "workspace_root": str(cwd),
            "codex_cli_bin": cmd[0],
            "codex_model": _resolved_model or config.CODEX_CLI_MODEL or None,
            "model_decision": {"model": _resolved_model, "reason": _model_reason},
            "exit_code": return_code,
            "duration_ms": duration_ms,
            "output_file": str(output_file),
            "prompt_file": str(prompt_file),
            "agent_bundle_dir": str(agent_bundle_dir),
            "agent_manifest_file": str(agent_manifest_file),
            "agent_count": len(all_agents),
            **invocation_meta,
        }
        # Plan 54 F3 — telemetría rejection_lessons codex.
        if _mem_meta_codex:
            metadata.update(_mem_meta_codex)
        # V1.1 — sello del prompt usado (trazabilidad/versionado).
        try:
            from services import agent_prompt_registry as _apr

            _body = selected_path.read_text(encoding="utf-8")
            _sha = _apr.ensure_version(vscode_agent_filename, _body)
            if _sha:
                metadata["prompt_sha"] = _sha
                # V2.4 — sello del run_fingerprint (dedup de runs idénticos).
                from services import run_cache as _rc
                _rc.seal_into_metadata(
                    metadata,
                    prompt_sha=_sha,
                    # model_override (no el resuelto): coincide con el fingerprint
                    # del lookup en el launch. Ver claude_code_cli_runner.
                    model=model_override,
                    context_blocks=raw_blocks,
                )
        except Exception:  # noqa: BLE001
            logger.debug("V1.1 prompt_sha sealing falló (no crítico)", exc_info=True)

        # R1.1 — si el stall watchdog disparó, marcar failed/stalled y salir.
        if _codex_stall_fired[0]:
            stall_meta = {
                "detected_at": datetime.utcnow().isoformat(),
                "last_event_at": datetime.utcfromtimestamp(
                    started.timestamp() + (_codex_last_event_mono[0] - _time.monotonic())
                ).isoformat() if False else datetime.utcnow().isoformat(),
            }
            metadata["stall"] = stall_meta
            _mark_terminal(
                execution_id,
                status="failed",
                error="stalled: sin actividad en stream",
                metadata=metadata,
            )
            log("error", "codex run terminado por watchdog de inactividad (stall)")
            ticket_status.on_execution_end(
                ticket_id=ticket_id, execution_id=execution_id,
                final_status="error", agent_type=agent_type, error="stalled",
            )
            _notify_outcome(
                execution_id=execution_id, ticket_id=ticket_id,
                agent_type=agent_type, status="error",
            )
            return

        # H5 — Runaway: si el guard disparó, marcar needs_review y salir.
        if _codex_runaway_triggered:
            metadata["runaway"] = {
                "reason": _codex_runaway_triggered[0],
                "turns": _stream_telemetry_sink.get("num_turns") if _stream_telemetry_sink else None,
                "cost": None,  # codex no reporta costo en stream
            }
            log("warn", f"codex runaway — degradando a needs_review: {_codex_runaway_triggered[0]}")
            _mark_terminal(
                execution_id,
                status="needs_review",
                output=output,
                metadata=metadata,
            )
            _safe_write_manifest(
                run_dir, run_id=execution_id, agent_type=agent_type,
                status="needs_review", exit_code=return_code,
                output_file=output_file, prompt_file=prompt_file,
            )
            append_event(run_dir, execution_id=execution_id,
                         event_type="needs_review",
                         payload={"exit_code": return_code, "duration_ms": duration_ms,
                                  "runaway": _codex_runaway_triggered[0]})
            ticket_status.on_execution_end(
                ticket_id=ticket_id, execution_id=execution_id,
                final_status="needs_review", agent_type=agent_type,
            )
            _notify_outcome(
                execution_id=execution_id,
                ticket_id=ticket_id,
                agent_type=agent_type,
                status="needs_review",
            )
            return

        if return_code == 0:
            # H2.2 — persistir telemetría codex (si hay datos capturados)
            if _stream_telemetry_sink:
                try:
                    from harness.telemetry import from_codex_event, persist as _persist_telemetry
                    _t = from_codex_event(_stream_telemetry_sink)
                    _persist_telemetry(execution_id, _t)
                    log("debug", f"harness_telemetry codex persistida: session_id={_t.session_id}")
                except Exception as exc:  # noqa: BLE001
                    log("warn", f"harness_telemetry codex: persist falló (no crítico): {exc}")

            # H2.3 — autocorrección via exec resume (antes de finalize_run)
            _codex_session_id: str | None = None
            try:
                with session_scope() as _sess:
                    _row = _sess.get(AgentExecution, execution_id)
                    if _row is not None:
                        _codex_session_id = _row.metadata_dict.get("codex_session_id")
            except Exception:
                pass

            if config.CODEX_CLI_AUTOCORRECT_ENABLED and t_ado_id is not None:
                try:
                    from services.codex_autocorrect import run_autocorrect_loop
                    from services import artifact_validator as _av

                    def _do_resume(sess_id: str, prompt: str) -> bool:
                        try:
                            resume_cmd = _build_resume_command(
                                session_id=sess_id,
                                prompt=prompt,
                                output_file=output_file,
                                model_override=_resolved_model,
                            )
                            import subprocess as _sp
                            _result = _sp.run(
                                resume_cmd,
                                capture_output=True,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=300,
                            )
                            return _result.returncode == 0
                        except Exception as _exc:
                            log("warn", f"codex resume subprocess falló: {_exc}")
                            return False

                    autocorrect_result = run_autocorrect_loop(
                        session_id=_codex_session_id,
                        ado_id=t_ado_id,
                        max_retries=config.CODEX_CLI_AUTOCORRECT_MAX_RETRIES,
                        gate_enabled=config.CODEX_CLI_CONTRACT_GATE_ENABLED,
                        resume_fn=_do_resume,
                        validate_fn=lambda aid, check_db=False: _av.validate_run_artifacts(aid, check_db=check_db),
                        log=log,
                    )
                    metadata["autocorrect_codex"] = {
                        "retries": autocorrect_result.retries_used,
                        "final_ok": autocorrect_result.final_artifacts_ok,
                    }
                    if autocorrect_result.status_suggestion == "needs_review":
                        # Override: gate + artifacts inválidos tras retries
                        _mark_terminal(
                            execution_id,
                            status="needs_review",
                            output=output,
                            metadata=metadata,
                        )
                        _safe_write_manifest(
                            run_dir, run_id=execution_id, agent_type=agent_type,
                            status="needs_review", exit_code=return_code,
                            output_file=output_file, prompt_file=prompt_file,
                        )
                        append_event(run_dir, execution_id=execution_id,
                                     event_type="needs_review",
                                     payload={"exit_code": return_code, "duration_ms": duration_ms})
                        log("warn", f"codex cli needs_review ({duration_ms}ms) — autocorrect agotado")
                        ticket_status.on_execution_end(
                            ticket_id=ticket_id, execution_id=execution_id,
                            final_status="needs_review", agent_type=agent_type,
                        )
                        _notify_outcome(
                            execution_id=execution_id,
                            ticket_id=ticket_id,
                            agent_type=agent_type,
                            status="needs_review",
                        )
                        stacky_logger.agent_event(
                            "agent_completed", execution_id=execution_id,
                            ticket_id=ticket_id, level="WARN", duration_ms=duration_ms,
                            output_data={"runtime": RUNTIME, "status": "needs_review",
                                         "exit_code": return_code},
                            tags=["agent", RUNTIME],
                        )
                        return
                except Exception as exc:  # noqa: BLE001
                    log("warn", f"codex autocorrect falló (no crítico): {exc}")

            # I1.1 — Auto-reparación ante output vacío/malformado (STACKY_RUN_REPAIR_ENABLED).
            # Corre DESPUÉS del autocorrect y ANTES del post-run. Comparte el techo de
            # retries del autocorrect. OFF → comportamiento actual exacto.
            if config.STACKY_RUN_REPAIR_ENABLED and t_ado_id is not None:
                try:
                    from harness.run_repair import attempt_repair as _attempt_repair

                    _repair_autocorrect_retries = (
                        metadata.get("autocorrect_codex", {}).get("retries", 0)
                        if isinstance(metadata.get("autocorrect_codex"), dict)
                        else 0
                    )

                    def _codex_repair_send(msg: str) -> str:
                        """Envía mensaje de repair via exec resume y devuelve nueva salida."""
                        try:
                            if not _codex_session_id:
                                return ""
                            import subprocess as _sp
                            _rcmd = _build_resume_command(
                                session_id=_codex_session_id,
                                prompt=msg,
                                output_file=output_file,
                                model_override=_resolved_model,
                            )
                            _r = _sp.run(
                                _rcmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=300,
                            )
                            if _r.returncode == 0 and output_file.exists():
                                return output_file.read_text(encoding="utf-8", errors="replace")
                            return ""
                        except Exception as _e:
                            log("warn", f"run_repair codex send falló: {_e}")
                            return ""

                    _repair_result = _attempt_repair(
                        output_text=output or "",
                        artifacts=[str(output_file)] if output_file.exists() else [],
                        runtime=RUNTIME,
                        retries_budget=config.CODEX_CLI_AUTOCORRECT_MAX_RETRIES,
                        retries_used=_repair_autocorrect_retries,
                        send_fn=_codex_repair_send,
                        enabled=True,
                    )
                    if _repair_result is not None:
                        metadata["run_repair"] = _repair_result
                        if _repair_result.get("recovered"):
                            log("info", "run_repair: output recuperado tras reintento (codex)")
                            # Re-leer output reparado
                            if output_file.exists():
                                output = output_file.read_text(encoding="utf-8", errors="replace")
                        else:
                            log("warn", "run_repair: reintento no recuperó el output (codex)")
                except Exception as exc:  # noqa: BLE001
                    log("warn", f"run_repair codex falló (no crítico): {exc}")

            # H2.1 — post-run pipeline (contract validator + confidence)
            try:
                from harness.post_run import finalize_run as _finalize_run
                _pr = _finalize_run(
                    runtime=RUNTIME,
                    agent_type=agent_type or "",
                    output_text=output or "",
                    ado_id=t_ado_id,
                    gate_enabled=config.CODEX_CLI_CONTRACT_GATE_ENABLED,
                    log=log,
                )
                metadata.update(_pr.metadata_patch)
                final_status = _pr.status_suggestion
            except Exception as exc:  # noqa: BLE001
                log("warn", f"harness post_run falló (no crítico): {exc}")
                final_status = "completed"

            # Plan 38 C1 — Trazabilidad: agent_type, agent_name, produced_files
            if config.STACKY_EXECUTION_TRACE_ENABLED:
                try:
                    from agent_runner import _build_trace_metadata, _collect_produced_files
                    _trace = _build_trace_metadata(
                        prompt_blocks=raw_blocks or [],
                        agent_type=agent_type or "",
                        agent_name=getattr(selected_agent, "name", ""),
                        prompt_text_enabled=config.STACKY_TRACE_PROMPT_TEXT_ENABLED,
                    )
                    for k, v in _trace.items():
                        metadata.setdefault(k, v)
                    metadata.setdefault("produced_files", _collect_produced_files(None))
                except Exception:
                    pass
            # Plan 77 F3 (Codex CLI) — Postea análisis de fase del Issue (si aplica). No-fatal.
            try:
                from api.tickets import publish_issue_phase_from_run as _pub_issue_phase  # noqa: PLC0415
                _ipm = _pub_issue_phase(
                    ticket_id=ticket_id,
                    agent_type=agent_type,
                    output=output or "",
                    project_name=_codex_project_name,
                )
                if _ipm is not None:
                    metadata["issue_phase"] = _ipm
            except Exception:  # noqa: BLE001
                pass
            _mark_terminal(
                execution_id,
                status=final_status,
                output=output,
                metadata=metadata,
            )
            final_status = _read_status(execution_id, fallback=final_status)
            _safe_write_manifest(
                run_dir,
                run_id=execution_id,
                agent_type=agent_type,
                status=final_status,
                exit_code=return_code,
                output_file=output_file,
                prompt_file=prompt_file,
            )
            append_event(
                run_dir,
                execution_id=execution_id,
                event_type=final_status,
                payload={"exit_code": return_code, "duration_ms": duration_ms},
            )
            # H7.2 — repro.ps1: comando exacto + env STACKY_* no sensibles.
            try:
                write_repro_script(
                    run_dir=run_dir,
                    cmd=cmd,
                    env=build_agent_env(extra={"STACKY_EXECUTION_ID": str(execution_id)}),
                )
            except Exception as _repro_exc:  # noqa: BLE001
                log("warn", f"write_repro_script falló (no crítico): {_repro_exc}")
            log("info", f"codex cli {final_status} ({duration_ms}ms)")
            # Hook A (Fase B): captura DRAFT post-run, paridad con github_copilot.
            if final_status == "completed":
                try:
                    from services import post_run_memory

                    memory_id = post_run_memory.capture_on_completion(execution_id)
                    if memory_id:
                        log("info", f"stacky-memory draft capturado: {memory_id}")
                except Exception as exc:  # noqa: BLE001
                    log("warn", f"post_run_memory completion hook falló: {exc}")
            ticket_status.on_execution_end(
                ticket_id=ticket_id,
                execution_id=execution_id,
                final_status=final_status,
                agent_type=agent_type,
            )
            _notify_outcome(
                execution_id=execution_id,
                ticket_id=ticket_id,
                agent_type=agent_type,
                status=final_status,
            )
            stacky_logger.agent_event(
                "agent_completed",
                execution_id=execution_id,
                ticket_id=ticket_id,
                level="INFO",
                duration_ms=duration_ms,
                output_data={
                    "runtime": RUNTIME,
                    "output_chars": len(output or ""),
                    "exit_code": return_code,
                },
                tags=["agent", RUNTIME],
            )
        else:
            error = f"codex cli exited with code {return_code}"
            _mark_terminal(
                execution_id,
                status="error",
                output=output,
                error=error,
                metadata=metadata,
            )
            _safe_write_manifest(
                run_dir,
                run_id=execution_id,
                agent_type=agent_type,
                status="error",
                exit_code=return_code,
                error_message=error,
                output_file=output_file,
                prompt_file=prompt_file,
            )
            append_event(
                run_dir,
                execution_id=execution_id,
                event_type="error",
                payload={"exit_code": return_code, "duration_ms": duration_ms, "error": error},
            )
            log("error", error)
            ticket_status.on_execution_end(
                ticket_id=ticket_id,
                execution_id=execution_id,
                final_status="error",
                agent_type=agent_type,
                error=error,
            )
            _notify_outcome(
                execution_id=execution_id,
                ticket_id=ticket_id,
                agent_type=agent_type,
                status="error",
            )
            stacky_logger.agent_event(
                "agent_failed",
                execution_id=execution_id,
                ticket_id=ticket_id,
                level="ERROR",
                output_data={"runtime": RUNTIME, "error": error, "exit_code": return_code},
                tags=["agent", RUNTIME],
            )

    except Exception as exc:  # noqa: BLE001
        heartbeat_stop.set()
        with _PROCESSES_LOCK:
            _PROCESSES.pop(execution_id, None)
        logger.exception("[exec=%s] codex cli runtime failed", execution_id)
        log("error", f"codex cli runtime failed: {exc}")
        _mark_terminal(execution_id, status="error", error=str(exc))
        if run_dir is not None:
            _safe_write_manifest(
                run_dir,
                run_id=execution_id,
                agent_type=agent_type,
                status="error",
                exit_code=return_code,
                error_message=str(exc),
                output_file=output_file,
                prompt_file=prompt_file,
            )
            try:
                append_event(
                    run_dir,
                    execution_id=execution_id,
                    event_type="exception",
                    payload={"error": str(exc)},
                )
            except Exception:
                pass
        try:
            with session_scope() as session:
                row = session.get(AgentExecution, execution_id)
                ticket_id = row.ticket_id if row else None
                agent_type = row.agent_type if row else None
            if ticket_id is not None:
                ticket_status.on_execution_end(
                    ticket_id=ticket_id,
                    execution_id=execution_id,
                    final_status="error",
                    agent_type=agent_type,
                    error=str(exc),
                )
                _notify_outcome(
                    execution_id=execution_id,
                    ticket_id=ticket_id,
                    agent_type=agent_type,
                    status="error",
                )
        except Exception:
            logger.exception("could not mark ticket status after codex cli failure")
    finally:
        # V0.3 — liberar el slot de concurrencia adquirido en el launch.
        try:
            from services import run_slots
            run_slots.release()
        except Exception:  # noqa: BLE001
            logger.debug("[exec=%s] run_slots.release falló", execution_id, exc_info=True)
        log_streamer.close(execution_id)


def _safe_write_manifest(
    run_dir: Path,
    *,
    run_id: int,
    agent_type: str | None,
    status: str,
    exit_code: int | None = None,
    error_message: str | None = None,
    output_file: Path | None = None,
    prompt_file: Path | None = None,
) -> None:
    """Wrapper sobre write_manifest que nunca falla el lifecycle del runner."""
    try:
        artifacts: list[dict] = []
        if output_file is not None and output_file.exists():
            artifacts.append({"path": str(output_file), "kind": "output_md"})
        if prompt_file is not None and prompt_file.exists():
            artifacts.append({"path": str(prompt_file), "kind": "other"})
        signals = {"work_completed": status == "completed"}
        write_manifest(
            run_dir,
            run_id=run_id,
            agent_type=agent_type,
            status=status,
            exit_code=exit_code,
            error_message=error_message,
            artifacts=artifacts,
            signals=signals,
        )
    except Exception:
        logger.exception("[exec=%s] manifest write failed (no crítico)", run_id)


# ── H3.3 — Egress check para CLI ─────────────────────────────────────────────

def _check_cli_egress(
    *,
    prompt: str,
    project: str | None,
    model: str,
):
    """Verifica egress policies sobre el prompt final ANTES del spawn.

    Devuelve `EgressDecision` si STACKY_CLI_EGRESS_ENABLED=true, o None si está
    deshabilitado (default). Si bloquea, el llamador debe abortar el spawn.

    Nunca lanza: cualquier error interno → None (best-effort, no bloquea el run).
    """
    if os.environ.get("STACKY_CLI_EGRESS_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return None
    try:
        from services import egress_policies  # noqa: PLC0415
        return egress_policies.check(project=project, model=model, context_text=prompt)
    except Exception:  # noqa: BLE001
        logger.debug("_check_cli_egress: error inesperado, saltando check", exc_info=True)
        return None


def _build_command(
    *,
    cwd: Path,
    output_file: Path,
    model_override: str | None,
) -> list[str]:
    codex_bin = _resolve_codex_cli_bin()
    cmd = [
        codex_bin,
        "exec",
        "--json",
        "--color",
        "never",
        "--skip-git-repo-check",
        "--output-last-message",
        str(output_file),
        "-C",
        str(cwd),
        "-s",
        config.CODEX_CLI_SANDBOX,
    ]
    if (config.CODEX_CLI_APPROVAL or "").strip().lower() in {
        "bypass",
        "dangerously-bypass",
        "dangerously-bypass-approvals-and-sandbox",
    }:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    model = model_override or config.CODEX_CLI_MODEL
    if model:
        cmd.extend(["-m", model])
    cmd.append("-")
    return cmd


def _build_resume_command(
    *,
    session_id: str,
    prompt: str,
    output_file: Path,
    model_override: str | None,
) -> list[str]:
    codex_bin = _resolve_codex_cli_bin()
    cmd = [
        codex_bin,
        "exec",
        "resume",
        "--json",
        "--skip-git-repo-check",
        "--output-last-message",
        str(output_file),
    ]
    if (config.CODEX_CLI_APPROVAL or "").strip().lower() in {
        "bypass",
        "dangerously-bypass",
        "dangerously-bypass-approvals-and-sandbox",
    }:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    model = model_override or config.CODEX_CLI_MODEL
    if model:
        cmd.extend(["-m", model])
    cmd.extend([session_id, prompt])
    return cmd


def _resolve_codex_cli_bin() -> str:
    configured = (config.CODEX_CLI_BIN or "codex").strip()
    configured = configured.strip('"')

    found = shutil.which(configured)
    if found:
        return found

    candidates: list[Path] = []
    if configured and configured.lower() not in {"codex", "codex.exe"}:
        configured_path = Path(configured)
        candidates.append(configured_path)
        if os.name == "nt" and configured_path.suffix == "":
            candidates.append(configured_path.with_suffix(".exe"))

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "OpenAI" / "Codex" / "bin" / "codex.exe")
        candidates.append(Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe")

        app_data = os.environ.get("APPDATA")
        if app_data:
            candidates.append(Path(app_data) / "npm" / "codex.cmd")
            candidates.append(Path(app_data) / "npm" / "codex.exe")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(
        "No encontré Codex CLI. Instalalo o configurá CODEX_CLI_BIN con la ruta "
        "a codex.exe. En Windows suele estar en "
        "%LOCALAPPDATA%\\OpenAI\\Codex\\bin\\codex.exe."
    )


def _display_command(cmd: list[str]) -> str:
    safe: list[str] = []
    skip_next = False
    for part in cmd:
        if skip_next:
            safe.append("<file>")
            skip_next = False
            continue
        if part == "--output-last-message":
            safe.append(part)
            skip_next = True
        elif any(ch.isspace() for ch in part):
            safe.append(f'"{part}"')
        else:
            safe.append(part)
    return " ".join(safe)


def _resolve_cwd(workspace_root: str | None) -> Path:
    if workspace_root:
        candidate = Path(workspace_root)
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[2]


def _build_codex_prompt(
    *,
    selected_agent: vscode_agents.VsCodeAgent,
    all_agents: list[vscode_agents.VsCodeAgent],
    ticket_message: str,
    agent_bundle_dir: Path,
    agent_manifest_file: Path,
    invocation_block: str = "",
    mcp_enabled: bool = False,
    skills_section: str = "",
) -> str:
    """H3.1: las reglas se obtienen de harness.run_contract.rules_text en call-time.
    H4.3: skills_section se inyecta ANTES de las reglas si está presente.
    """
    from harness.run_contract import rules_text  # noqa: PLC0415
    rules = rules_text(runtime="codex", mcp_enabled=mcp_enabled)

    inventory = _format_agent_inventory(all_agents, agent_bundle_dir)
    skills_block = f"\n{skills_section.strip()}\n\n" if skills_section.strip() else ""

    return f"""# Stacky Agents Codex CLI runtime

{invocation_block}
Tu `.agent.md` (persona/rol) no está en este mensaje: leé el archivo desde la
'Ruta agent.md' indicada arriba antes de empezar y usalo como fuente de rol,
criterio, tono, restricciones y forma de trabajo.

## Catalogo de agentes Stacky disponibles

Stacky copio todos los `.agent.md` conocidos a esta ejecucion para que Codex
CLI pueda consultar cualquier agente GitHub Copilot Pro aunque el operador haya
elegido solo uno.

- Carpeta local: {agent_bundle_dir}
- Manifest JSON: {agent_manifest_file}

{inventory}

## Ticket y contexto

{ticket_message}
{skills_block}
{rules}
"""


def _materialize_agent_prompts(
    run_dir: Path,
    agents: list[vscode_agents.VsCodeAgent],
) -> tuple[Path, Path]:
    bundle_dir = run_dir / "stacky_agents"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []

    for agent in agents:
        filename = Path(agent.filename).name
        target = bundle_dir / filename
        target.write_text(agent.system_prompt or "", encoding="utf-8")
        manifest.append(
            {
                "name": agent.name,
                "filename": filename,
                "description": agent.description or "",
                "path": str(target),
            }
        )

    manifest_file = bundle_dir / "manifest.json"
    manifest_file.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return bundle_dir, manifest_file


def _format_agent_inventory(
    agents: list[vscode_agents.VsCodeAgent],
    agent_bundle_dir: Path,
) -> str:
    if not agents:
        return "- No se encontraron agentes en Stacky/agents."
    lines: list[str] = []
    for agent in agents:
        desc = (agent.description or "").replace("\n", " ").strip()
        if len(desc) > 220:
            desc = desc[:217] + "..."
        path = agent_bundle_dir / Path(agent.filename).name
        lines.append(f"- {agent.name} (`{agent.filename}`) - {desc or 'sin descripcion'} - {path}")
    return "\n".join(lines)


def _read_stream(
    execution_id: int,
    stream: Any,
    default_level: str,
    group: str,
    tail: list[str],
    telemetry_sink: dict | None = None,
    on_runaway: "Callable[[str], None] | None" = None,
) -> None:
    """Lee el stream de codex y procesa línea a línea.

    H2.2: si telemetry_sink es provisto (dict mutable), acumula el último
    evento JSONL que contenga session_id o campos de uso. El caller persiste
    harness_telemetry tras el wait().
    H5: on_runaway(razón) se llama la primera vez que el guard dispara.
    """
    from typing import Callable  # noqa: PLC0415 — import local para no afectar startup
    _event_count = 0
    _last_telemetry_emit = 0.0
    if stream is None:
        return
    for raw in stream:
        line = raw.rstrip("\r\n")
        if not line:
            continue
        _event_count += 1
        message, level = _summarize_codex_line(line, default_level)
        session_id = _extract_codex_session_id(line)
        if session_id:
            _remember_codex_session(execution_id, session_id)
        # H2.2 — acumula telemetría si el evento tiene campos de interés
        if telemetry_sink is not None:
            try:
                event = json.loads(line)
                if isinstance(event, dict) and (
                    event.get("session_id") or event.get("conversation_id")
                    or event.get("usage") or event.get("num_turns") or event.get("total_cost_usd")
                ):
                    telemetry_sink.update(event)
                    if config.STACKY_LIVE_TELEMETRY_ENABLED:
                        now = time.monotonic()
                        if now - _last_telemetry_emit >= 2.0:
                            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
                            payload = {
                                "turns": event.get("num_turns"),
                                "input_tokens": usage.get("input_tokens") if isinstance(usage, dict) else None,
                                "output_tokens": usage.get("output_tokens") if isinstance(usage, dict) else None,
                                "cost_usd": event.get("total_cost_usd"),
                                "cost_estimated": bool(event.get("total_cost_usd") is None),
                            }
                            if any(v is not None for v in payload.values()):
                                log_streamer.push(
                                    execution_id,
                                    "info",
                                    "telemetry",
                                    group="telemetry",
                                    event_type="telemetry",
                                    data=payload,
                                )
                                _last_telemetry_emit = now
            except (json.JSONDecodeError, Exception):
                pass
        # H5 — Runaway: on_runaway se llama una sola vez si el guard dispara.
        if on_runaway is not None:
            try:
                on_runaway(_event_count, line)
            except Exception:  # noqa: BLE001
                pass
        _push(execution_id, level, message, group=group)
        tail.append(message)
        if len(tail) > 200:
            del tail[:50]


def _write_prompt_to_stdin(
    execution_id: int,
    proc: subprocess.Popen[str],
    prompt: str,
) -> None:
    if proc.stdin is None:
        _push(execution_id, "warn", "codex cli stdin unavailable; waiting for process output")
        return

    try:
        chunk_size = 16_384
        total = len(prompt)
        _push(execution_id, "info", f"writing prompt to codex stdin ({total} chars)")
        for index in range(0, total, chunk_size):
            proc.stdin.write(prompt[index:index + chunk_size])
            proc.stdin.flush()
        proc.stdin.close()
        _push(execution_id, "info", "prompt sent to codex stdin")
    except (BrokenPipeError, OSError) as exc:
        _push(
            execution_id,
            "warn",
            f"codex cli closed stdin before full prompt write: {exc}; waiting for exit details",
        )
        try:
            proc.stdin.close()
        except Exception:
            pass


def _summarize_codex_line(line: str, default_level: str) -> tuple[str, str]:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return (line[:4000], default_level)

    if not isinstance(data, dict):
        return (str(data)[:4000], default_level)

    event_type = str(data.get("type") or data.get("event") or "event")
    level = str(data.get("level") or default_level).lower()
    if level not in {"debug", "info", "warn", "error"}:
        level = default_level

    for key in ("message", "msg", "text", "summary"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return (f"{event_type}: {value.strip()}"[:4000], level)

    item = data.get("item")
    if isinstance(item, dict):
        item_type = item.get("type") or item.get("kind") or "item"
        for key in ("text", "message", "command", "name", "status"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return (f"{event_type}/{item_type}: {value.strip()}"[:4000], level)
        return (f"{event_type}/{item_type}"[:4000], level)

    return (f"{event_type}: {json.dumps(data, ensure_ascii=False)[:3500]}", level)


def _extract_codex_session_id(line: str) -> str | None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    candidates: list[Any] = [
        data.get("session_id"),
        data.get("conversation_id"),
        data.get("thread_id"),
    ]
    item = data.get("item")
    if isinstance(item, dict):
        candidates.extend(
            [
                item.get("session_id"),
                item.get("conversation_id"),
                item.get("thread_id"),
            ]
        )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _remember_codex_session(execution_id: int, session_id: str) -> None:
    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return
            md = row.metadata_dict
            if md.get("codex_session_id") == session_id:
                return
            md["codex_session_id"] = session_id
            row.metadata_dict = md
        _push(execution_id, "debug", f"codex session_id captured: {session_id}", group="codex")
    except Exception:
        logger.exception("[exec=%s] could not persist codex session id", execution_id)


def _input_resume_context(execution_id: int) -> tuple[str | None, Path, str | None]:
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            raise RuntimeError(f"execution_id={execution_id} not found")
        md = row.metadata_dict
        session_id = md.get("codex_session_id")
        workspace_root = md.get("workspace_root")
        model = md.get("codex_model") or md.get("model_override")
    return (
        session_id if isinstance(session_id, str) else None,
        _resolve_cwd(workspace_root if isinstance(workspace_root, str) else None),
        model if isinstance(model, str) else None,
    )


def _resume_with_input(
    execution_id: int,
    session_id: str,
    prompt: str,
    *,
    cwd: Path,
    model_override: str | None,
    user: str | None,
) -> None:
    lock = _RESUME_LOCKS.setdefault(execution_id, threading.Lock())
    with lock:
        started = datetime.utcnow()
        run_dir = Path(__file__).resolve().parents[1] / "data" / "codex_runs" / str(execution_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        suffix = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        output_file = run_dir / f"input_{suffix}_last_message.md"
        stdout_tail: list[str] = []
        stderr_tail: list[str] = []  # Plan 68 AD-1 — tail dedicado para stderr (paridad con claude)
        return_code: int | None = None

        try:
            _mark_status(execution_id, "running")
            cmd = _build_resume_command(
                session_id=session_id,
                prompt=prompt,
                output_file=output_file,
                model_override=model_override,
            )
            redacted_cmd = [*cmd[:-1], "<operator-input>"]
            _push(
                execution_id,
                "info",
                "codex resume command: " + _display_command(redacted_cmd),
                group="operator",
            )

            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
                # Fase 3c: el resume tampoco debe heredar credenciales ADO.
                env=build_agent_env(extra={"STACKY_EXECUTION_ID": str(execution_id)}),
            )
            _push(execution_id, "info", f"codex resume started pid={proc.pid}", group="operator")

            readers = [
                threading.Thread(
                    target=_read_stream,
                    args=(execution_id, proc.stdout, "info", "codex", stdout_tail),
                    daemon=True,
                ),
                threading.Thread(
                    target=_read_stream,
                    args=(execution_id, proc.stderr, "warn", "codex-stderr", stderr_tail),  # Plan 68 AD-1 — tail dedicado (era stdout_tail)
                    daemon=True,
                ),
            ]
            for reader in readers:
                reader.start()

            return_code = proc.wait()
            for reader in readers:
                reader.join(timeout=5)

            duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            output = _read_output(output_file, stdout_tail)
            _append_resume_output(
                execution_id,
                output=output,
                return_code=return_code,
                output_file=output_file,
                duration_ms=duration_ms,
                user=user,
            )
            if return_code == 0:
                _mark_status(execution_id, "completed")
                _push(execution_id, "info", f"codex input completed ({duration_ms}ms)", group="operator")
            else:
                _mark_status(execution_id, "error", f"codex input failed with code {return_code}")
                _push(
                    execution_id,
                    "error",
                    f"codex input failed with code {return_code}",
                    group="operator",
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[exec=%s] codex input resume failed", execution_id)
            _mark_status(execution_id, "error", str(exc))
            _push(execution_id, "error", f"codex input resume failed: {exc}", group="operator")


def _append_resume_output(
    execution_id: int,
    *,
    output: str,
    return_code: int | None,
    output_file: Path,
    duration_ms: int,
    user: str | None,
) -> None:
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        previous = (row.output or "").strip()
        if output.strip():
            row.output = (previous + "\n\n---\n\n" + output.strip()).strip() if previous else output.strip()
            row.output_format = "markdown"
        md = row.metadata_dict
        resume_runs = list(md.get("codex_resume_runs") or [])
        resume_runs.append(
            {
                "output_file": str(output_file),
                "exit_code": return_code,
                "duration_ms": duration_ms,
                "user": user,
                "completed_at": datetime.utcnow().isoformat(),
            }
        )
        md["codex_resume_runs"] = resume_runs[-20:]
        row.metadata_dict = md


def _mark_status(execution_id: int, status: str, error: str | None = None) -> None:
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        row.status = status
        row.error_message = error
        if status in {"completed", "error", "cancelled"}:
            row.completed_at = datetime.utcnow()


def _run_pre_run_checks(
    execution_id: int,
    workspace_root: str | None,
    ticket_id: int | None,
    agent_type: str | None,
) -> bool:
    from services.pre_run_git import run_pull_check

    def log(level: str, message: str) -> None:
        log_streamer.push(
            execution_id,
            level,
            message,
            group="pre_run",
            event_type="pre_run",
        )

    result = run_pull_check(workspace_root, log=log)
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return False
        current_md = row.metadata_dict
        current_md["pre_run"] = {"git_pull_check": result.to_dict()}
        row.metadata_dict = current_md

    if not result.ok:
        error = "; ".join(result.errors or result.warnings or ["pre-run git check failed"])
        log("error", f"pre-run bloqueado: {error}")
        _mark_terminal(execution_id, status="error", error=error)
        if ticket_id is not None:
            ticket_status.on_execution_end(
                ticket_id=ticket_id,
                execution_id=execution_id,
                final_status="error",
                agent_type=agent_type,
                error=error,
            )
        return False

    for warning in result.warnings:
        log("warn", warning)
    return True


def _read_output(output_file: Path | None, stdout_tail: list[str]) -> str:
    if output_file and output_file.exists():
        try:
            text = output_file.read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError:
            pass
    return "\n".join(stdout_tail[-80:]).strip()


def reap(execution_id: int, grace_seconds: int = 10) -> bool:
    """R0.1 — Termina el subproceso registrado para execution_id (codex_cli).

    Busca el Popen exacto registrado bajo _PROCESSES_LOCK. Hace terminate()
    → wait(grace) → kill() best-effort. Solo actua sobre el pid registrado.

    Retorna True si el proceso fue reaped.
    Retorna False si no estaba registrado o ya habia terminado.
    """
    with _PROCESSES_LOCK:
        proc = _PROCESSES.get(execution_id)
    if proc is None:
        return False
    try:
        proc.terminate()
        try:
            proc.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return True
    except Exception:  # noqa: BLE001
        return False


def _mark_terminal(
    execution_id: int,
    *,
    status: str,
    output: str | None = None,
    error: str | None = None,
    metadata: dict | None = None,
) -> None:
    emit_failure_feedback = False
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        row.status = status
        row.output = output
        row.output_format = "markdown"
        row.error_message = error
        row.completed_at = datetime.utcnow()
        current_md = row.metadata_dict
        current_md.update(metadata or {})
        current_md["runtime"] = RUNTIME
        # V0.4 — taxonomía de fallos (clave nueva, no renombra nada).
        if status in ("error", "needs_review"):
            try:
                from harness.failure import classify
                kind = classify(
                    return_code=current_md.get("return_code"),
                    error_message=error,
                    metadata={**current_md, "status": status,
                              "contract_result": current_md.get("contract_result")},
                )
                if kind is not None:
                    current_md["failure_kind"] = kind
            except Exception:  # noqa: BLE001
                logger.debug("[exec=%s] failure classify falló", execution_id, exc_info=True)
            emit_failure_feedback = True
        row.metadata_dict = current_md

    if status == "completed":
        try:
            from services import self_review

            outcome = self_review.apply_to_execution(execution_id=execution_id)
            status = str(outcome.get("status") or status)
            if status in ("error", "needs_review"):
                emit_failure_feedback = True
        except Exception:  # noqa: BLE001
            logger.debug("[exec=%s] self_review apply falló (fail-open)", execution_id, exc_info=True)

    if emit_failure_feedback:
        try:
            from services import ado_feedback

            ado_feedback.comment_run_outcome(execution_id)
        except Exception:  # noqa: BLE001
            logger.debug("[exec=%s] ado_feedback comment falló (no crítico)", execution_id, exc_info=True)


def _read_status(execution_id: int, *, fallback: str) -> str:
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return fallback
        return row.status or fallback


def write_repro_script(
    run_dir: "Path",
    *,
    cmd: list[str],
    env: dict[str, str],
) -> None:
    """H7.2 — Escribe run_dir/repro.ps1 con el comando exacto + env STACKY_* no sensibles.

    Espeja el repro.ps1 que claude_code_cli_runner ya genera (F1.2).
    Las variables sensibles se filtran con agent_env.is_denied.
    Solo incluye variables STACKY_* para mantener el script mínimo y reproducible.
    """
    from services.agent_env import is_denied

    # Incluir solo vars STACKY_* que no sean sensibles (is_denied también protege PATH, etc.)
    safe_env: list[tuple[str, str]] = [
        (k, v)
        for k, v in sorted(env.items())
        if k.upper().startswith("STACKY_") and not is_denied(k)
    ]

    lines: list[str] = [
        "# Stacky repro script — codex_cli_runner (H7.2)",
        "# Ejecutá este script para reproducir la ejecución localmente.",
        "",
    ]

    if safe_env:
        lines.append("# Variables de entorno no sensibles")
        for k, v in safe_env:
            # Escaping mínimo para PowerShell: las comillas simples en el valor se duplican
            safe_v = v.replace("'", "''")
            lines.append(f"$env:{k} = '{safe_v}'")
        lines.append("")

    # Comando como invocación PowerShell
    ps_cmd = " ".join(f'"{part}"' if " " in part else part for part in cmd)
    lines.append("# Comando")
    lines.append(ps_cmd)
    lines.append("")

    script_path = Path(run_dir) / "repro.ps1"
    script_path.write_text("\n".join(lines), encoding="utf-8")
