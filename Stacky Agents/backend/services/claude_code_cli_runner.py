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
    effort_override: str | None = None,
    work_item_type: str = "Epic",
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
            "work_item_type": work_item_type,
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
            "effort_override": effort_override,
            "work_item_type": work_item_type,
        },
        daemon=True,
        name=f"claude-code-cli-{execution_id}",
    )
    thread.start()
    return execution_id


# R1.2 — Tickets pool cuyos runs son ONE-SHOT (sin consola conversacional):
# apenas llega el `result` terminal se cierra stdin y la sesión sale limpia.
#   -1 = brief→épica (comportamiento histórico)
#   -7 = Documentador (plan 113, doc_documenter._CONVERSATION_ADO_ID): pipeline
#        autónomo en background — nadie responde por consola; sin esto el
#        proceso quedaba vivo esperando input del operador y el run del
#        Documentador se colgaba hasta el timeout (1800s).
#   -8 = Incident Pool (Plan 131 C14, resolutor de incidencias): mismo patrón,
#        el agente unificado corre en background sin consola conversacional.
# Las consolas multi-turno reales (-3 doctor, -4 DevOps, -5 remota, -6 PRs y
# tickets positivos) NO van acá: siguen conversacionales.
_ONE_SHOT_ADO_IDS = frozenset({-1, -7, -8})


def _is_one_shot(t_ado_id) -> bool:
    """True si el ticket pool corre en modo one-shot (cerrar al primer result)."""
    return t_ado_id in _ONE_SHOT_ADO_IDS


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


def _stderr_excerpt(stderr_tail: list[str], *, max_lines: int = 40) -> str:
    """Plan 37 (F2.2) — últimas N líneas de stderr del proceso `claude`, limpias.

    El motivo real de un `exit != 0` (flag no soportada, error de MCP/tool, etc.)
    queda en stderr; lo extraemos para persistirlo y dejar de "fallar en silencio".
    """
    if not stderr_tail:
        return ""
    return "\n".join(stderr_tail[-max_lines:]).strip()


def _format_cli_error(return_code: int | None, stderr_excerpt: str) -> str:
    """Mensaje de error persistible: genérico + extracto de stderr si lo hay."""
    base = f"claude code cli exited with code {return_code}"
    if stderr_excerpt:
        return f"{base}: {stderr_excerpt[:500]}"
    return base


# ── Fallback sonnet-5 → sonnet-4-6 en el spawn ───────────────────────────────
# El operador fijó sonnet-5 como modelo PRIMARIO del CLI (config.CLAUDE_CODE_CLI_MODEL,
# nuevo default) con sonnet-4-6 como FALLBACK (config.CLAUDE_CODE_CLI_MODEL_FALLBACK):
# si el binario `claude` rechaza --model (versión vieja del CLI sin soporte para
# sonnet-5 todavía, typo de configuración, etc.) el runner reintenta UNA vez con
# el fallback antes de darse por vencido. Ambos intentos quedan logueados.
_MODEL_FAILURE_GRACE_SEC = 2.0
_MODEL_FAILURE_PATTERNS = (
    "unknown model",
    "invalid model",
    "model not found",
    "no such model",
    "unsupported model",
    "unrecognized model",
    "not a valid model",
    "model_not_found",
    "does not exist",
)


def _looks_like_model_error(stderr_text: str) -> bool:
    """Heurística: ¿el stderr sugiere que el CLI rechazó --model?

    No hay contrato documentado del mensaje real del binario `claude`, así que
    esto es best-effort (ver docstring del módulo, supuesto §6). Un exit-code
    != 0 dentro de la ventana de gracia YA dispara el reintento en
    `_spawn_claude_with_fallback` aunque este helper no matchee nada — el
    matching solo enriquece el log, no es la condición de reintento.
    """
    low = (stderr_text or "").lower()
    return any(p in low for p in _MODEL_FAILURE_PATTERNS)


def _spawn_claude_with_fallback(
    *,
    primary_model: str,
    fallback_model: str | None,
    build_cmd,
    cwd,
    creationflags: int,
    env: dict,
    log,
) -> tuple[subprocess.Popen, list[str], str]:
    """Lanza `claude` con `primary_model`; si falla rápido, reintenta con `fallback_model`.

    "Falla rápido" = el proceso termina (poll() != None) dentro de
    `_MODEL_FAILURE_GRACE_SEC` desde el spawn. Un run real de Claude Code nunca
    termina en <2s (el turno tarda segundos/minutos), así que una salida dentro
    de esa ventana es atribuible al spawn/modelo (CLI rechaza --model, error de
    spawn, etc.), no a un turno legítimo corto.

    Se reintenta A LO SUMO UNA VEZ (primary → fallback, nunca un loop). El
    `proc` del ÚLTIMO intento disponible se devuelve SIEMPRE tal cual —
    vivo o ya muerto — sin que este helper toque sus streams: si hasta el
    fallback falla, el manejo de exit-code/stderr preexistente aguas abajo
    (que lee proc.stdout/stderr en threads propios) sigue cubriendo ese caso
    exactamente igual que antes de este cambio. Solo se hace un `communicate()`
    (para loguear el motivo) sobre los intentos INTERMEDIOS que se descartan.

    Devuelve (proc, cmd_usado, modelo_efectivo).
    """
    attempts = [primary_model]
    if fallback_model and fallback_model != primary_model:
        attempts.append(fallback_model)

    for i, model in enumerate(attempts):
        is_last_attempt = i == len(attempts) - 1
        cmd = build_cmd(model)
        log("info", f"claude code cli intento {i + 1}/{len(attempts)} con modelo {model!r}")
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
            env=env,
        )

        if is_last_attempt:
            # Nada más para reintentar: se devuelve tal cual (vivo o no) y el
            # manejo de error preexistente hace su trabajo si murió.
            return proc, cmd, model

        deadline = time.time() + _MODEL_FAILURE_GRACE_SEC
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.05)

        if proc.poll() is None:
            # Sigue vivo pasada la ventana de gracia: arranque exitoso.
            return proc, cmd, model

        # Terminó dentro de la ventana de gracia y hay fallback disponible:
        # se descarta este proceso (nadie más va a leer sus streams) y se
        # reintenta con el siguiente modelo de la lista.
        try:
            _, err_text = proc.communicate(timeout=2)
        except Exception:  # noqa: BLE001 — ya está muerto, best-effort
            err_text = ""
        rc = proc.returncode
        model_error = _looks_like_model_error(err_text)
        log(
            "warn",
            f"claude code cli terminó de inmediato con modelo {model!r} (rc={rc}, "
            f"¿error de modelo?={model_error}); reintentando con fallback {attempts[i + 1]!r}",
        )

    # Inalcanzable: el loop siempre retorna en la última iteración (is_last_attempt).
    raise RuntimeError("_spawn_claude_with_fallback: no se pudo lanzar claude con ningún modelo")


def _classify_run_outcome(
    *, stall_fired: bool, result_ok_seen: bool, return_code: int | None
) -> str:
    """R1.2 — Clasifica el desenlace de un run claude_code_cli.

    - ``success``: salida limpia (rc==0) o el agente emitió un ``result``
      terminal exitoso (one-shot cerrado, o stall/terminate tras entregar
      trabajo: la sesión solo quedó ociosa, el trabajo ya estaba hecho).
    - ``failed_stall``: el watchdog disparó SIN un result ok → cuelgue real.
    - ``error``: exit code != 0 sin result ok → fallo del propio CLI.
    """
    if stall_fired and not result_ok_seen:
        return "failed_stall"
    if return_code == 0 or result_ok_seen:
        return "success"
    return "error"


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


def _send_system_message(execution_id: int, text: str) -> bool:
    """Escribe un mensaje originado por Stacky (no el operador) al stdin vivo.

    Lo usa el loop de autocorrección (F1.3). Retorna False si el proceso ya no
    acepta stdin — nunca lanza (la autocorrección no debe tumbar el run).
    """
    with _PROCESSES_LOCK:
        proc = _PROCESSES.get(execution_id)
    if proc is None or proc.poll() is not None:
        return False
    if proc.stdin is None or proc.stdin.closed:
        return False
    lock = _STDIN_LOCKS.setdefault(execution_id, threading.Lock())
    with lock:
        try:
            proc.stdin.write(_user_message_line(text))
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            return False
    _push(
        execution_id,
        "info",
        f"stacky → claude (autocorrección): {text[:2000]}",
        group="operator",
    )
    return True


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
    effort_override: str | None = None,
    work_item_type: str = "Epic",
) -> None:
    started = datetime.utcnow()

    def log(level: str, message: str, group: str | None = None, indent: int = 0) -> None:
        _push(execution_id, level, message, group=group, indent=indent)

    output_file: Path | None = None
    prompt_file: Path | None = None
    run_dir: Path | None = None
    hooks_settings_file: Path | None = None
    stdout_tail: list[str] = []
    # Plan 37 (F2.1) — tail de stderr AISLADO: el motivo real de un exit!=0 vive
    # en stderr; lo persistimos en la rama de error para no "fallar en silencio".
    stderr_tail: list[str] = []
    return_code: int | None = None
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    agent_type: str | None = None
    ticket_id: int | None = None
    mask_map: dict[str, str] = {}
    knowledge_meta: dict[str, Any] = {}

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

        cwd, _cwd_fallback = _resolve_cwd(workspace_root)
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
        # Q0.1/Q1.2 — registrar qué bloques de calidad fueron inyectados para Q2.2.
        _enriched_ids = {b.get("id") for b in enriched_blocks if isinstance(b, dict)}
        _ac_injected = "acceptance-criteria" in _enriched_ids
        _fewshot_count = sum(
            1 for b in enriched_blocks
            if isinstance(b, dict) and b.get("id") == "few-shot-approved"
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
        project_name = project_ctx.stacky_project_name if project_ctx else None
        # Plan 54 F2 — inicializar vars de memory_prefix (solo se populan en rama "append").
        _mem_prefix_claude: str = ""
        _mem_meta_claude: dict = {}
        if system_prompt_mode == "append":
            knowledge_section, knowledge_meta = _build_project_knowledge(
                agent_type=agent_type or "",
                project_name=project_name,
                context_text=rich_message,
                log=log,
            )
            # H4.3 — Stacky Skills injection (ANTES de _STACKY_RULES).
            skills_block = ""
            try:
                from services.cli_feature_flags import skills_enabled  # noqa: PLC0415
                from services import stacky_skills  # noqa: PLC0415
                if skills_enabled(project_name):
                    _mcp_active = getattr(config, "CLAUDE_CODE_CLI_MCP_ENABLED", False) and bool(
                        project_name
                    )
                    matched = stacky_skills.select_for_run(
                        agent_type=agent_type or "",
                        project=project_name,
                        context_text=rich_message,
                        max_skills=3,
                    )
                    if matched:
                        index_text = stacky_skills.render_index(matched)
                        if _mcp_active:
                            # Solo índice + instrucción de pedir el cuerpo via tool.
                            skills_block = (
                                "## Stacky Skills disponibles\n\n"
                                + index_text
                                + "\n\nPara obtener el procedimiento completo de una skill "
                                "usá la tool `stacky_get_skill` con el nombre exacto."
                            )
                        else:
                            # Cuerpo del top-1 skill con cap.
                            top = matched[0]
                            skills_block = (
                                "## Stacky Skills disponibles\n\n"
                                + index_text
                                + f"\n\n### Skill activa: {top.name}\n\n"
                                + stacky_skills.cap_body(top.body)
                            )
                        log("info", f"H4: skills inyectadas ({len(matched)})", group="operator")
            except Exception as exc:  # noqa: BLE001
                log("warn", f"H4: no se pudo inyectar skills: {exc}")
            # Plan 54 F2 — inyección rejection_lessons en claude_code_cli (paridad FA-11).
            _mem_prefix_claude = ""
            _mem_meta_claude: dict = {}
            try:
                from services.memory_prefix import build_memory_prefix as _bmp_cli  # noqa: PLC0415
                _mem_prefix_claude, _mem_meta_claude = _bmp_cli(
                    project=project_name,
                    agent_type=agent_type or "",
                )
                if _mem_prefix_claude:
                    log("info", "Plan 54: rejection_lessons inyectadas en system prompt (CLI)", group="operator")
            except Exception as _exc_mp:  # noqa: BLE001
                log("warn", f"Plan 54: memory_prefix falló (no crítico): {_exc_mp}")
            system_prompt_text = _build_system_prompt(
                selected_agent,
                invocation_block=invocation_block,
                project_knowledge=knowledge_section,
                skills_section=skills_block,
            )
            if _mem_prefix_claude:
                system_prompt_text = (_mem_prefix_claude.strip() + "\n\n" + system_prompt_text).strip()
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

        # F1.4 — settings.json efímero con hook PostToolUse de validación de
        # artifacts. Solo hooks; no toca permisos (decisión §5.3). Flag OFF default.
        if config.CLAUDE_CODE_CLI_HOOKS_ENABLED:
            try:
                from services import claude_cli_hooks

                hooks_settings_file = claude_cli_hooks.write_run_settings(
                    run_dir, port=config.PORT
                )
                log(
                    "info",
                    "hook de validación de artifacts generado (--settings efímero, F1.4)",
                )
            except Exception as exc:  # noqa: BLE001 — el hook nunca bloquea el run
                log("warn", f"no se pudo generar el settings.json de hooks: {exc}")
                hooks_settings_file = None

        # F2.1 — Stacky MCP server (--mcp-config). Por proyecto, OFF default.
        mcp_config_file: Path | None = None
        try:
            from services import stacky_mcp

            mcp_config_file = stacky_mcp.maybe_write_mcp_config(
                run_dir,
                project_name=project_name,
                ticket_id=ticket_id,
                ado_id=t_ado_id,
                execution_id=execution_id,
                port=config.PORT,
            )
            if mcp_config_file is not None:
                log("info", "Stacky MCP server inyectado (--mcp-config, F2.1)")
        except Exception as exc:  # noqa: BLE001 — el MCP nunca bloquea el run
            log("warn", f"no se pudo generar el mcp-config (continuando sin MCP): {exc}")
            mcp_config_file = None

        # F2.3 — re-run con --resume + delta prompt (por proyecto, OFF default).
        resume_session_id, delta_prefix = _resolve_resume(
            execution_id=execution_id,
            ticket_id=ticket_id,
            agent_type=agent_type,
            project_name=project_name,
            current_blocks=enriched_blocks,
            log=log,
        )
        if delta_prefix:
            prompt = delta_prefix + "\n\n" + prompt

        # F3.2 / §5.2 — routing de modelo OBLIGATORIO también en el CLI.
        # El runtime CLI corre SIEMPRE modelos Claude, así que routeamos con
        # backend="anthropic" sin importar LLM_BACKEND (que es del path copilot).
        # decide() aplica el cap duro (clamp_model): jamás opus/fable, ni por override.
        from services import llm_router

        # I0.2 — Cómputo de fingerprint_complexity en el CLI.
        # Solo se calcula si el flag está ON. OFF → None (routing byte-idéntico).
        _cli_complexity: str | None = None
        if config.STACKY_COMPLEXITY_ESTIMATION_ENABLED:
            try:
                from harness.complexity import estimate_complexity as _est_c
                _cli_title = ""
                _cli_desc = ""
                try:
                    from db import session_scope as _ss
                    from models import Ticket as _Ticket
                    with _ss() as _sess_c:
                        _tobj = _sess_c.get(_Ticket, ticket_id)
                        if _tobj is not None:
                            _cli_title = _tobj.title or ""
                            _cli_desc = _tobj.description or ""
                except Exception:
                    pass
                _cli_complexity = _est_c(
                    agent_type=agent_type or "",
                    ticket_title=_cli_title,
                    ticket_description=_cli_desc,
                    blocks=enriched_blocks,
                )
                log("info", f"complexity estimation → {_cli_complexity} (I0.2)")
            except Exception as _exc_c:  # noqa: BLE001
                log("warn", f"complexity estimation falló (no crítico): {_exc_c}")

        routed_model = model_override or config.CLAUDE_CODE_CLI_MODEL
        try:
            decision = llm_router.decide(
                agent_type=agent_type or "",
                blocks=enriched_blocks,
                fingerprint_complexity=_cli_complexity,
                # El default fijo del operador (CLAUDE_CODE_CLI_MODEL, sonnet-4-6)
                # actúa como override del router: TODA invocación CLI usa ese
                # modelo salvo override explícito por-run. Vacío = router decide.
                override=model_override or (config.CLAUDE_CODE_CLI_MODEL or None),
                backend="anthropic",
                project_name=project_name,
            )
            routed_model = decision.model
            log("info", f"router → {decision.model} ({decision.reason})")
        except Exception as exc:  # noqa: BLE001 — el routing nunca bloquea el run
            # Fallback: cap duro igual aplicado sobre el modelo estático/override.
            routed_model = llm_router.clamp_model(routed_model)
            log("warn", f"router falló, usando modelo {routed_model}: {exc}")

        # H3.3 — Egress check antes del spawn (STACKY_CLI_EGRESS_ENABLED, OFF default).
        egress_decision = _check_cli_egress(
            prompt=prompt,
            project=project_name,
            model=routed_model or "",
        )
        if egress_decision is not None and not egress_decision.allowed:
            reason = egress_decision.reason
            log("error", f"egress bloqueado antes de spawn claude: {reason}")
            with session_scope() as s:
                row = s.query(AgentExecution).filter(AgentExecution.id == execution_id).first()
                if row:
                    row.status = "error"
                    row.output = f"[egress] run bloqueado: {reason}"
            return

        # Q0.2 — Esfuerzo adaptativo por dificultad estimada (OFF default).
        # effort_override explícito (ej: "high" para briefs) tiene prioridad.
        _adaptive_effort = _map_effort(_cli_complexity)
        if _adaptive_effort:
            log("info", f"adaptive effort → {_adaptive_effort} (complexity={_cli_complexity}, Q0.2)")
        _effective_effort = effort_override or _adaptive_effort
        if effort_override:
            log("info", f"effort_override explícito → {effort_override} (prioridad sobre adaptativo)")

        def _build_cli_command(model_for_attempt: str) -> list[str]:
            return _build_command(
                model_override=model_for_attempt,
                system_prompt_file=system_prompt_file,
                settings_file=hooks_settings_file,
                mcp_config_file=mcp_config_file,
                resume_session_id=resume_session_id,
                effort_override=_effective_effort,
            )

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        # Cap de sesión (segundos). 0 = ilimitado: la sesión interactiva vive
        # hasta que el operador la cierra/cancela o Claude termina por su cuenta.
        session_timeout = config.CLAUDE_CODE_CLI_TIMEOUT if config.CLAUDE_CODE_CLI_TIMEOUT > 0 else None

        # Primario sonnet-5 (routed_model) con fallback a
        # config.CLAUDE_CODE_CLI_MODEL_FALLBACK (sonnet-4-6 por default) si el
        # CLI rechaza el primero casi de inmediato (spawn error, --model
        # inválido, etc.). Ver _spawn_claude_with_fallback.
        proc, cmd, _effective_model = _spawn_claude_with_fallback(
            primary_model=routed_model or "",
            fallback_model=(config.CLAUDE_CODE_CLI_MODEL_FALLBACK or None),
            build_cmd=_build_cli_command,
            cwd=cwd,
            creationflags=creationflags,
            env=build_agent_env(extra={"STACKY_EXECUTION_ID": str(execution_id)}),
            log=log,
        )
        if _effective_model != routed_model:
            log(
                "warn",
                f"claude code cli usó el modelo fallback {_effective_model!r} "
                f"(primario {routed_model!r} no arrancó)",
            )
        routed_model = _effective_model

        log("info", f"claude code cli cwd={cwd}")
        log("info", "claude code cli command: " + _display_command(cmd))
        log(
            "info",
            f"loaded {len(all_agents)} Stacky agent prompt(s); selected {selected_agent.filename}",
        )

        spawn_epoch = time.time()
        log("info", f"claude code cli process started pid={proc.pid}")
        with _PROCESSES_LOCK:
            _PROCESSES[execution_id] = proc

        # F1.2 (sub-ítem §5.1) — repro.ps1: comando exacto + env para reproducir
        # el run a mano al debuggear. Best-effort, nunca bloquea el run.
        try:
            _write_repro_script(
                run_dir,
                cmd=cmd,
                cwd=cwd,
                execution_id=execution_id,
                initial_message=prompt,
            )
        except Exception:  # noqa: BLE001
            logger.debug("[exec=%s] repro.ps1 write failed", execution_id, exc_info=True)

        # Enviar el prompt inicial como primer mensaje de usuario (stream-json).
        # NO cerramos stdin: queda abierto para que el operador responda desde la
        # consola in-page (send_input).
        try:
            proc.stdin.write(_user_message_line(prompt))
            proc.stdin.flush()
            log("info", f"prompt inicial enviado a claude por stdin ({len(prompt)} chars)", group="operator")
            log("info", _prompt_echo_message(prompt, pii_masked=bool(mask_map)), group="operator")
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

        # F1.2 — telemetría nativa del stream (session_id, usage, costo, turnos)
        stream_telemetry: dict[str, Any] = {}
        last_telemetry_emit = 0.0

        # F1.3 — loop de autocorrección sobre stdin (flag OFF default).
        autocorrect = None
        if config.CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED and t_ado_id:
            from services.cli_autocorrect import AutocorrectLoop

            autocorrect = AutocorrectLoop(
                ado_id=int(t_ado_id),
                max_retries=config.CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES,
                send=lambda text: _send_system_message(execution_id, text),
                log=log,
                since_epoch=spawn_epoch,
            )
            log("info", "autocorrección de artifacts habilitada (F1.3)")

        # Q1.1 — pase correctivo de criterios incumplidos (flag OFF default).
        _criteria_repair_result: list[dict | None] = [None]   # [0] = meta o None
        _criteria_repair_done: list[bool] = [False]           # flag mutable para closure

        # Fix robusto brief→épica — pase correctivo de épica (flag ON default).
        # Si el BusinessAgent one-shot narra en vez de emitir el HTML de la épica,
        # le pedimos UNA vez por stdin que re-emita SOLO el HTML antes de cerrar.
        _epic_repair_result: list[dict | None] = [None]       # [0] = meta o None
        _epic_repair_done: list[bool] = [False]               # flag mutable para closure

        # Plan 160 F0 — pase correctivo del resolutor de incidencias (flag ON
        # default). Espejo de _epic_repair_result/_epic_repair_done, gateado
        # por agent_type=="incident" en vez de "business".
        _incident_repair_result: list[dict | None] = [None]
        _incident_repair_done: list[bool] = [False]

        # H5 — Runaway guard: límite de turnos y costo por run.
        from harness.runaway_guard import RunLimits, RunawayGuard
        _runaway_guard = RunawayGuard(
            RunLimits(
                max_turns=config.STACKY_RUNAWAY_MAX_TURNS,
                max_cost_usd=config.STACKY_RUNAWAY_MAX_COST_USD,
            )
        )
        _runaway_triggered: list[str] = []  # [0] = razón si se disparó

        # R1.1 — stall watchdog: rastrea el ultimo evento del stream.
        _last_event_wall: list[datetime] = [datetime.utcnow()]
        _last_event_mono: list[float] = [time.monotonic()]
        _stall_fired: list[bool] = [False]
        # Plan 144 F4 — último tipo de señal del stream (diagnóstico de stall).
        _last_event_kind: list[str] = ["none"]
        # R1.2 — ¿el agente emitió un `result` terminal exitoso? Si sí, el run
        # completó su trabajo aunque después la sesión quede ociosa.
        _result_ok_seen: list[bool] = [False]
        # R1.2 — run de un solo turno (pool tickets sintéticos: brief→épica
        # ado_id=-1, Documentador ado_id=-7, resolutor de incidencias Plan 131
        # ado_id=-8): no hay consola conversacional, así que cerramos stdin
        # apenas llega el result terminal para salir limpio sin esperar al
        # watchdog ni al operador.
        _one_shot = _is_one_shot(t_ado_id)

        def _on_stream_event(event: dict) -> None:
            nonlocal last_telemetry_emit
            _last_event_wall[0] = datetime.utcnow()
            _last_event_mono[0] = time.monotonic()
            # Plan 144 F4 — última señal conocida (diagnóstico humano del stall).
            etype = event.get("type") or "unknown"
            if etype == "assistant":
                _last_event_kind[0] = "assistant_text"
            elif etype == "tool_use" or event.get("name"):
                _last_event_kind[0] = f"tool_use:{event.get('name') or '?'}"
            else:
                _last_event_kind[0] = etype
            _capture_result_telemetry(stream_telemetry, event)
            # R1.2 — un `result` terminal sin is_error = el agente entregó su
            # trabajo. Lo recordamos para clasificar bien un stall posterior y
            # para cerrar la sesión one-shot.
            if event.get("type") == "result":
                _result_ok_seen[0] = not bool(event.get("is_error"))
            if config.STACKY_LIVE_TELEMETRY_ENABLED:
                now = time.monotonic()
                if now - last_telemetry_emit >= 2.0:
                    usage = stream_telemetry.get("usage") if isinstance(stream_telemetry.get("usage"), dict) else {}
                    telemetry_payload = {
                        "turns": stream_telemetry.get("num_turns"),
                        "input_tokens": usage.get("input_tokens") if isinstance(usage, dict) else None,
                        "output_tokens": usage.get("output_tokens") if isinstance(usage, dict) else None,
                        "cost_usd": stream_telemetry.get("total_cost_usd"),
                        "cost_estimated": False,
                    }
                    if any(v is not None for v in telemetry_payload.values()):
                        log_streamer.push(
                            execution_id,
                            "info",
                            "telemetry",
                            group="telemetry",
                            event_type="telemetry",
                            data=telemetry_payload,
                        )
                        last_telemetry_emit = now
            # Fin de turno = evento `result`: validar artifacts y, si están
            # inválidos, pedir corrección por el stdin todavía abierto.
            if autocorrect is not None and event.get("type") == "result":
                autocorrect.on_turn_end()
            # Q1.1 — pase correctivo de criterios incumplidos (último turno,
            # solo una vez, después de que autocorrect haya terminado su ciclo).
            if (
                not _criteria_repair_done[0]
                and event.get("type") == "result"
                and getattr(config, "STACKY_CRITERIA_REPAIR_ENABLED", False)
            ):
                _criteria_repair_done[0] = True
                try:
                    from harness.criteria_repair import attempt_criteria_repair as _acr
                    _ac_retries_used = (
                        autocorrect.attempts if autocorrect is not None else 0
                    )
                    _ac_budget = config.CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES
                    _current_output = "\n".join(final_output) if final_output else ""
                    _cr = _acr(
                        execution_id=execution_id,
                        artifact_text=_current_output,
                        runtime=RUNTIME,
                        retries_budget=_ac_budget,
                        retries_used=_ac_retries_used,
                        send_fn=lambda msg: _send_system_message(execution_id, msg),
                        enabled=True,
                        min_score=float(config.STACKY_SELF_REVIEW_MIN_SCORE),
                    )
                    _criteria_repair_result[0] = _cr
                    if _cr is not None:
                        log("info", f"criteria_repair: {_cr} (Q1.1)")
                except Exception as _exc_cr:  # noqa: BLE001
                    log("warn", f"criteria_repair falló (no crítico): {_exc_cr}")
            # Fix robusto brief→épica — pase correctivo de épica (último turno,
            # solo una vez, stdin todavía abierto). Si el BusinessAgent one-shot
            # devolvió narración en vez del HTML de la épica, le pedimos UNA vez
            # que re-emita SOLO el HTML. Reusa _send_system_message como Q1.1.
            if (
                not _epic_repair_done[0]
                and event.get("type") == "result"
                and getattr(config, "STACKY_EPIC_REPAIR_ENABLED", False)
                and _one_shot
                and (agent_type or "").lower() == "business"
            ):
                _epic_repair_done[0] = True
                try:
                    from api.tickets import (
                        _extract_epic_html, _looks_like_epic,
                        _epic_grounding_warnings, _epic_gate_enabled,
                    )
                    # Plan 58 F2 — bucle de convergencia de calidad (cuando flag ON).
                    if (
                        getattr(config, "STACKY_QUALITY_CONVERGENCE_ENABLED", False)
                        and _epic_gate_enabled()
                    ):
                        from harness.convergence import (
                            run_convergence_loop, build_convergence_payload,
                        )
                        from harness.epic_gate import evaluate_epic_gate, GateDecision

                        def _current_clean_58() -> str:
                            _txt = "\n".join(final_output) if final_output else ""
                            return _extract_epic_html(_txt)

                        def _evaluate_58():
                            _clean58 = _current_clean_58()
                            return evaluate_epic_gate(
                                clean_html=_clean58,
                                structural_warnings=_epic_grounding_warnings(_clean58),
                                process_catalog=None,
                                catalog_blocking_enabled=False,
                                looks_like_epic_fn=_looks_like_epic,
                            )

                        def _build_msg_58(verdict) -> str:
                            base = (
                                "Tu último mensaje no cumple el contrato de la épica. "
                                "Re-emití AHORA, como único contenido del mensaje, "
                                "EXCLUSIVAMENTE el HTML de la épica dentro de un único "
                                "bloque ```html ... ```: <h1> con el título, el resumen "
                                "ejecutivo y los bloques <hr><h2>RF-XXX consecutivos y SIN "
                                "duplicados ni headings vacíos. SIN narración, SIN preámbulo, "
                                "SIN escribirla en un archivo."
                            )
                            if verdict.structural_defects:
                                base += "\nDefectos detectados: " + ", ".join(verdict.structural_defects) + "."
                            return base

                        # C2 — budget compartido con el cap de autocorrección.
                        _ac_used_58 = autocorrect.attempts if autocorrect is not None else 0
                        _ac_cap_58 = int(config.CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES)
                        _cfg_cap_58 = max(1, int(config.STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS))
                        _budget_58 = min(_cfg_cap_58, _ac_cap_58 - _ac_used_58)
                        _initial_58 = _evaluate_58()
                        _conv_58 = run_convergence_loop(
                            enabled=True,
                            runtime=RUNTIME,
                            max_iterations=_budget_58,
                            initial_verdict=_initial_58,
                            build_repair_message=_build_msg_58,
                            send_fn=lambda m: _send_system_message(execution_id, m),
                            reextract_and_evaluate_fn=_evaluate_58,
                        )
                        _epic_repair_result[0] = build_convergence_payload(_conv_58)
                        log("info", f"convergence: {_epic_repair_result[0]}")
                    else:
                        # Rama legacy (flag OFF o gate OFF): single-shot original.
                        _current_output = "\n".join(final_output) if final_output else ""
                        _clean = _extract_epic_html(_current_output)
                        # Plan 51 F3 — si el gate está ON, decide REPAIR por cualquier
                        # defecto reparable (no solo narración). El runner solo repara
                        # FORMA (catálogo se chequea en autopublish). Si el gate está
                        # OFF, conserva el disparador histórico (not _looks_like_epic).
                        _needs_repair = not _looks_like_epic(_clean)
                        _repair_reason = "narration_not_epic"
                        _gate_defects: list[str] = []
                        if _epic_gate_enabled():
                            try:
                                from harness.epic_gate import evaluate_epic_gate, GateDecision
                                _verdict = evaluate_epic_gate(
                                    clean_html=_clean,
                                    structural_warnings=_epic_grounding_warnings(_clean),
                                    process_catalog=None,
                                    catalog_blocking_enabled=False,
                                    looks_like_epic_fn=_looks_like_epic,
                                )
                                _gate_defects = list(_verdict.structural_defects)
                                if _verdict.decision == GateDecision.REPAIR:
                                    _needs_repair = True
                                    _repair_reason = f"gate_repair:{_gate_defects}"
                            except Exception:  # noqa: BLE001
                                pass
                        if _needs_repair:
                            _ac_used = autocorrect.attempts if autocorrect is not None else 0
                            _ac_budget = config.CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES
                            if _ac_used < _ac_budget:
                                _EPIC_REPAIR_MSG = (
                                    "Tu último mensaje no cumple el contrato de la épica. "
                                    "Re-emití AHORA, como único contenido del mensaje, "
                                    "EXCLUSIVAMENTE el HTML de la épica dentro de un único "
                                    "bloque ```html ... ```: <h1> con el título, el resumen "
                                    "ejecutivo y los bloques <hr><h2>RF-XXX consecutivos y SIN "
                                    "duplicados ni headings vacíos. SIN narración, SIN preámbulo, "
                                    "SIN escribirla en un archivo."
                                )
                                _sent = _send_system_message(execution_id, _EPIC_REPAIR_MSG)
                                _epic_repair_result[0] = {
                                    "attempted": True,
                                    "reason": _repair_reason,
                                    "sent": bool(_sent),
                                }
                                log("info", f"epic_repair: reintento solicitado (sent={_sent}, reason={_repair_reason})")
                            else:
                                _epic_repair_result[0] = {
                                    "attempted": False,
                                    "reason": _repair_reason,
                                    "budget_exhausted": True,
                                }
                except Exception as _exc_er:  # noqa: BLE001
                    log("warn", f"epic_repair falló (no crítico): {_exc_er}")
            # Plan 160 F0 — pase correctivo del resolutor de incidencias
            # (último turno, solo una vez, stdin todavía abierto). Si el
            # IncidentAgent one-shot devolvió narración en vez del HTML del
            # desglose, le pedimos UNA vez que re-emita SOLO el HTML.
            if (
                not _incident_repair_done[0]
                and event.get("type") == "result"
                and getattr(config, "STACKY_INCIDENT_REPAIR_ENABLED", False)
                and _one_shot
                and (agent_type or "").lower() == "incident"
            ):
                _incident_repair_done[0] = True
                try:
                    from api.tickets import _extract_epic_html_raw, _looks_like_incident

                    _current_output_inc = "\n".join(final_output) if final_output else ""
                    _clean_inc = _extract_epic_html_raw(_current_output_inc)
                    if not _looks_like_incident(_clean_inc):
                        _ac_used_inc = autocorrect.attempts if autocorrect is not None else 0
                        _ac_budget_inc = config.CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES
                        if _ac_used_inc < _ac_budget_inc:
                            _INCIDENT_REPAIR_MSG = (
                                "Tu último mensaje no cumple el contrato del desglose de "
                                "incidencia. Re-emití AHORA, como único contenido del "
                                "mensaje, EXCLUSIVAMENTE el HTML del desglose con las "
                                "secciones RESUMEN EJECUTIVO, CONTEXTO DE NEGOCIO, ANALISIS "
                                "FUNCIONAL, ANALISIS TECNICO, PASOS DE REPRODUCCION, "
                                "CRITERIOS DE ACEPTACION, ARCHIVOS Y MODULOS PROBABLES, "
                                "EPICA RELACIONADA, PRIORIDAD Y ESTIMACION. SIN narración, "
                                "SIN preámbulo, SIN escribirlo en un archivo."
                            )
                            _sent_inc = _send_system_message(execution_id, _INCIDENT_REPAIR_MSG)
                            _incident_repair_result[0] = {
                                "attempted": True,
                                "reason": "narration_not_incident",
                                "sent": bool(_sent_inc),
                            }
                            log("info", f"incident_repair: reintento solicitado (sent={_sent_inc})")
                        else:
                            _incident_repair_result[0] = {
                                "attempted": False,
                                "reason": "narration_not_incident",
                                "budget_exhausted": True,
                            }
                            log("info", "incident_repair: presupuesto agotado, no se reintenta")
                except Exception as _exc_ir:  # noqa: BLE001
                    log("warn", f"incident_repair falló (no crítico): {_exc_ir}")
            # H5 — chequear runaway en cada evento con datos de telemetría.
            if not _runaway_triggered:
                reason = _runaway_guard.observe(
                    num_turns=stream_telemetry.get("num_turns"),
                    cost_usd=stream_telemetry.get("total_cost_usd"),
                )
                if reason:
                    _runaway_triggered.append(reason)

        readers = [
            threading.Thread(
                target=_read_stream,
                args=(execution_id, proc.stdout, "info", "claude-code", stdout_tail, final_output),
                kwargs={"on_event": _on_stream_event},
                daemon=True,
            ),
            threading.Thread(
                target=_read_stream,
                args=(execution_id, proc.stderr, "warn", "claude-code-stderr", stderr_tail, None),
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
        _runaway_grace_deadline: float | None = None
        _one_shot_close_deadline: float | None = None
        stall_watchdog_sec = config.STACKY_STALL_WATCHDOG_SECONDS
        while True:
            try:
                return_code = proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                # H5 — Runaway: si el guard disparó, enviar señal de cierre
                # y esperar gracia de 60s antes de terminate.
                if _runaway_triggered and _runaway_grace_deadline is None:
                    reason = _runaway_triggered[0]
                    log("warn", f"claude code cli runaway detectado — {reason}")
                    _RUNAWAY_CLOSE_MSG = (
                        "El operador ha solicitado detener el run: has alcanzado "
                        "el límite de turnos o costo configurado. "
                        "Por favor finaliza la tarea actual y entrega un resumen "
                        "de lo completado hasta ahora."
                    )
                    try:
                        if proc.stdin and not proc.stdin.closed:
                            proc.stdin.write(_user_message_line(_RUNAWAY_CLOSE_MSG))
                            proc.stdin.flush()
                    except Exception:
                        pass
                    _runaway_grace_deadline = _time.monotonic() + 60.0
                if _runaway_grace_deadline is not None and _time.monotonic() > _runaway_grace_deadline:
                    log("warn", "claude code cli runaway: gracia expirada — terminando")
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
                # R1.2 — run one-shot (brief→épica): apenas el agente entrega su
                # result terminal cerramos stdin para que el proceso salga limpio.
                # Damos una gracia corta y, si no sale, lo terminamos: así el run
                # finaliza en segundos (no espera 600s al watchdog) y libera el
                # slot, evitando el 409 duplicate_run por sesión zombie.
                if _one_shot and _result_ok_seen[0] and _one_shot_close_deadline is None:
                    log("info", "run one-shot: result terminal recibido — cerrando sesión")
                    try:
                        if proc.stdin and not proc.stdin.closed:
                            proc.stdin.close()
                    except Exception:  # noqa: BLE001
                        pass
                    _one_shot_close_deadline = _time.monotonic() + 20.0
                if _one_shot_close_deadline is not None and _time.monotonic() > _one_shot_close_deadline:
                    log("warn", "run one-shot: gracia post-result expirada — terminando")
                    proc.terminate()
                    try:
                        return_code = proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        return_code = proc.wait()
                    break
                # R1.1 — watchdog de inactividad: sin eventos por N segundos → stall.
                if stall_watchdog_sec > 0 and not _stall_fired[0]:
                    elapsed_no_event = _time.monotonic() - _last_event_mono[0]
                    if elapsed_no_event >= stall_watchdog_sec:
                        log("warn",
                            f"R1.1 stall watchdog: {elapsed_no_event:.0f}s sin eventos del stream — terminando")
                        if config.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED:
                            try:
                                log_streamer.flush(execution_id)
                            except Exception:  # noqa: BLE001
                                pass
                        try:
                            if proc.stdin and not proc.stdin.closed:
                                proc.stdin.close()
                        except Exception:  # noqa: BLE001
                            pass
                        proc.terminate()
                        try:
                            return_code = proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            return_code = proc.wait()
                        _stall_fired[0] = True
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
            "work_item_type": work_item_type,
            "claude_code_cli_bin": cmd[0],
            "claude_code_model": routed_model or model_override or config.CLAUDE_CODE_CLI_MODEL or None,
            "exit_code": return_code,
            "duration_ms": duration_ms,
            "output_file": str(output_file),
            "prompt_file": str(prompt_file),
            "agent_count": len(all_agents),
            "system_prompt_mode": system_prompt_mode,
            "system_prompt_file": str(system_prompt_file) if system_prompt_file else None,
            "agent_name": selected_agent.name,
            "pii_masked": bool(mask_map),
            "hooks_enabled": hooks_settings_file is not None,
            # Q0.1 / Q1.2 — flags de calidad para Q2.2 KPIs
            "acceptance_criteria_injected": _ac_injected,
            "few_shot_count": _fewshot_count,
            **invocation_meta,
        }
        # Plan 54 F2 — telemetría rejection_lessons CLI.
        if _mem_meta_claude:
            metadata.update(_mem_meta_claude)
        # H0.3 — flag de fallback de cwd (workspace_root vacío/None).
        if _cwd_fallback:
            metadata["cwd_fallback"] = True
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
                    # model_override (no el modelo resuelto): el launch computa el
                    # mismo fingerprint con model_override para el lookup, así
                    # coinciden. Dos runs con el mismo override (incl. None) → mismo fp.
                    model=model_override,
                    context_blocks=raw_blocks,
                )
        except Exception:  # noqa: BLE001
            logger.debug("V1.1 prompt_sha sealing falló (no crítico)", exc_info=True)
        # F2.2 — trazabilidad del conocimiento del proyecto inyectado.
        if knowledge_meta:
            metadata["project_knowledge"] = knowledge_meta
        # F2.1 / F2.3 — trazabilidad de MCP y resume.
        metadata["mcp_enabled"] = mcp_config_file is not None
        if resume_session_id:
            metadata["resumed_session_id"] = resume_session_id
        # F1.2 — telemetría nativa persistida en metadata. session_id va
        # top-level: habilita F2.3 (--resume) sin re-parsear nada.
        if stream_telemetry:
            session_id = stream_telemetry.get("session_id")
            if session_id:
                metadata["session_id"] = session_id
            metadata["claude_telemetry"] = {
                k: v for k, v in stream_telemetry.items() if k != "session_id"
            }
        # Plan 158 — paridad de telemetría de costo con codex_cli (kill-switch).
        # Se llama SIEMPRE (incluso con stream_telemetry vacío) para que
        # metadata["model"] quede seteado aunque el proceso haya sido matado
        # antes de un evento result (Defecto A es independiente del stall).
        if config.STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED:
            _finalize_cost_telemetry(
                execution_id=execution_id,
                metadata=metadata,
                stream_telemetry=stream_telemetry,
                routed_model=routed_model,
            )
        # F1.3 — trazabilidad del loop de autocorrección.
        if autocorrect is not None:
            metadata["autocorrect"] = autocorrect.summary()
        # Q1.1 — sello del pase correctivo de criterios (clave nueva, aditiva).
        if _criteria_repair_result[0] is not None:
            metadata["criteria_repair"] = _criteria_repair_result[0]
        # Fix robusto brief→épica — sello del pase correctivo de épica (aditivo).
        if _epic_repair_result[0] is not None:
            metadata["epic_repair"] = _epic_repair_result[0]
        # Plan 160 F0 — sello del pase correctivo de incidencia (aditivo).
        if _incident_repair_result[0] is not None:
            metadata["incident_repair"] = _incident_repair_result[0]
        # Plan 58 F4 — telemetría del bucle de convergencia (C4: solo en este scope,
        # no dentro de _on_stream_event donde metadata no está en scope).
        if getattr(config, "STACKY_QUALITY_CONVERGENCE_ENABLED", False) and _epic_repair_result[0] is not None:
            _p58 = _epic_repair_result[0]
            metadata["epic_convergence"] = {
                "enabled": True,
                "converged": _p58.get("converged"),
                "iterations": _p58.get("iterations"),
                "final_decision": _p58.get("final_decision"),
                "stop_reason": _p58.get("stop_reason"),
                "global_budget_spent": _p58.get("global_budget_spent"),
            }
        # Plan 41 — Autopublicación backend de la épica brief→épica.
        # Mueve la garantía de creación de la épica del navegador al backend:
        # si la run es brief→épica (one-shot del BusinessAgent) y el output trae
        # HTML de épica, se publica en ADO de forma autónoma, idempotente y con
        # fallo RUIDOSO (needs_review). Sella metadata["epic_ado_id"].
        def _maybe_autopublish_epic(current_status: str) -> str:
            if not config.STACKY_EPIC_AUTOPUBLISH_BACKEND:
                return current_status
            if not (_one_shot and (agent_type or "").lower() == "business"):
                return current_status
            # Plan 45 F2 — bifurcación Epic vs Issue según el tipo destino sellado
            # en metadata. Issue solo si el flag global está ON (defensa en
            # profundidad: run_brief ya rechaza Issue con flag OFF).
            _is_issue = (
                str(metadata.get("work_item_type") or "Epic") == "Issue"
                and config.STACKY_ISSUE_FROM_BRIEF_ENABLED
            )
            _label = "issue" if _is_issue else "épica"
            try:
                from api.tickets import (
                    autopublish_epic_from_run,
                    publish_issue_from_run,
                )
            except Exception as exc:  # noqa: BLE001
                log("warn", f"autopublish {_label}: import falló (no crítico): {exc}")
                return current_status
            _brief_text = ""
            for _b in (raw_blocks or []):
                if isinstance(_b, dict) and _b.get("id") == "brief":
                    _brief_text = str(_b.get("content") or "")
                    break
            _proj = project_ctx.stacky_project_name if project_ctx else None
            _seal_key = "issue_ado_id" if _is_issue else "epic_ado_id"
            _publish = publish_issue_from_run if _is_issue else autopublish_epic_from_run
            try:
                _publish_kwargs = {
                    "output": output,
                    "brief": _brief_text,
                    "project_name": _proj,
                    "already_published_id": metadata.get(_seal_key),
                }
                # Plan 47 F2bis — ventana temporal del rescate del disco (R-STALE):
                # solo aplica al path de épica (publish_issue_from_run no lo acepta).
                if not _is_issue:
                    _publish_kwargs["run_started_at"] = spawn_epoch
                _res = _publish(**_publish_kwargs)
            except Exception as exc:  # noqa: BLE001 — nunca tumbar el finalizador
                log("error", f"autopublish {_label}: error inesperado: {exc}")
                metadata["epic_publish_error"] = str(exc)
                return "needs_review"
            if _res.error is not None:
                # Fallo RUIDOSO: el WI NO se creó → needs_review visible.
                metadata["epic_publish_error"] = _res.error
                log("error", f"autopublish {_label}: publicación falló → needs_review: {_res.error}")
                return "needs_review"
            if _res.ado_id is not None and not _res.skipped:
                metadata[_seal_key] = _res.ado_id
                log("info", f"autopublish {_label}: {_label} creado autónomamente ado_id={_res.ado_id}")
            elif _res.ado_id is not None and _res.skipped:
                metadata[_seal_key] = _res.ado_id  # ya sellado, re-afirmar
            # Plan 42 F2/F4 — sellar warnings de grounding y resumen post-épica.
            # Plan 52 F4 — el path Issue también produce grounding_warnings y
            # epic_summary (publish_issue_from_run los puebla reusando las helpers).
            if _res.grounding_warnings:
                metadata["grounding_warnings"] = _res.grounding_warnings
            if _res.epic_summary is not None:
                metadata["epic_summary"] = _res.epic_summary
            # Plan 47 F3 — telemetría del método de recuperación de la épica.
            if _res.recovery_method:
                metadata["epic_recovery"] = _res.recovery_method
            # Plan 60 F1 — sellar baseline para aprendizaje bidireccional.
            if not _is_issue and not _res.skipped:
                if _res.published_html is not None:
                    metadata["epic_baseline_html"] = _res.published_html
                if _res.baseline_rev is not None:
                    metadata["epic_baseline_rev"] = _res.baseline_rev
            return current_status

        # H5 — trazabilidad del runaway guard.
        if _runaway_triggered:
            # Incluso en runaway intentamos publicar la épica si el agente alcanzó
            # a entregar el HTML (no perder trabajo); el status sigue needs_review.
            _maybe_autopublish_epic("needs_review")
            metadata["runaway"] = {
                "reason": _runaway_triggered[0],
                "turns": stream_telemetry.get("num_turns"),
                "cost": stream_telemetry.get("total_cost_usd"),
            }
            # El run terminó por runaway: siempre needs_review.
            log("warn", f"claude code cli runaway — degradando a needs_review: {_runaway_triggered[0]}")
            _mark_terminal(
                execution_id,
                status="needs_review",
                output=output,
                metadata=metadata,
            )
            _safe_write_manifest(
                run_dir,
                run_id=execution_id,
                agent_type=agent_type,
                status="needs_review",
                exit_code=return_code,
                output_file=output_file,
                prompt_file=prompt_file,
            )
            append_event(
                run_dir,
                execution_id=execution_id,
                event_type="needs_review",
                payload={"exit_code": return_code, "duration_ms": duration_ms,
                         "runaway": _runaway_triggered[0]},
            )
            ticket_status.on_execution_end(
                ticket_id=ticket_id,
                execution_id=execution_id,
                final_status="needs_review",
                agent_type=agent_type,
            )
            _notify_outcome(
                execution_id=execution_id,
                ticket_id=ticket_id,
                agent_type=agent_type,
                status="needs_review",
            )
            return

        # I1.1 — Auto-reparación ante output vacío/malformado (STACKY_RUN_REPAIR_ENABLED).
        # Corre ANTES de la evaluación de calidad, solo si return_code==0 y flag ON.
        # Comparte el techo de retries del autocorrect. OFF → sin cambio.
        if return_code == 0 and config.STACKY_RUN_REPAIR_ENABLED:
            try:
                from harness.run_repair import attempt_repair as _attempt_repair_cl

                _cl_autocorrect_retries = (
                    autocorrect.attempts if autocorrect is not None else 0
                )
                _cl_autocorrect_budget = (
                    config.CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES
                )

                def _claude_repair_send(msg: str) -> str:
                    """Envía mensaje de repair via stdin y devuelve nueva salida."""
                    try:
                        ok = _send_system_message(execution_id, msg)
                        if ok and output_file.exists():
                            return output_file.read_text(encoding="utf-8", errors="replace")
                        return ""
                    except Exception as _e:
                        log("warn", f"run_repair claude send falló: {_e}")
                        return ""

                _cl_repair_result = _attempt_repair_cl(
                    output_text=output or "",
                    artifacts=[str(output_file)] if output_file.exists() else [],
                    runtime=RUNTIME,
                    retries_budget=_cl_autocorrect_budget,
                    retries_used=_cl_autocorrect_retries,
                    send_fn=_claude_repair_send,
                    enabled=True,
                )
                if _cl_repair_result is not None:
                    metadata["run_repair"] = _cl_repair_result
                    if _cl_repair_result.get("recovered"):
                        log("info", "run_repair: output recuperado tras reintento (claude)")
                        # Re-leer output reparado
                        if output_file.exists():
                            output = output_file.read_text(encoding="utf-8", errors="replace")
                    else:
                        log("warn", "run_repair: reintento no recuperó el output (claude)")
            except Exception as exc:  # noqa: BLE001
                log("warn", f"run_repair claude falló (no crítico): {exc}")

        # R1.1/R1.2 — desenlace del run. Un stall SIN result terminal exitoso es
        # un cuelgue real → failed. Si hubo result(ok), el agente terminó su
        # trabajo y la sesión solo quedó ociosa → se trata como éxito.
        _outcome_kind = _classify_run_outcome(
            stall_fired=_stall_fired[0],
            result_ok_seen=_result_ok_seen[0],
            return_code=return_code,
        )
        if _outcome_kind == "failed_stall":
            # Plan 144 F4 (C1) — trust persistido (F2) o lectura on-demand si
            # el preflight estaba OFF (diagnóstico best-effort).
            trust_ok = _derive_stall_trust_ok(execution_id, cwd)
            stall_meta = {
                "detected_at": datetime.utcnow().isoformat(),
                "last_event_at": _last_event_wall[0].isoformat(),
                "last_signal": _last_event_kind[0],
                "seconds_idle": round(time.monotonic() - _last_event_mono[0]),
                "watchdog_seconds": stall_watchdog_sec,
                "trust_ok": trust_ok,  # True/False si se conoce; None si indeterminado.
            }
            metadata["stall"] = stall_meta
            _mark_terminal(
                execution_id,
                status="failed",
                error="stalled: stream sin eventos",
                metadata=metadata,
            )
            log("error",
                f"run terminado por inactividad ({stall_watchdog_sec}s) — última señal: {_last_event_kind[0]}")
            ticket_status.on_execution_end(
                ticket_id=ticket_id,
                execution_id=execution_id,
                final_status="error",
                agent_type=agent_type,
                error="stalled",
            )
            _notify_outcome(
                execution_id=execution_id,
                ticket_id=ticket_id,
                agent_type=agent_type,
                status="error",
            )
        elif _outcome_kind == "success":
            # Éxito: salida limpia (rc=0) o el agente emitió un result terminal
            # exitoso (one-shot cerrado, o stall/terminate tras entregar trabajo).
            if _result_ok_seen[0] and return_code != 0:
                metadata["finalized_after_result"] = {
                    "reason": "stall_or_oneshot_close",
                    "stall_fired": bool(_stall_fired[0]),
                    "one_shot": bool(_one_shot),
                    "exit_code": return_code,
                    "last_event_at": _last_event_wall[0].isoformat(),
                }
                log("info", "result(ok) recibido: run finalizado como exitoso (sesión cerrada tras entregar trabajo)")
            # F1.1 — Paridad de calidad con el path copilot: contract validator
            # + confidence ANTES de marcar terminal. Con el gate habilitado,
            # errores duros de contrato degradan a needs_review (estado ya
            # soportado por agent_completion.py), no completed.
            cv_result, conf, final_status = _evaluate_output_quality(
                agent_type or "", output or "", log=log
            )
            metadata["confidence"] = conf.to_dict()
            metadata["contract_score"] = cv_result.score
            # Plan 41 — autopublicar la épica antes de marcar terminal. Puede
            # forzar needs_review si la publicación falla (fallo ruidoso).
            final_status = _maybe_autopublish_epic(final_status)
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
            # Plan 77 F3 (Claude CLI) — Postea análisis de fase del Issue (si aplica). No-fatal.
            try:
                from api.tickets import publish_issue_phase_from_run as _pub_issue_phase  # noqa: PLC0415
                _ipm = _pub_issue_phase(
                    ticket_id=ticket_id,
                    agent_type=agent_type,
                    output=output or "",
                    project_name=project_name,
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
                contract_result=cv_result.to_dict(),
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
            log("info", f"claude code cli {final_status} ({duration_ms}ms)")
            # Hook A (Fase B): captura DRAFT post-run, paridad con github_copilot.
            # Solo en completed: un run degradado por contrato no es buen draft.
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
                    "status": final_status,
                    "contract_passed": cv_result.passed,
                    "contract_score": cv_result.score,
                    "confidence": conf.overall,
                    "total_cost_usd": stream_telemetry.get("total_cost_usd"),
                    "num_turns": stream_telemetry.get("num_turns"),
                },
                tags=["agent", RUNTIME],
            )
        else:
            # Plan 37 (F2.2) — el motivo real del exit!=0 vive en stderr: lo
            # persistimos en error_message (→ manifest + DB), en el evento y en
            # metadata para que el fallo se VEA y no parezca "usó Copilot".
            stderr_excerpt = _stderr_excerpt(stderr_tail)
            error = _format_cli_error(return_code, stderr_excerpt)
            if stderr_excerpt:
                metadata["stderr_tail"] = stderr_excerpt
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
                payload={
                    "exit_code": return_code,
                    "duration_ms": duration_ms,
                    "error": error,
                    "stderr_tail": stderr_excerpt,
                },
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
                _notify_outcome(
                    execution_id=execution_id,
                    ticket_id=ticket_id,
                    agent_type=agent_type,
                    status="error",
                )
        except Exception:
            logger.exception("could not mark ticket status after claude code cli failure")
    finally:
        # F1.4 — limpiar los archivos efímeros del hook (Stacky genera y limpia).
        if hooks_settings_file is not None and run_dir is not None:
            try:
                from services import claude_cli_hooks

                claude_cli_hooks.cleanup_run_settings(run_dir)
            except Exception:  # noqa: BLE001
                logger.debug("[exec=%s] hooks cleanup failed", execution_id, exc_info=True)
        # V0.3 — liberar el slot de concurrencia adquirido en el launch.
        try:
            from services import run_slots
            run_slots.release()
        except Exception:  # noqa: BLE001
            logger.debug("[exec=%s] run_slots.release falló", execution_id, exc_info=True)
        log_streamer.close(execution_id)


# ---------------------------------------------------------------------------
# H3.3 — Egress check para CLI
# ---------------------------------------------------------------------------

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
    import os as _os  # noqa: PLC0415 — evitar shadowing del módulo os del módulo
    if _os.environ.get("STACKY_CLI_EGRESS_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return None
    try:
        from services import egress_policies  # noqa: PLC0415
        return egress_policies.check(project=project, model=model, context_text=prompt)
    except Exception:  # noqa: BLE001
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger("stacky.cli_runner").debug(
            "_check_cli_egress: error inesperado, saltando check", exc_info=True
        )
        return None


# ---------------------------------------------------------------------------
# Construcción del comando
# ---------------------------------------------------------------------------

def _map_effort(complexity: str | None) -> str | None:
    """Q0.2 — Mapa determinístico S/M/L/XL → low/medium/high.

    Respeta STACKY_EFFORT_FLOOR como piso. Devuelve None si el flag está OFF
    para que `_build_command` caiga al default de config (byte-idéntico).
    """
    if not getattr(config, "STACKY_ADAPTIVE_EFFORT_ENABLED", False):
        return None
    if not complexity:
        return None
    _MAP = {"S": "low", "M": "medium", "L": "high", "XL": "high"}
    mapped = _MAP.get(complexity, "medium")
    floor = (getattr(config, "STACKY_EFFORT_FLOOR", "medium") or "medium").strip().lower()
    _ORDER = {"low": 0, "medium": 1, "high": 2}
    if _ORDER.get(mapped, 1) < _ORDER.get(floor, 1):
        mapped = floor
    return mapped


def _build_command(
    *,
    model_override: str | None,
    system_prompt_file: Path | None = None,
    settings_file: Path | None = None,
    mcp_config_file: Path | None = None,
    resume_session_id: str | None = None,
    effort_override: str | None = None,
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

    # F1.4 — settings.json efímero generado por Stacky (solo hooks; no toca
    # permisos, --dangerously-skip-permissions sigue mandando — §5.3).
    if settings_file is not None:
        cmd.extend(["--settings", str(settings_file)])

    # F2.1 — Stacky MCP server inyectado vía --mcp-config (stdio).
    if mcp_config_file is not None:
        cmd.extend(["--mcp-config", str(mcp_config_file)])

    # F2.3 — continuación de sesión: reusa el contexto cacheado de la sesión
    # previa (más barato y con memoria de lo ya hecho). El delta prompt se
    # envía como primer mensaje de usuario (ver _run_in_background).
    if resume_session_id:
        cmd.extend(["--resume", str(resume_session_id)])

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

    # Reasoning effort (`--effort low|medium|high`, CLI >= 2.x).
    # effort_override gana sobre config (Q0.2 — adaptativo). Valores inválidos
    # no se pasan para no romper el spawn.
    effort = (effort_override or getattr(config, "CLAUDE_CODE_CLI_EFFORT", "") or "").strip().lower()
    # Plan 43 F0 — set ampliado: low/medium/high/xhigh/max (oficial Claude CLI >= 2.x).
    if effort in ("low", "medium", "high", "xhigh", "max"):
        cmd.extend(["--effort", effort])

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


def _write_repro_script(
    run_dir: Path,
    *,
    cmd: list[str],
    cwd: Path,
    execution_id: int,
    initial_message: str,
) -> Path:
    """F1.2 (decisión §5.1) — genera `repro.ps1` en el run_dir.

    Script PowerShell con el comando exacto + env mínimo para que el operador
    reproduzca el run a mano al debuggear. El primer mensaje de usuario
    (stream-json) se materializa en `first_message.jsonl` y se pipea por stdin,
    igual que hace el runner.
    """
    first_message = run_dir / "first_message.jsonl"
    first_message.write_text(_user_message_line(initial_message), encoding="utf-8")

    quoted = " ".join(
        f'"{part}"' if any(ch.isspace() for ch in part) or part.endswith((".md", ".json")) else part
        for part in cmd
    )
    script = f"""# repro.ps1 — generado por Stacky Agents (execution_id={execution_id})
# Reproduce este run de Claude Code CLI a mano. El prompt inicial va por stdin
# en formato stream-json (first_message.jsonl). Sumá mensajes escribiendo más
# líneas JSONL en stdin si querés continuar la conversación.
$env:STACKY_EXECUTION_ID = "{execution_id}"
Set-Location "{cwd}"
Get-Content -Raw "{first_message}" | & {quoted}
"""
    repro = run_dir / "repro.ps1"
    repro.write_text(script, encoding="utf-8")
    return repro


def _evaluate_output_quality(agent_type: str, output: str, *, log=None):
    """F1.1 — Paridad de calidad con el path copilot (agent_runner.py:686-757).

    Corre contract_validator + confidence sobre el output y decide el status
    terminal: con CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED=true, errores duros de
    contrato degradan a `needs_review`; si no, queda `completed` (la validación
    y la persistencia corren siempre).

    Retorna (cv_result, confidence_result, final_status).
    """
    import contract_validator
    from services import confidence

    _log = log or (lambda *a, **k: None)

    _log("info", "validando contrato del output…")
    cv_result = contract_validator.validate(agent_type, output or "")
    _log(
        "info" if cv_result.passed else "warn",
        f"contrato {'OK' if cv_result.passed else 'WARNINGS'} — score {cv_result.score}/100"
        + (f" ({len(cv_result.failures)} errores)" if cv_result.failures else ""),
    )

    conf = confidence.score(output or "")
    _log(
        "info" if conf.overall >= 70 else "warn",
        f"confidence {conf.overall}/100"
        + (f" (señales: {len(conf.signals)})" if conf.signals else ""),
    )

    final_status = "completed"
    if config.CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED and cv_result.failures:
        final_status = "needs_review"
        _log(
            "warn",
            f"contrato con {len(cv_result.failures)} error(es) duro(s) → needs_review "
            "(CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED=true)",
        )
    return cv_result, conf, final_status


# ---------------------------------------------------------------------------
# Construcción del prompt
# ---------------------------------------------------------------------------

# H3.1 — Texto canónico de reglas delegado a harness/run_contract.py.
# Ya no se mantiene texto local; los runners consumen rules_text() en call-time.
# Compatibilidad: _STACKY_RULES se mantiene como alias lazy para código no
# migrado (legacy prompt monolítico _build_claude_code_prompt).
def _get_stacky_rules(*, mcp_enabled: bool = False) -> str:
    from harness.run_contract import rules_text  # noqa: PLC0415
    return rules_text(runtime="claude", mcp_enabled=mcp_enabled)


# Alias de compatibilidad para _build_claude_code_prompt (modo rollback).
# No se usa en _build_system_prompt (call-time lookup).
_STACKY_RULES = _get_stacky_rules()


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


def _resolve_resume(
    *,
    execution_id: int,
    ticket_id: int | None,
    agent_type: str | None,
    project_name: str | None,
    current_blocks: list[dict],
    log,
) -> tuple[str | None, str | None]:
    """F2.3 / H7.1 — Decide si continuar la sesión Claude previa con --resume + delta.

    Delega en harness.resume.resolve (dueño único, parametrizado por runtime).
    Mantiene la firma original para garantizar bit-identical con el runner claude.
    Best-effort: cualquier fallo → (None, None). Nunca lanza.
    """
    try:
        from harness.resume import resolve as _resume_resolve

        session_ref, delta_prefix = _resume_resolve(
            runtime=RUNTIME,
            ticket_id=ticket_id,
            agent_type=agent_type,
            project=project_name,
            current_blocks=current_blocks,
            execution_id=execution_id,
        )
        if session_ref:
            log(
                "info",
                f"re-run con --resume de sesión previa (F2.3/H7.1): session_id={session_ref[:12]}…",
            )
        return session_ref, delta_prefix
    except Exception as exc:  # noqa: BLE001 — resume nunca tumba el run
        log("warn", f"no se pudo resolver --resume (arranque en frío): {exc}")
        return None, None


def _build_project_knowledge(
    *,
    agent_type: str,
    project_name: str | None,
    context_text: str,
    log,
) -> tuple[str, dict]:
    """F2.2 — Conocimiento del proyecto para el system prompt (por proyecto, OFF
    default). Delega en cli_project_knowledge (dueño único, anti B6). Nunca lanza.
    """
    from services import cli_feature_flags

    if not cli_feature_flags.project_knowledge_enabled(project_name):
        return "", {}
    try:
        from services import cli_project_knowledge

        return cli_project_knowledge.build_project_knowledge_section(
            agent_type=agent_type,
            project=project_name,
            context_text=context_text,
            log=log,
        )
    except Exception as exc:  # noqa: BLE001 — el conocimiento nunca bloquea el run
        log("warn", f"no se pudo componer el conocimiento del proyecto (F2.2): {exc}")
        return "", {"project_knowledge_error": str(exc)}


def _build_system_prompt(
    selected_agent: vscode_agents.VsCodeAgent,
    *,
    invocation_block: str = "",
    project_knowledge: str = "",
    mcp_enabled: bool = False,
    skills_section: str = "",
) -> str:
    """System prompt real para --append-system-prompt-file (Fase C).

    Declara dónde está el `.agent.md` seleccionado y las reglas duras de Stacky,
    pero no copia el contenido del agente dentro del prompt. Si F2.2 está activa
    por proyecto, agrega el bloque de conocimiento del proyecto al final.

    H3.1: las reglas se obtienen de harness.run_contract.rules_text en call-time.
    H4.3: si skills_section está presente, se inyecta ANTES de _STACKY_RULES.
    """
    from harness.run_contract import rules_text  # noqa: PLC0415
    rules = rules_text(runtime="claude", mcp_enabled=mcp_enabled)
    invocation_section = f"{invocation_block}\n\n" if invocation_block else ""
    knowledge_section = f"\n\n{project_knowledge.strip()}\n" if project_knowledge.strip() else ""
    skills_block = f"\n\n{skills_section.strip()}\n" if skills_section.strip() else ""
    return f"""Stacky te lanzó desde Claude Code CLI para trabajar sobre un ticket y mantener
trazabilidad en los logs del workbench. No se inyecta el contenido del `.agent.md`
seleccionado en este system prompt: leelo desde la ruta indicada abajo y usá ese
archivo como fuente de rol, criterio, tono, restricciones y forma de trabajo.

{invocation_section}# Agente que estás adoptando: {selected_agent.name} ({selected_agent.filename})

{rules}{knowledge_section}{skills_block}
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

{invocation_section}Tu `.agent.md` (persona/rol) no está en este mensaje: leé el archivo desde la
'Ruta agent.md' indicada arriba y usalo como fuente de rol, criterio, tono,
restricciones y forma de trabajo.

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
    on_event: Any | None = None,
) -> None:
    """Lee stdout/stderr línea a línea y parsea el stream JSON de Claude Code.

    Claude Code con --output-format stream-json emite eventos JSONL.
    Los eventos del tipo 'assistant' con role='assistant' contienen el texto
    generado; los eventos 'result' tienen el output final consolidado.

    `on_event(data: dict)` (F1.2/F1.3): callback opcional invocado con cada
    evento JSON parseado — telemetría nativa + detección de fin de turno.
    """
    if stream is None:
        return
    for raw in stream:
        line = raw.rstrip("\r\n")
        if not line:
            continue
        message, level, extracted_text, event = _parse_claude_code_line(line, default_level)
        # Render detallado (thinking / tool_use / tool_result) para eventos
        # assistant/user; el resto usa el mensaje plano del parser.
        detail_lines = _event_detail_lines(event)
        if detail_lines is None:
            detail_lines = [(message, level)] if message else []
        for detail_message, detail_level in detail_lines:
            _push(execution_id, detail_level, detail_message, group=group)
            tail.append(detail_message)
        if len(tail) > 200:
            del tail[:50]
        # Acumular texto de output para extracción final
        if final_output is not None and extracted_text:
            final_output.append(extracted_text)
        if on_event is not None and event is not None:
            try:
                on_event(event)
            except Exception:  # noqa: BLE001 — el callback nunca corta el stream
                logger.exception("[exec=%s] on_event callback failed", execution_id)


# Tope del echo del prompt inicial en la consola in-page. El prompt completo
# queda siempre en prompt.md del run_dir (metadata.prompt_file).
_PROMPT_ECHO_MAX_CHARS = 6000


def _prompt_echo_message(prompt: str, *, pii_masked: bool = False) -> str:
    """Arma el mensaje de consola con el input exacto enviado a la CLI.

    Permite al operador ver/debuggear el prompt real sin abrir el prompt.md
    del run_dir. Si hubo masking de PII, lo indica: los placeholders [PII_n]
    son lo que la CLI realmente recibe. Truncado para no inundar la consola.
    """
    body = prompt
    if len(prompt) > _PROMPT_ECHO_MAX_CHARS:
        body = (
            prompt[:_PROMPT_ECHO_MAX_CHARS]
            + f"\n… [truncado: {len(prompt)} chars en total — completo en prompt.md del run]"
        )
    suffix = " (PII enmascarada)" if pii_masked else ""
    return f"input inicial → claude{suffix}:\n{body}"


def _tool_result_excerpt(content: Any, max_chars: int = 400) -> str:
    """Resume el contenido de un tool_result a una línea legible."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_text = str(block.get("text") or "")
            if block_text:
                parts.append(block_text)
            elif block.get("type"):
                # Bloques no-textuales (image, document, …): dejar constancia.
                parts.append(f"[bloque {block.get('type')}]")
        text = " ".join(parts)
    elif content is None:
        text = ""
    elif isinstance(content, dict):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)
    text = " ".join(text.split())
    return text[:max_chars] if text else "(sin contenido)"


def _event_detail_lines(event: dict | None) -> list[tuple[str, str]] | None:
    """Render debug-friendly de eventos assistant/user del stream-json.

    Devuelve [(message, level), ...] respetando el orden real de los bloques
    de contenido (thinking → texto → tool_use / tool_result), para que la
    consola in-page muestre cómo razona y qué herramientas usa la CLI.
    Devuelve None si el evento no tiene render especial (cae al mensaje plano
    de _parse_claude_code_line).
    """
    if not isinstance(event, dict):
        return None
    event_type = event.get("type")
    if event_type not in ("assistant", "user"):
        return None
    message_obj = event.get("message")
    if not isinstance(message_obj, dict):
        return None
    content = message_obj.get("content")
    if isinstance(content, str):
        # user events con content plano (p. ej. replay de --resume).
        text = content.strip()
        if not text:
            return []
        label = "assistant" if event_type == "assistant" else "user"
        return [(f"{label}: {text[:3000]}", "info")]
    if not isinstance(content, list):
        return None
    text_label = "assistant" if event_type == "assistant" else "user"
    lines: list[tuple[str, str]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "thinking":
            text = str(item.get("thinking") or item.get("text") or "").strip()
            if text:
                lines.append((f"thinking: {text[:3000]}", "debug"))
        elif item_type == "text":
            text = str(item.get("text") or "").strip()
            if text:
                lines.append((f"{text_label}: {text[:3000]}", "info"))
        elif item_type == "tool_use":
            tool_name = item.get("name") or "tool"
            summary = json.dumps(item.get("input") or {}, ensure_ascii=False)[:600]
            lines.append((f"tool_use/{tool_name}: {summary}", "info"))
        elif item_type == "tool_result":
            is_err = bool(item.get("is_error"))
            excerpt = _tool_result_excerpt(item.get("content"))
            lines.append(
                (
                    f"tool_result({'error' if is_err else 'ok'}): {excerpt}",
                    "warn" if is_err else "info",
                )
            )
    return lines


def _capture_result_telemetry(telemetry: dict, event: dict) -> None:
    """F1.2 — Captura telemetría nativa del stream-json en un dict mutable.

    `session_id` aparece en system/init y en result; usage/cost/turns solo en
    el evento `result` final de cada turno (el último gana).
    """
    session_id = event.get("session_id")
    if session_id:
        telemetry["session_id"] = session_id
    if event.get("type") != "result":
        return
    usage = event.get("usage")
    if isinstance(usage, dict):
        captured = {
            key: usage.get(key)
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            )
            if usage.get(key) is not None
        }
        if captured:
            telemetry["usage"] = captured
    for key in ("total_cost_usd", "num_turns", "is_error"):
        if event.get(key) is not None:
            telemetry[key] = event[key]


def _finalize_cost_telemetry(
    execution_id: int,
    metadata: dict,
    stream_telemetry: dict,
    routed_model: str | None,
) -> None:
    """Plan 158 F1 — expone metadata["model"] (clave canónica que lee
    cost_analytics.extract_cost_row) y persiste harness_telemetry canónico,
    con paridad exacta con codex_cli_runner.py:808-817.

    Defecto A (plan 158 §2.3): el modelo resuelto sólo vivía en
    metadata["claude_code_model"], nunca en metadata["model"]. Este método
    setea AMBAS claves — "claude_code_model" no se borra (retro-compat).

    Defecto B (plan 158 §2.3): claude_code_cli_runner nunca llamaba
    harness.telemetry.persist(), a diferencia de codex_cli_runner. Sin esa
    llamada, metadata["harness_telemetry"] nunca existe para este runtime y
    el fallback de estimación de costo (_maybe_estimate_cost) nunca corre.

    Nunca lanza: cualquier fallo de persist() se loguea como warning (no
    crítico), igual que el try/except de codex_cli_runner.py:816-817.
    """
    resolved_model = routed_model or metadata.get("claude_code_model")
    metadata["model"] = resolved_model
    if not stream_telemetry:
        return
    try:
        from harness.telemetry import from_claude_stream, persist as _persist_telemetry

        _stream_for_telemetry = dict(stream_telemetry)
        _stream_for_telemetry.setdefault("model", resolved_model)
        _t = from_claude_stream(_stream_for_telemetry)
        _persist_telemetry(execution_id, _t)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[exec={execution_id}] harness_telemetry claude: persist falló (no crítico): {exc}"
        )


def _parse_claude_code_line(
    line: str, default_level: str
) -> tuple[str, str, str, dict | None]:
    """Parsea una línea del stream JSON de Claude Code CLI.

    Retorna (message_for_log, level, extracted_text_for_output, event_dict).
    `event_dict` es el JSON parseado (None si la línea no era JSON-objeto) —
    lo consumen la telemetría F1.2 y el loop de autocorrección F1.3.

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
        return (line[:4000], default_level, "", None)

    if not isinstance(data, dict):
        return (str(data)[:4000], default_level, "", None)

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
                data,
            )
        return (f"result: {json.dumps(data, ensure_ascii=False)[:3500]}", level, "", data)

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
                return (f"assistant: {short}", "info", extracted_text, data)
        return (f"assistant: {json.dumps(data, ensure_ascii=False)[:3500]}", "info", "", data)

    # Tool use — solo log, sin output
    if event_type == "tool_use":
        tool_name = data.get("name") or data.get("tool_name") or "tool"
        tool_input = data.get("input") or {}
        summary = json.dumps(tool_input, ensure_ascii=False)[:500]
        return (f"tool_use/{tool_name}: {summary}", "info", "", data)

    if event_type == "tool_result":
        tool_id = data.get("tool_use_id") or ""
        is_err = bool(data.get("is_error"))
        level = "warn" if is_err else "info"
        return (f"tool_result/{tool_id}({'error' if is_err else 'ok'})", level, "", data)

    # Eventos de sistema (init, etc.)
    if event_type == "system":
        subtype = data.get("subtype") or ""
        return (f"system/{subtype}: {json.dumps(data, ensure_ascii=False)[:500]}", "debug", "", data)

    # Fallback genérico — igual que Codex
    for key in ("message", "msg", "text", "summary"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return (f"{event_type}: {value.strip()}"[:4000], level, "", data)

    return (f"{event_type}: {json.dumps(data, ensure_ascii=False)[:3500]}", level, "", data)


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

def _resolve_cwd(workspace_root: str | None) -> tuple[Path, bool]:
    """Resuelve el directorio de trabajo para el run.

    Returns:
        (path, cwd_fallback) donde cwd_fallback=True indica que se usó el
        directorio de instalación de Stacky como fallback (workspace_root vacío).

    Raises:
        ValueError: si workspace_root está seteado pero el path NO existe en
            disco. Nunca cae en silencio al dir de instalación con skip-permissions
            ON (H0.3 — fix hazard _resolve_cwd).
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    if workspace_root:
        candidate = Path(workspace_root)
        if candidate.exists():
            return candidate, False
        raise ValueError(
            f"workspace_root seteado pero no existe en disco: {workspace_root!r}. "
            "Verificá que el proyecto Stacky tenga una ruta válida configurada."
        )
    # workspace_root vacío/None → fallback al dir del repo; loguear advertencia
    fallback = Path(__file__).resolve().parents[2]
    _log.warning(
        "workspace_root vacío; usando fallback al dir de Stacky: %s. "
        "Seteá 'workspace_root' en el proyecto para evitar operar sobre la instalación.",
        fallback,
    )
    return fallback, True


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


def _derive_stall_trust_ok(execution_id: int, cwd: str | Path | None) -> bool | None:
    """Plan 144 F4 (C1) — deriva `trust_ok` para stall_meta.

    Prioriza el trust PERSISTIDO por el preflight (F2, `row.metadata_dict["trust"]`).
    Si no hay key persistida (preflight estaba OFF), hace una lectura on-demand
    sobre `cwd` — es justo el caso con mayor valor diagnóstico: el CLI colgado
    en el diálogo de trust en vez de salir con code 1. Extraída como función
    pura (sin stream) para ser testeable de forma aislada.

    Returns:
        True/False si el trust se conoce; None si es indeterminado (nunca
        False por ausencia de dato — evitar falso "no confiado").
    """
    trust_ok: bool | None = None
    try:
        with session_scope() as _s:
            _row = _s.get(AgentExecution, execution_id)
            _persisted = (_row.metadata_dict.get("trust") if _row else None) or {}
        if "trusted" in _persisted:
            trust_ok = bool(_persisted["trusted"])
        elif cwd:
            from services import claude_workspace_trust as _cwt
            trust_ok = _cwt.read_workspace_trust(str(cwd)).trusted
    except Exception:  # noqa: BLE001 — diagnóstico best-effort, nunca romper el cierre del run
        trust_ok = None
    return trust_ok


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

    # Plan 144 F2/F3 — preflight de confianza de workspace (solo Claude CLI).
    if config.CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED and workspace_root:
        from services import claude_workspace_trust as _cwt
        trust = _cwt.read_workspace_trust(workspace_root)
        if not trust.trusted:
            if config.CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED:
                # F3 — comportamiento explícito opt-in (excepción dura d).
                trust = _cwt.set_workspace_trusted(workspace_root)
                log("warn",
                    f"trust auto-set: workspace confiado automáticamente "
                    f"(projects[{trust.project_key}].hasTrustDialogAccepted=true)")
            else:
                remedio = (
                    f"El workspace no está confiado por Claude Code CLI. "
                    f"Abrí `claude` una vez en {trust.project_key} y aceptá el diálogo de confianza, "
                    f"o activá 'Auto-confiar workspace (claude)' en Config → Runtimes CLI, "
                    f"o seteá projects[\"{trust.project_key}\"].hasTrustDialogAccepted=true en {trust.config_path}."
                )
                log("error", f"pre-run bloqueado (trust): {remedio}")
                _mark_terminal(execution_id, status="error", error=remedio,
                               metadata={"trust": {"trusted": False, "project_key": trust.project_key}})
                if ticket_id is not None:
                    ticket_status.on_execution_end(
                        ticket_id=ticket_id, execution_id=execution_id,
                        final_status="error", agent_type=agent_type, error=remedio)
                return False
        else:
            with session_scope() as session:
                row = session.get(AgentExecution, execution_id)
                if row is not None:
                    current_md = row.metadata_dict
                    current_md["trust"] = {"trusted": True, "project_key": trust.project_key}
                    row.metadata_dict = current_md
    # (fin bloque trust)

    return True


def reap(execution_id: int, grace_seconds: int = 10) -> bool:
    """R0.1 — Termina el subproceso registrado para execution_id (claude_code_cli).

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
    contract_result: dict | None = None,
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
        # V0.4 — taxonomía de fallos: clasifica runs terminados en error/needs_review.
        if status in ("error", "needs_review"):
            try:
                from harness.failure import classify
                kind = classify(
                    return_code=current_md.get("return_code"),
                    error_message=error,
                    metadata={**current_md, "status": status,
                              "contract_result": contract_result or current_md.get("contract_result")},
                )
                if kind is not None:
                    current_md["failure_kind"] = kind
            except Exception:  # noqa: BLE001
                logger.debug("[exec=%s] failure classify falló", execution_id, exc_info=True)
            emit_failure_feedback = True
        row.metadata_dict = current_md
        # F1.1 — paridad con el path copilot (agent_runner.py:720)
        if contract_result is not None:
            row.contract_result = contract_result

    # R0.1/R0.2 — flush incremental y reap DESPUES de marcar estado en DB.
    if config.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED:
        if config.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED:
            try:
                log_streamer.flush(execution_id)
            except Exception:  # noqa: BLE001
                logger.debug("[exec=%s] flush incremental fallo (no critico)", execution_id)
        reap(execution_id)

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
