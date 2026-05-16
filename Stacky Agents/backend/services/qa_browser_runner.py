"""Background runner for guarded QA Browser runs.

Stacky cannot directly press buttons in the operator's Codex desktop browser.
For the automatic path we launch Codex CLI with the same guarded run spec and
require it to report progress back through the QA Browser endpoints.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import log_streamer
from config import config
from db import session_scope
from models import AgentExecution
from services import codex_cli_runner, ticket_status

logger = logging.getLogger("stacky_agents.qa_browser_runner")

RUNTIME = "codex_cli_qa_browser"

_PROCESSES: dict[int, subprocess.Popen[str]] = {}
_PROCESSES_LOCK = threading.Lock()


def start_run(
    *,
    execution_id: int,
    prompt: str,
    workspace_root: str | None,
    model_override: str | None = None,
) -> None:
    """Launch Codex CLI in the background for an existing qa-browser execution."""
    thread = threading.Thread(
        target=_run_in_background,
        args=(execution_id,),
        kwargs={
            "prompt": prompt,
            "workspace_root": workspace_root,
            "model_override": model_override,
        },
        daemon=True,
        name=f"qa-browser-codex-{execution_id}",
    )
    thread.start()


def cancel(execution_id: int) -> bool:
    """Terminate a QA Browser Codex process if Stacky owns one."""
    with _PROCESSES_LOCK:
        proc = _PROCESSES.get(execution_id)
    if proc is None:
        return False
    _push(execution_id, "warn", "qa browser codex cancel requested", group="codex-browser")
    try:
        proc.terminate()
        return True
    except Exception as exc:  # noqa: BLE001
        _push(execution_id, "error", f"qa browser codex cancel failed: {exc}", group="codex-browser")
        return False


def _run_in_background(
    execution_id: int,
    *,
    prompt: str,
    workspace_root: str | None,
    model_override: str | None,
) -> None:
    started = datetime.utcnow()
    output_file: Path | None = None
    stdout_tail: list[str] = []
    return_code: int | None = None

    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                raise RuntimeError(f"execution_id={execution_id} not found")
            ticket_id = row.ticket_id
            agent_type = row.agent_type

        cwd = codex_cli_runner._resolve_cwd(workspace_root)  # package-local reuse
        run_dir = Path(__file__).resolve().parents[1] / "data" / "codex_runs" / str(execution_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        output_file = run_dir / "last_message.md"
        prompt_file = run_dir / "qa_browser_prompt.md"
        prompt_file.write_text(prompt, encoding="utf-8")

        cmd = codex_cli_runner._build_command(
            cwd=cwd,
            output_file=output_file,
            model_override=model_override,
        )
        _push(execution_id, "info", f"qa browser codex cwd={cwd}", group="codex-browser")
        _push(
            execution_id,
            "info",
            "qa browser codex command: " + codex_cli_runner._display_command(cmd),
            group="codex-browser",
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
        )
        with _PROCESSES_LOCK:
            _PROCESSES[execution_id] = proc
        _push(execution_id, "info", f"qa browser codex process started pid={proc.pid}", group="codex-browser")

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

        codex_cli_runner._write_prompt_to_stdin(execution_id, proc, prompt)

        return_code = proc.wait()
        for reader in readers:
            reader.join(timeout=5)

        duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
        output = codex_cli_runner._read_output(output_file, stdout_tail)
        metadata = {
            "runtime": RUNTIME,
            "workspace_root": str(cwd),
            "codex_cli_bin": cmd[0],
            "codex_model": model_override or config.CODEX_CLI_MODEL or None,
            "exit_code": return_code,
            "duration_ms": duration_ms,
            "output_file": str(output_file),
            "prompt_file": str(prompt_file),
        }

        terminal = _mark_terminal_if_needed(
            execution_id,
            return_code=return_code,
            output=output,
            metadata=metadata,
        )
        if terminal is None:
            _push(
                execution_id,
                "info",
                f"qa browser codex finished after Stacky completion ({duration_ms}ms)",
                group="codex-browser",
            )
            return

        status, error = terminal
        if status == "error":
            _push(execution_id, "error", error or "qa browser codex failed", group="codex-browser")
        ticket_status.on_execution_end(
            ticket_id=ticket_id,
            execution_id=execution_id,
            final_status=status,
            agent_type=agent_type,
            error=error,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("[exec=%s] qa browser codex runtime failed", execution_id)
        _push(execution_id, "error", f"qa browser codex runtime failed: {exc}", group="codex-browser")
        terminal = _mark_terminal_if_needed(
            execution_id,
            return_code=return_code if return_code is not None else -1,
            output=None,
            metadata={"runtime": RUNTIME},
            forced_error=str(exc),
        )
        if terminal is not None:
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
                logger.exception("could not mark ticket status after qa browser codex failure")
    finally:
        with _PROCESSES_LOCK:
            _PROCESSES.pop(execution_id, None)
        log_streamer.close(execution_id)


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
        message, level = codex_cli_runner._summarize_codex_line(line, default_level)
        _push(execution_id, level, message, group=group)
        tail.append(message)
        if len(tail) > 200:
            del tail[:50]


def _mark_terminal_if_needed(
    execution_id: int,
    *,
    return_code: int,
    output: str | None,
    metadata: dict[str, Any],
    forced_error: str | None = None,
) -> tuple[str, str | None] | None:
    """Mark the execution terminal only if /complete has not already done it."""
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return ("error", f"execution_id={execution_id} not found")
        if row.status in {"completed", "error", "cancelled"}:
            md = row.metadata_dict
            md.update(metadata)
            row.metadata_dict = md
            return None

        error = forced_error
        if error is None:
            if return_code == 0:
                error = "Codex finalizo sin llamar al endpoint /complete del run QA Browser."
            else:
                error = f"Codex QA Browser salio con codigo {return_code}."

        md = row.metadata_dict
        md.update(metadata)
        md["runtime"] = RUNTIME
        row.metadata_dict = md
        row.output = output
        row.output_format = "markdown"
        row.status = "error"
        row.error_message = error
        row.completed_at = datetime.utcnow()
        return ("error", error)


def _push(
    execution_id: int,
    level: str,
    message: str,
    group: str | None = None,
) -> None:
    log_streamer.push(execution_id, level, message, group=group)
    backend_level = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }.get(level, logging.INFO)
    logger.log(backend_level, "[exec=%s] %s", execution_id, message)
