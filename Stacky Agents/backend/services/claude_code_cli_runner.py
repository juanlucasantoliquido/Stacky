"""Claude Code CLI runtime for Stacky Agents.

Lanza prompts a través del CLI `claude` (Claude Code) en modo non-interactive
con streaming JSON. Mantiene el mismo contrato estructural que
`codex_cli_runner.py`: crea una fila AgentExecution, despacha un thread en
background, hace streaming de stdout/stderr al log_streamer y marca el
estado terminal cuando el proceso termina.

Flags de invocación:
    claude -p "<prompt>" --output-format stream-json --verbose

    -p / --print       modo non-interactive: escribe el prompt directo
    --output-format    stream-json: devuelve eventos JSON línea a línea
    --verbose          incluye telemetría de tokens / tool calls en el stream
    --model <model>    modelo a usar (ej. claude-sonnet-4-5); opcional
    --dangerously-skip-permissions
                       # TODO: verificar si esta flag existe en la versión
                       # instalada del operador. Codex tiene
                       # --dangerously-bypass-approvals-and-sandbox;
                       # Claude Code CLI puede diferir. Por ahora NO se agrega
                       # por defecto. Agregar con CLAUDE_CODE_CLI_SKIP_PERMISSIONS=true
                       # una vez confirmado.

Supuestos documentados (para revisión del operador):
    1. El binario se llama `claude` (configurable vía CLAUDE_CODE_CLI_BIN).
    2. El flag para prompt non-interactive es `-p` o `--print`.
    3. El streaming JSON se activa con `--output-format stream-json`.
    4. `--verbose` produce eventos adicionales (token counts, tool calls).
    5. No existe flag equivalente a `--output-last-message` de Codex;
       el output final se captura del stream (último evento `result` o
       acumulado del tipo `assistant`).
    6. Claude Code CLI no usa stdin para el prompt (a diferencia de Codex).
       El prompt se pasa directo como argumento de `-p`.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import log_streamer
from config import config
from db import session_scope
from models import AgentExecution, Ticket
from services import (
    context_enrichment,
    pii_masker,
    stacky_agents as stacky_agents_svc,
    ticket_status,
    vscode_agents,
)
from services.agent_env import build_agent_env
from services.project_context import resolve_project_context
from services.manifest_watcher import append_event, write_heartbeat, write_manifest
from services.stacky_logger import logger as stacky_logger

logger = logging.getLogger("stacky_agents.claude_code_cli")

RUNTIME = "claude_code_cli"

_PROCESSES: dict[int, subprocess.Popen[str]] = {}
_PROCESSES_LOCK = threading.Lock()
# Lock por ejecución para serializar escrituras al stdin del proceso (el operador
# puede enviar varias respuestas concurrentes desde la consola).
_STDIN_LOCKS: dict[int, threading.Lock] = {}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def start_claude_code_cli_run(
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
    """Crea una fila AgentExecution y lanza Claude Code CLI en background.

    Retorna el execution_id recién creado.  El thread de background actualiza
    la fila al completarse o fallar.
    """
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

    log_streamer.open(execution_id)
    log_streamer.push(
        execution_id,
        "info",
        "preparando ejecucion claude code cli",
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
        name=f"claude-code-cli-{execution_id}",
    )
    thread.start()
    return execution_id


def cancel(execution_id: int, *, grace_seconds: float = 8.0) -> bool:
    """Cierra la sesión Claude Code CLI de forma ordenada.

    Cerrar stdin hace que Claude termine el turno en curso y salga limpio
    (exit 0 → 'completed'). Si no muere dentro de `grace_seconds`, un watcher
    lo termina/mata. La llamada retorna de inmediato (no bloquea el request).
    """
    with _PROCESSES_LOCK:
        proc = _PROCESSES.get(execution_id)
    if proc is None:
        return False
    _push(execution_id, "warn", "claude code cli cierre solicitado (cerrando stdin)", group="operator")
    try:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
    except Exception:
        pass

    def _grace_watch() -> None:
        try:
            proc.wait(timeout=grace_seconds)
            return  # salió limpio
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    threading.Thread(target=_grace_watch, daemon=True, name=f"claude-cli-cancel-{execution_id}").start()
    return True


def _user_message_line(text: str) -> str:
    """Codifica un mensaje de usuario en el formato stream-json de Claude Code.

    Una línea JSONL por mensaje:
      {"type":"user","message":{"role":"user","content":[{"type":"text","text":"..."}]}}
    """
    payload = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        },
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"


def send_input(execution_id: int, text: str, *, user: str | None = None) -> dict[str, Any]:
    """Envía texto del operador a una ejecución Claude Code CLI viva.

    Escribe un mensaje de usuario stream-json en el stdin del proceso. Claude
    procesa el turno y continúa la misma conversación (stdin permanece abierto
    para multi-turno). Si el proceso ya no acepta stdin devuelve HTTP 409 vía
    RuntimeError.
    """
    message = (text or "").strip()
    if not message:
        raise ValueError("text is required")

    with _PROCESSES_LOCK:
        proc = _PROCESSES.get(execution_id)
    if proc is None or proc.poll() is not None:
        raise RuntimeError(
            "La ejecución de Claude ya terminó; no se puede enviar más texto."
        )
    if proc.stdin is None or proc.stdin.closed:
        raise RuntimeError("El stdin de Claude no está disponible para esta ejecución.")

    lock = _STDIN_LOCKS.setdefault(execution_id, threading.Lock())
    with lock:
        try:
            proc.stdin.write(_user_message_line(message))
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeError(f"No se pudo escribir en Claude: {exc}") from exc

    _push(
        execution_id,
        "info",
        f"operator → claude: {message[:2000]}",
        group="operator",
    )
    return {"ok": True, "mode": "stdin", "execution_id": execution_id}


# ---------------------------------------------------------------------------
# Thread de background
# ---------------------------------------------------------------------------

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
    return_code: int | None = None
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    agent_type: str | None = None
    ticket_id: int | None = None
    mask_map: dict[str, str] = {}

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
        log("info", "start claude code cli runtime")

        selected_agent = vscode_agents.get_agent_by_filename(
            config.VSCODE_PROMPTS_DIR, vscode_agent_filename
        )
        all_agents = vscode_agents.list_agents(config.VSCODE_PROMPTS_DIR)
        if selected_agent is None:
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
        run_dir = Path(__file__).resolve().parents[1] / "data" / "claude_code_runs" / str(execution_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        # Claude Code CLI no tiene --output-last-message; capturamos del stream.
        # output_file se usa como sink para el resultado final extraído del stream.
        output_file = run_dir / "last_message.md"
        prompt_file = run_dir / "prompt.md"

        # Fase B — enriquecimiento de contexto (épica + artifacts + similares +
        # comentarios/adjuntos ADO). Corre acá, en el thread de background, para no
        # bloquear el request de lanzamiento (el dock ya abrió con execution_id).
        log("info", "enriqueciendo contexto del ticket…")
        enriched_blocks, _ado_stats = context_enrichment.enrich_blocks(
            ticket_id=ticket_id,
            agent_type=agent_type or "",
            raw_blocks=raw_blocks,
            project_ctx=project_ctx,
            log=log,
        )
        rich_message = context_enrichment.build_ticket_context_text(
            ado_id=t_ado_id,
            title=t_title,
            description=t_desc,
            work_item_type=t_wit,
            blocks=enriched_blocks,
        )
        # Fallback: si no se pudo armar nada (ticket sin datos), usar el mensaje
        # title-only que vino del dispatcher.
        if not rich_message.strip():
            rich_message = ticket_message
        # Fase B — PII masking ANTES de mandar el prompt al CLI (paridad con
        # github_copilot). Se guarda el mask_map para re-hidratar el output.
        masked_message, mask_map = pii_masker.mask_text(rich_message)
        if mask_map:
            log("info", f"PII masking: {len(mask_map)} ocurrencias enmascaradas")

        invocation_block = stacky_agents_svc.build_invocation_block(
            entry=agent_entry,
            workspace_root=cwd,
        )

        # Fase C — cómo se referencia la persona del agente.
        #   "append" (default): system prompt real con el contrato de invocación
        #                       y la ruta del .agent.md, sin copiar su contenido.
        #                       El primer mensaje de usuario lleva ticket + contexto.
        #   "user_message":     contrato de invocación en el primer mensaje (rollback),
        #                       también sin copiar el contenido del .agent.md.
        system_prompt_mode = (config.CLAUDE_CODE_CLI_SYSTEM_PROMPT_MODE or "append")
        system_prompt_file: Path | None = None
        if system_prompt_mode == "append":
            system_prompt_text = _build_system_prompt(
                selected_agent,
                invocation_block=invocation_block,
            )
            system_prompt_file = run_dir / "system_prompt.md"
            system_prompt_file.write_text(system_prompt_text, encoding="utf-8")
            prompt = _build_user_message(
                all_agents=all_agents,
                ticket_message=masked_message,
                invocation_block=invocation_block,
            )
            log(
                "info",
                f"adoptando agente {selected_agent.name} ({selected_agent.filename}) "
                "vía referencia a .agent.md (--append-system-prompt-file)",
                group="operator",
            )
        else:
            # Rollback: todo en el primer mensaje de usuario.
            prompt = _build_claude_code_prompt(
                selected_agent=selected_agent,
                all_agents=all_agents,
                ticket_message=masked_message,
                invocation_block=invocation_block,
            )
            log(
                "info",
                f"agente {selected_agent.name} ({selected_agent.filename}) embebido en el "
                "primer mensaje (CLAUDE_CODE_CLI_SYSTEM_PROMPT_MODE=user_message)",
                group="operator",
            )
        prompt_file.write_text(prompt, encoding="utf-8")

        cmd = _build_command(
            model_override=model_override,
            system_prompt_file=system_prompt_file,
        )
        log("info", f"claude code cli cwd={cwd}")
        log("info", "claude code cli command: " + _display_command(cmd))
        log(
            "info",
            f"loaded {len(all_agents)} Stacky agent prompt(s); selected {selected_agent.filename}",
        )

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        # Cap de sesión (segundos). 0 = ilimitado: la sesión interactiva vive
        # hasta que el operador la cierra/cancela o Claude termina por su cuenta.
        session_timeout = config.CLAUDE_CODE_CLI_TIMEOUT if config.CLAUDE_CODE_CLI_TIMEOUT > 0 else None

        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.PIPE,      # interactivo: prompt + respuestas del operador
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
            env=build_agent_env(extra={"STACKY_EXECUTION_ID": str(execution_id)}),
        )
        log("info", f"claude code cli process started pid={proc.pid}")
        with _PROCESSES_LOCK:
            _PROCESSES[execution_id] = proc

        # Enviar el prompt inicial como primer mensaje de usuario (stream-json).
        # NO cerramos stdin: queda abierto para que el operador responda desde la
        # consola in-page (send_input).
        try:
            proc.stdin.write(_user_message_line(prompt))
            proc.stdin.flush()
            log("info", f"prompt inicial enviado a claude por stdin ({len(prompt)} chars)", group="operator")
        except Exception as exc:  # noqa: BLE001
            log("error", f"no se pudo enviar el prompt inicial a claude: {exc}")
            raise

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
            name=f"claude-code-cli-hb-{execution_id}",
        )
        heartbeat_thread.start()

        # Acumulador del output final extraído del stream JSON
        final_output: list[str] = []

        readers = [
            threading.Thread(
                target=_read_stream,
                args=(execution_id, proc.stdout, "info", "claude-code", stdout_tail, final_output),
                daemon=True,
            ),
            threading.Thread(
                target=_read_stream,
                args=(execution_id, proc.stderr, "warn", "claude-code-stderr", stdout_tail, None),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()

        # Sesión interactiva: esperamos en bucle hasta que el proceso termine
        # (operador cierra/cancela stdin, o Claude finaliza). El heartbeat sigue
        # latiendo en su propio thread, así que el reaper no lo marca colgado.
        import time as _time
        session_deadline = (_time.monotonic() + session_timeout) if session_timeout else None
        while True:
            try:
                return_code = proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                if session_deadline is not None and _time.monotonic() > session_deadline:
                    log("warn", f"claude code cli cap de sesión alcanzado ({session_timeout}s) — terminando")
                    try:
                        if proc.stdin and not proc.stdin.closed:
                            proc.stdin.close()
                    except Exception:
                        pass
                    proc.terminate()
                    try:
                        return_code = proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        return_code = proc.wait()
                    break
                continue

        heartbeat_stop.set()
        for reader in readers:
            reader.join(timeout=5)
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=2)

        with _PROCESSES_LOCK:
            _PROCESSES.pop(execution_id, None)
        _STDIN_LOCKS.pop(execution_id, None)

        duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)

        # Escribir output final al archivo para trazabilidad.
        # Re-hidratar PII enmascarada para que el operador vea los datos reales.
        output = _extract_output(final_output, stdout_tail)
        if output and mask_map:
            output = pii_masker.unmask(output, mask_map)
        if output:
            output_file.write_text(output, encoding="utf-8")

        invocation_meta = stacky_agents_svc.invocation_metadata(
            entry=agent_entry,
            workspace_root=cwd,
        )
        metadata = {
            "runtime": RUNTIME,
            "vscode_agent_filename": vscode_agent_filename,
            "workspace_root": str(cwd),
            "claude_code_cli_bin": cmd[0],
            "claude_code_model": model_override or config.CLAUDE_CODE_CLI_MODEL or None,
            "exit_code": return_code,
            "duration_ms": duration_ms,
            "output_file": str(output_file),
            "prompt_file": str(prompt_file),
            "agent_count": len(all_agents),
            "system_prompt_mode": system_prompt_mode,
            "system_prompt_file": str(system_prompt_file) if system_prompt_file else None,
            "agent_name": selected_agent.name,
            "pii_masked": bool(mask_map),
            **invocation_meta,
        }

        if return_code == 0:
            _mark_terminal(
                execution_id,
                status="completed",
                output=output,
                metadata=metadata,
            )
            _safe_write_manifest(
                run_dir,
                run_id=execution_id,
                agent_type=agent_type,
                status="completed",
                exit_code=return_code,
                output_file=output_file,
                prompt_file=prompt_file,
            )
            append_event(
                run_dir,
                execution_id=execution_id,
                event_type="completed",
                payload={"exit_code": return_code, "duration_ms": duration_ms},
            )
            log("info", f"claude code cli completed ({duration_ms}ms)")
            ticket_status.on_execution_end(
                ticket_id=ticket_id,
                execution_id=execution_id,
                final_status="completed",
                agent_type=agent_type,
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
            error = f"claude code cli exited with code {return_code}"
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
        _STDIN_LOCKS.pop(execution_id, None)
        logger.exception("[exec=%s] claude code cli runtime failed", execution_id)
        log("error", f"claude code cli runtime failed: {exc}")
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
        except Exception:
            logger.exception("could not mark ticket status after claude code cli failure")
    finally:
        log_streamer.close(execution_id)


# ---------------------------------------------------------------------------
# Construcción del comando
# ---------------------------------------------------------------------------

def _build_command(
    *,
    model_override: str | None,
    system_prompt_file: Path | None = None,
) -> list[str]:
    """Construye el comando CLI para Claude Code en modo interactivo (streaming).

    El prompt NO va como argumento posicional: se envía como mensaje de usuario
    stream-json por stdin (ver _user_message_line). Esto permite mantener stdin
    abierto y enviar respuestas del operador en turnos sucesivos.

    Flags:
      -p / --print              : modo print (no abre UI interactiva de terminal)
      --input-format stream-json: lee mensajes de usuario JSONL desde stdin
      --output-format stream-json --verbose : eventos JSONL en stdout
      --append-system-prompt-file : contrato/ruta del .agent.md como system
                                    prompt real (Fase C); no copia el contenido
                                    del agente. Usa archivo para no chocar con
                                    el límite de longitud de línea en Windows.
      --model                   : modelo específico (opcional)
    """
    claude_bin = _resolve_claude_code_cli_bin()
    model = model_override or config.CLAUDE_CODE_CLI_MODEL

    cmd = [
        claude_bin,
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",        # stream-json requiere --verbose
    ]

    # Fase C — referenciar la persona del agente sin copiar su prompt.
    if system_prompt_file is not None:
        cmd.extend(["--append-system-prompt-file", str(system_prompt_file)])

    # Permisos: en modo -p no hay forma de aprobar tool calls interactivamente,
    # así que el agente queda bloqueado salvo que se configure un modo permisivo.
    if config.CLAUDE_CODE_CLI_SKIP_PERMISSIONS:
        cmd.append("--dangerously-skip-permissions")
    else:
        permission_mode = (config.CLAUDE_CODE_CLI_PERMISSION_MODE or "acceptEdits").strip()
        if permission_mode:
            cmd.extend(["--permission-mode", permission_mode])

    if model:
        cmd.extend(["--model", model])

    return cmd


def _resolve_claude_code_cli_bin() -> str:
    """Resuelve la ruta del binario `claude` en el PATH o rutas conocidas.

    Lanza FileNotFoundError si no lo encuentra — el dispatcher en agent_runner
    captura este error y hace fallback a github_copilot.
    """
    configured = (config.CLAUDE_CODE_CLI_BIN or "claude").strip().strip('"')

    found = shutil.which(configured)
    if found:
        return found

    candidates: list[Path] = []
    if configured and configured.lower() not in {"claude", "claude.exe"}:
        configured_path = Path(configured)
        candidates.append(configured_path)
        if os.name == "nt" and configured_path.suffix == "":
            candidates.append(configured_path.with_suffix(".exe"))

    if os.name == "nt":
        # Rutas conocidas de instalación en Windows
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "AnthropicClaude" / "claude.exe")
            # npm global install: npm i -g @anthropic-ai/claude-code
        app_data = os.environ.get("APPDATA")
        if app_data:
            candidates.append(Path(app_data) / "npm" / "claude.cmd")
            candidates.append(Path(app_data) / "npm" / "claude.exe")
        # nvm / fnm path típico
        candidates.append(Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd")
        candidates.append(Path.home() / "AppData" / "Roaming" / "npm" / "claude.exe")
    else:
        # Linux / macOS: rutas comunes post npm install -g
        candidates.append(Path("/usr/local/bin/claude"))
        candidates.append(Path.home() / ".local" / "bin" / "claude")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(
        "No encontré Claude Code CLI ('claude'). "
        "Instalalo con: npm install -g @anthropic-ai/claude-code "
        "o configurá CLAUDE_CODE_CLI_BIN con la ruta al binario."
    )


def _display_command(cmd: list[str]) -> str:
    """Versión legible del comando para logs (el prompt va por stdin, no acá)."""
    safe: list[str] = []
    for part in cmd:
        if any(ch.isspace() for ch in part):
            safe.append(f'"{part}"')
        else:
            safe.append(part)
    return " ".join(safe)


# ---------------------------------------------------------------------------
# Construcción del prompt
# ---------------------------------------------------------------------------

# Reglas duras de Stacky: definen *cómo* actúa el agente (no *qué* hacer). Van
# al canal de system prompt junto con la persona del .agent.md.
_STACKY_RULES = """## Reglas de ejecución (Stacky Agents)

- Trabajá en el workspace configurado para el proyecto.
- Mantené el comportamiento esperado por el agente que estás adoptando.
- Si editás archivos, limitá el cambio al alcance del ticket y dejá evidencia
  clara en tu respuesta final.
- Reportá comandos relevantes, archivos tocados y cualquier bloqueo real.
- Regla absoluta: no toques Azure DevOps. No publiques comentarios, no crees
  ni actualices work items, no cambies estados, no ejecutes APIs/CLI/scripts de
  ADO y no solicites credenciales ADO. Stacky Agents es el único autorizado a
  escribir en ADO.
- Si el resultado debe ser un comentario ADO, generá el archivo
  `Agentes/outputs/<ADO_ID>/comment.html` y opcionalmente `comment.meta.json`.
  Stacky lo validará y publicará.
- Si el resultado debe ser una Task hija para un Epic, generá
  `Agentes/outputs/epic-<ADO_ID>/<RF_SLUG>/pending-task.json` y los archivos
  referenciados, como `plan-de-pruebas.md`. Stacky creará la Task desde la UI y
  marcará el JSON como consumido."""


def _build_agent_inventory(all_agents: list[vscode_agents.VsCodeAgent]) -> str:
    inventory_lines: list[str] = []
    for agent in all_agents:
        desc = (agent.description or "").replace("\n", " ").strip()
        if len(desc) > 220:
            desc = desc[:217] + "..."
        inventory_lines.append(
            f"- {agent.name} (`{agent.filename}`): {desc or 'sin descripcion'}"
        )
    return "\n".join(inventory_lines) if inventory_lines else "- (no se encontraron agentes)"


def _build_system_prompt(
    selected_agent: vscode_agents.VsCodeAgent,
    *,
    invocation_block: str = "",
) -> str:
    """System prompt real para --append-system-prompt-file (Fase C).

    Declara dónde está el `.agent.md` seleccionado y las reglas duras de Stacky,
    pero no copia el contenido del agente dentro del prompt.
    """
    invocation_section = f"{invocation_block}\n\n" if invocation_block else ""
    return f"""Stacky te lanzó desde Claude Code CLI para trabajar sobre un ticket y mantener
trazabilidad en los logs del workbench. No se inyecta el contenido del `.agent.md`
seleccionado en este system prompt: leelo desde la ruta indicada abajo y usá ese
archivo como fuente de rol, criterio, tono, restricciones y forma de trabajo.

{invocation_section}# Agente que estás adoptando: {selected_agent.name} ({selected_agent.filename})

{_STACKY_RULES}
"""


def _build_user_message(
    *,
    all_agents: list[vscode_agents.VsCodeAgent],
    ticket_message: str,
    invocation_block: str = "",
) -> str:
    """Primer mensaje de usuario (Fase C): define *qué* hacer — ticket + contexto.

    La persona ya viaja por el canal de system prompt (ver _build_system_prompt),
    así que acá solo van el catálogo de agentes (referencia) y el ticket/contexto.
    """
    inventory = _build_agent_inventory(all_agents)
    invocation_section = f"{invocation_block}\n\n" if invocation_block else ""
    return f"""{invocation_section}## Catálogo de agentes Stacky disponibles (referencia)

{inventory}

## Ticket y contexto

{ticket_message}
"""


def _build_claude_code_prompt(
    *,
    selected_agent: vscode_agents.VsCodeAgent,
    all_agents: list[vscode_agents.VsCodeAgent],
    ticket_message: str,
    invocation_block: str = "",
) -> str:
    """Prompt monolítico (modo rollback `user_message`): persona + contexto en el
    primer mensaje de usuario. Es el comportamiento previo a Fase C, disponible vía
    CLAUDE_CODE_CLI_SYSTEM_PROMPT_MODE=user_message si --append-system-prompt diera
    problemas.
    """
    inventory = _build_agent_inventory(all_agents)
    invocation_section = f"{invocation_block}\n\n" if invocation_block else ""
    return f"""# Stacky Agents Claude Code CLI runtime

{invocation_section}Stacky te esta lanzando desde Claude Code CLI para trabajar sobre el ticket y
mantener trazabilidad en los logs del workbench. No se inyecta el contenido del
`.agent.md` seleccionado en este mensaje: debes leerlo desde la ruta indicada en
el bloque "Agente Stacky seleccionado" y usar ese archivo como fuente de rol,
criterio, tono, restricciones y forma de trabajo.

## Agente seleccionado

- Nombre: {selected_agent.name}
- Archivo: {selected_agent.filename}
- Descripcion: {selected_agent.description or "(sin descripcion)"}

## Catalogo de agentes Stacky disponibles

{inventory}

## Ticket y contexto

{ticket_message}

{_STACKY_RULES}
"""


# ---------------------------------------------------------------------------
# Streaming y parsing del output
# ---------------------------------------------------------------------------

def _read_stream(
    execution_id: int,
    stream: Any,
    default_level: str,
    group: str,
    tail: list[str],
    final_output: list[str] | None,
) -> None:
    """Lee stdout/stderr línea a línea y parsea el stream JSON de Claude Code.

    Claude Code con --output-format stream-json emite eventos JSONL.
    Los eventos del tipo 'assistant' con role='assistant' contienen el texto
    generado; los eventos 'result' tienen el output final consolidado.
    """
    if stream is None:
        return
    for raw in stream:
        line = raw.rstrip("\r\n")
        if not line:
            continue
        message, level, extracted_text = _parse_claude_code_line(line, default_level)
        _push(execution_id, level, message, group=group)
        tail.append(message)
        if len(tail) > 200:
            del tail[:50]
        # Acumular texto de output para extracción final
        if final_output is not None and extracted_text:
            final_output.append(extracted_text)


def _parse_claude_code_line(line: str, default_level: str) -> tuple[str, str, str]:
    """Parsea una línea del stream JSON de Claude Code CLI.

    Retorna (message_for_log, level, extracted_text_for_output).

    Estructura esperada del stream-json de Claude Code:
      {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "..."}]}}
      {"type": "result", "result": "...", "is_error": false}
      {"type": "system", "subtype": "init", ...}
      {"type": "tool_use", ...}
      {"type": "tool_result", ...}
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return (line[:4000], default_level, "")

    if not isinstance(data, dict):
        return (str(data)[:4000], default_level, "")

    event_type = str(data.get("type") or "event")
    level = default_level
    extracted_text = ""

    # Evento de resultado final
    if event_type == "result":
        is_error = bool(data.get("is_error"))
        result_val = data.get("result") or data.get("output") or ""
        if isinstance(result_val, str) and result_val.strip():
            extracted_text = result_val.strip()
            level = "error" if is_error else "info"
            return (
                f"result({'error' if is_error else 'ok'}): {result_val.strip()[:3000]}",
                level,
                extracted_text,
            )
        return (f"result: {json.dumps(data, ensure_ascii=False)[:3500]}", level, "")

    # Evento de mensaje del asistente (streaming de texto)
    if event_type == "assistant":
        message_obj = data.get("message") or {}
        content = message_obj.get("content") or []
        if isinstance(content, list):
            texts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            full_text = "".join(texts).strip()
            if full_text:
                extracted_text = full_text
                short = full_text[:3000]
                return (f"assistant: {short}", "info", extracted_text)
        return (f"assistant: {json.dumps(data, ensure_ascii=False)[:3500]}", "info", "")

    # Tool use — solo log, sin output
    if event_type == "tool_use":
        tool_name = data.get("name") or data.get("tool_name") or "tool"
        tool_input = data.get("input") or {}
        summary = json.dumps(tool_input, ensure_ascii=False)[:500]
        return (f"tool_use/{tool_name}: {summary}", "info", "")

    if event_type == "tool_result":
        tool_id = data.get("tool_use_id") or ""
        is_err = bool(data.get("is_error"))
        level = "warn" if is_err else "info"
        return (f"tool_result/{tool_id}({'error' if is_err else 'ok'})", level, "")

    # Eventos de sistema (init, etc.)
    if event_type == "system":
        subtype = data.get("subtype") or ""
        return (f"system/{subtype}: {json.dumps(data, ensure_ascii=False)[:500]}", "debug", "")

    # Fallback genérico — igual que Codex
    for key in ("message", "msg", "text", "summary"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return (f"{event_type}: {value.strip()}"[:4000], level, "")

    return (f"{event_type}: {json.dumps(data, ensure_ascii=False)[:3500]}", level, "")


def _extract_output(final_output: list[str], stdout_tail: list[str]) -> str:
    """Extrae el output final del run.

    Prioridad:
      1. Último evento 'result' capturado en final_output.
      2. Concatenación de eventos 'assistant' capturados.
      3. Últimas líneas del tail de stdout.
    """
    if final_output:
        # El último elemento suele ser el 'result' consolidado si está presente
        return "\n\n".join(final_output).strip()
    return "\n".join(stdout_tail[-80:]).strip()


# ---------------------------------------------------------------------------
# Helpers de persistencia (mismo patrón que codex_cli_runner)
# ---------------------------------------------------------------------------

def _resolve_cwd(workspace_root: str | None) -> Path:
    if workspace_root:
        candidate = Path(workspace_root)
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[2]


def _push(
    execution_id: int,
    level: str,
    message: str,
    group: str | None = None,
    indent: int = 0,
) -> None:
    log_streamer.push(execution_id, level, message, group=group, indent=indent)
    backend_level = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }.get(level, logging.INFO)
    logger.log(backend_level, "[exec=%s] %s", execution_id, message)


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


def _mark_terminal(
    execution_id: int,
    *,
    status: str,
    output: str | None = None,
    error: str | None = None,
    metadata: dict | None = None,
) -> None:
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
        row.metadata_dict = current_md


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
        logger.exception("[exec=%s] manifest write failed (no critico)", run_id)
