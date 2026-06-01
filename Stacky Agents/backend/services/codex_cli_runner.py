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
            status="running",
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
    _push(execution_id, "info", "start codex cli runtime")
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
        prompt = _build_codex_prompt(
            selected_agent=selected_agent,
            all_agents=all_agents,
            ticket_message=masked_message,
            agent_bundle_dir=agent_bundle_dir,
            agent_manifest_file=agent_manifest_file,
            invocation_block=invocation_block,
        )
        prompt_file = run_dir / "prompt.md"
        prompt_file.write_text(prompt, encoding="utf-8")

        cmd = _build_command(
            cwd=cwd,
            output_file=output_file,
            model_override=model_override,
        )
        log("info", f"codex cli cwd={cwd}")
        log("info", "codex cli command: " + _display_command(cmd))
        log(
            "info",
            f"loaded {len(all_agents)} GitHub Copilot agent prompt(s); selected {selected_agent.filename}",
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

        readers = [
            threading.Thread(
                target=_read_stream,
                args=(execution_id, proc.stdout, "info", "codex", stdout_tail),
                daemon=True,
            ),
            threading.Thread(
                target=_read_stream,
                args=(execution_id, proc.stderr, "warn", "codex-stderr", stdout_tail),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()

        _write_prompt_to_stdin(execution_id, proc, prompt)

        return_code = proc.wait()
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
            "codex_model": model_override or config.CODEX_CLI_MODEL or None,
            "exit_code": return_code,
            "duration_ms": duration_ms,
            "output_file": str(output_file),
            "prompt_file": str(prompt_file),
            "agent_bundle_dir": str(agent_bundle_dir),
            "agent_manifest_file": str(agent_manifest_file),
            "agent_count": len(all_agents),
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
            log("info", f"codex cli completed ({duration_ms}ms)")
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
        except Exception:
            logger.exception("could not mark ticket status after codex cli failure")
    finally:
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
) -> str:
    inventory = _format_agent_inventory(all_agents, agent_bundle_dir)
    selected_path = str(Path(config.VSCODE_PROMPTS_DIR) / selected_agent.filename)

    return f"""# Stacky Agents Codex CLI runtime

{invocation_block}

Stacky te esta lanzando desde Codex CLI para trabajar sobre el ticket y mantener
trazabilidad en los logs del workbench. No se inyecta el contenido del
`.agent.md` seleccionado en este mensaje: debes leerlo desde la ruta indicada en
el bloque "Agente Stacky seleccionado" y usar ese archivo como fuente de rol,
criterio, tono, restricciones y forma de trabajo.

## Agente seleccionado

- Nombre: {selected_agent.name}
- Archivo: {selected_agent.filename}
- Path: {selected_path}
- Descripcion: {selected_agent.description or "(sin descripcion)"}

## Catalogo de agentes GitHub Copilot Pro disponibles

Stacky copio todos los `.agent.md` conocidos a esta ejecucion para que Codex
CLI pueda consultar cualquier agente GitHub Copilot Pro aunque el operador haya
elegido solo uno.

- Carpeta local: {agent_bundle_dir}
- Manifest JSON: {agent_manifest_file}

{inventory}

## Ticket y contexto

{ticket_message}

## Instrucciones de ejecucion

- Trabaja en el workspace configurado para el proyecto.
- Mantene el comportamiento esperado por el agente seleccionado.
- Si editas archivos, limita el cambio al alcance del ticket y deja evidencia
  clara en tu respuesta final.
- Reporta comandos relevantes, archivos tocados y cualquier bloqueo real.
- Regla absoluta: no toques Azure DevOps. No publiques comentarios, no crees
  ni actualices work items, no cambies estados, no ejecutes APIs/CLI/scripts de
  ADO y no solicites credenciales ADO. Stacky Agents es el unico autorizado a
  escribir en ADO.
- Si el resultado debe ser un comentario ADO, genera el archivo
  `Agentes/outputs/<ADO_ID>/comment.html` y opcionalmente `comment.meta.json`.
  Stacky lo validara y publicara.
- Si el resultado debe ser una Task hija para un Epic, genera
  `Agentes/outputs/epic-<ADO_ID>/<RF_SLUG>/pending-task.json` y los archivos
  referenciados, como `plan-de-pruebas.md`. Stacky creara la Task desde la UI y
  marcara el JSON como consumido.
"""


def _materialize_agent_prompts(
    run_dir: Path,
    agents: list[vscode_agents.VsCodeAgent],
) -> tuple[Path, Path]:
    bundle_dir = run_dir / "github_copilot_agents"
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
        return "- No se encontraron agentes en VSCODE_PROMPTS_DIR."
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
) -> None:
    if stream is None:
        return
    for raw in stream:
        line = raw.rstrip("\r\n")
        if not line:
            continue
        message, level = _summarize_codex_line(line, default_level)
        session_id = _extract_codex_session_id(line)
        if session_id:
            _remember_codex_session(execution_id, session_id)
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
                    args=(execution_id, proc.stderr, "warn", "codex-stderr", stdout_tail),
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


def _read_output(output_file: Path | None, stdout_tail: list[str]) -> str:
    if output_file and output_file.exists():
        try:
            text = output_file.read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError:
            pass
    return "\n".join(stdout_tail[-80:]).strip()


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
