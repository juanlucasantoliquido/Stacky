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
from models import AgentExecution
from services import ticket_status, vscode_agents
from services.agent_env import build_agent_env
from services.manifest_watcher import append_event, write_heartbeat, write_manifest
from services.stacky_logger import logger as stacky_logger

logger = logging.getLogger("stacky_agents.claude_code_cli")

RUNTIME = "claude_code_cli"

_PROCESSES: dict[int, subprocess.Popen[str]] = {}
_PROCESSES_LOCK = threading.Lock()


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
    _push(execution_id, "info", "start claude code cli runtime")
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


def cancel(execution_id: int) -> bool:
    """Termina el proceso Claude Code CLI si Stacky lo inició para esta ejecución."""
    with _PROCESSES_LOCK:
        proc = _PROCESSES.get(execution_id)
    if proc is None:
        return False
    _push(execution_id, "warn", "claude code cli cancel requested")
    try:
        proc.terminate()
        return True
    except Exception as exc:  # noqa: BLE001
        _push(execution_id, "error", f"claude code cli cancel failed: {exc}")
        return False


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

    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                raise RuntimeError(f"execution_id={execution_id} not found")
            ticket_id = row.ticket_id
            agent_type = row.agent_type

        selected_agent = vscode_agents.get_agent_by_filename(
            config.VSCODE_PROMPTS_DIR, vscode_agent_filename
        )
        all_agents = vscode_agents.list_agents(config.VSCODE_PROMPTS_DIR)
        if selected_agent is None:
            raise RuntimeError(
                f"agent prompt not found: {vscode_agent_filename} "
                f"(VSCODE_PROMPTS_DIR={config.VSCODE_PROMPTS_DIR})"
            )

        cwd = _resolve_cwd(workspace_root)
        run_dir = Path(__file__).resolve().parents[1] / "data" / "claude_code_runs" / str(execution_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        # Claude Code CLI no tiene --output-last-message; capturamos del stream.
        # output_file se usa como sink para el resultado final extraído del stream.
        output_file = run_dir / "last_message.md"
        prompt_file = run_dir / "prompt.md"

        prompt = _build_claude_code_prompt(
            selected_agent=selected_agent,
            all_agents=all_agents,
            ticket_message=ticket_message,
        )
        prompt_file.write_text(prompt, encoding="utf-8")

        cmd = _build_command(
            prompt=prompt,
            model_override=model_override,
        )
        log("info", f"claude code cli cwd={cwd}")
        log("info", "claude code cli command: " + _display_command(cmd))
        log(
            "info",
            f"loaded {len(all_agents)} GitHub Copilot agent prompt(s); selected {selected_agent.filename}",
        )

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        timeout = config.CLAUDE_CODE_CLI_TIMEOUT

        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,   # Claude Code CLI no usa stdin; prompt va en -p
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

        try:
            return_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log("error", f"claude code cli timeout after {timeout}s — terminating")
            proc.terminate()
            try:
                return_code = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                return_code = proc.wait()

        heartbeat_stop.set()
        for reader in readers:
            reader.join(timeout=5)
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=2)

        with _PROCESSES_LOCK:
            _PROCESSES.pop(execution_id, None)

        duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)

        # Escribir output final al archivo para trazabilidad
        output = _extract_output(final_output, stdout_tail)
        if output:
            output_file.write_text(output, encoding="utf-8")

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
    prompt: str,
    model_override: str | None,
) -> list[str]:
    """Construye el comando CLI para Claude Code en modo non-interactive.

    Supuestos sobre flags (verificar con `claude --help` en el host):
      -p / --print         : non-interactive, prompt como argumento posicional
      --output-format      : stream-json para streaming línea a línea
      --verbose            : incluye eventos de tool calls y token usage
      --model              : modelo específico (opcional)
    """
    claude_bin = _resolve_claude_code_cli_bin()
    model = model_override or config.CLAUDE_CODE_CLI_MODEL

    cmd = [
        claude_bin,
        "-p",               # non-interactive print mode
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",        # TODO: verificar si --verbose es soportado en versión instalada
    ]

    if model:
        cmd.extend(["--model", model])  # TODO: verificar flag --model vs -m en versión instalada

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
    """Versión segura del comando para logs: trunca el prompt a 120 chars."""
    safe: list[str] = []
    skip_next = False
    for part in cmd:
        if skip_next:
            truncated = part[:120].replace("\n", "\\n")
            safe.append(f'"<prompt:{len(part)}chars:{truncated}...>"')
            skip_next = False
            continue
        if part == "-p":
            safe.append(part)
            skip_next = True
        elif any(ch.isspace() for ch in part):
            safe.append(f'"{part}"')
        else:
            safe.append(part)
    return " ".join(safe)


# ---------------------------------------------------------------------------
# Construcción del prompt
# ---------------------------------------------------------------------------

def _build_claude_code_prompt(
    *,
    selected_agent: vscode_agents.VsCodeAgent,
    all_agents: list[vscode_agents.VsCodeAgent],
    ticket_message: str,
) -> str:
    """Construye el prompt para Claude Code CLI.

    A diferencia de Codex, el prompt se pasa como argumento de -p, no por stdin.
    Se incluye el system prompt del agente seleccionado inline.
    """
    inventory_lines: list[str] = []
    for agent in all_agents:
        desc = (agent.description or "").replace("\n", " ").strip()
        if len(desc) > 220:
            desc = desc[:217] + "..."
        inventory_lines.append(
            f"- {agent.name} (`{agent.filename}`): {desc or 'sin descripcion'}"
        )
    inventory = "\n".join(inventory_lines) if inventory_lines else "- (no se encontraron agentes)"

    return f"""# Stacky Agents Claude Code CLI runtime

Actua como el agente GitHub Copilot Pro seleccionado por el operador.
Stacky te esta lanzando desde Claude Code CLI para trabajar sobre el mismo
ticket y mantener trazabilidad en los logs del workbench.

## Agente seleccionado

- Nombre: {selected_agent.name}
- Archivo: {selected_agent.filename}
- Descripcion: {selected_agent.description or "(sin descripcion)"}

## System prompt del agente seleccionado

```markdown
{selected_agent.system_prompt}
```

## Catalogo de agentes GitHub Copilot Pro disponibles

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
