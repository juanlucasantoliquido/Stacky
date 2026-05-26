"""
Chat libre -- turnos 2+ despues de la ejecucion formal inicial.

POST /api/chat/turn
  Body: {
    "agent_filename": "DevPacifico.agent.md",
    "model": "gpt-4o",                          # opcional, usa default si omite
    "messages": [                               # historial desde el turno 2 en adelante
      {"role": "assistant", "content": "..."},  # respuesta del turno 1
      {"role": "user",      "content": "..."}   # nuevo mensaje del usuario
    ],
    "workspace_dir": null                       # opcional
  }
  Returns: {
    "ok": true,
    "text": "respuesta del agente",
    "tool_log": [{"tool","args","output","ok"}],
    "turns": 1,
    "model_used": "gpt-4o",
    "logs": ["[info] turno 1", ...]
  }

Portado desde WS2 (2026-05-23) -- P1.2.
Adaptaciones WS1:
  - usa vscode_agents.get_agent_by_filename para leer system_prompt (en vez de _read_agent_system_prompt de WS2).
  - invoke_hybrid no disponible en WS1 -- se usa invoke() standard o mock.
  - codex_cli_runner.run_sync se importa condicionalmente (puede no estar en WS1).
"""
from __future__ import annotations

import logging

from flask import Blueprint, abort, jsonify, request

from config import config

bp = Blueprint("chat", __name__, url_prefix="/chat")
logger = logging.getLogger("stacky_agents.api.chat")


def _get_system_prompt(agent_filename: str) -> str:
    """Lee el system_prompt del archivo .agent.md del agente.

    Usa vscode_agents (WS1) en lugar de la funcion interna de WS2.
    Retorna string vacio si no se encuentra el agente.
    """
    from services import vscode_agents
    agent = vscode_agents.get_agent_by_filename(
        prompts_dir=config.VSCODE_PROMPTS_DIR or "",
        filename=agent_filename,
    )
    if agent is None:
        return ""
    return agent.system_prompt or ""


def _messages_to_prose(messages: list[dict]) -> str:
    """Convierte historial a texto plano para backends sin soporte multi-turno."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if role == "system" or not content:
            continue
        label = "Usuario" if role == "user" else "Asistente"
        parts.append(f"**{label}:** {content}")
    return "\n\n".join(parts)


@bp.post("/turn")
def chat_turn():
    payload = request.get_json(force=True, silent=True) or {}
    agent_filename = (payload.get("agent_filename") or "").strip()
    model = (payload.get("model") or "").strip() or None
    messages: list[dict] = payload.get("messages") or []
    workspace_dir = (payload.get("workspace_dir") or "").strip() or None
    runtime = (payload.get("runtime") or "").strip() or None
    project_name = (payload.get("project_name") or "").strip() or None

    if not agent_filename:
        abort(400, "agent_filename es requerido")
    if not messages:
        abort(400, "messages no puede estar vacio")

    for i, m in enumerate(messages):
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant", "system"):
            abort(400, f"messages[{i}].role debe ser user, assistant o system")
        if not isinstance(m.get("content"), str):
            abort(400, f"messages[{i}].content debe ser string")

    logs: list[str] = []

    def on_log(level: str, msg: str) -> None:
        logs.append(f"[{level}] {msg}")
        logger.info("chat_turn [%s] %s", level, msg)

    # -- Codex CLI runtime --
    if runtime == "codex_cli":
        try:
            from services import codex_cli_runner
            if hasattr(codex_cli_runner, "run_sync"):
                answer = codex_cli_runner.run_sync(
                    agent_filename=agent_filename,
                    messages=messages,
                    model=model,
                    workspace_dir=workspace_dir,
                )
            else:
                abort(501, "codex_cli_runner.run_sync no disponible en esta version")
            return jsonify({
                "ok": True,
                "text": answer,
                "tool_log": [],
                "turns": 1,
                "model_used": model or getattr(config, "CODEX_CLI_MODEL", "codex"),
                "logs": logs,
            })
        except TimeoutError as exc:
            return jsonify({"ok": False, "error": str(exc), "logs": logs}), 504
        except Exception as exc:
            logger.error("chat_turn codex error: %s", exc, exc_info=True)
            return jsonify({"ok": False, "error": str(exc), "logs": logs}), 500

    # -- copilot / vscode_bridge / mock runtime --
    system = _get_system_prompt(agent_filename)
    backend = (getattr(config, "LLM_BACKEND", None) or "mock").lower()

    try:
        import copilot_bridge

        if backend == "vscode_bridge" and hasattr(copilot_bridge, "invoke_hybrid"):
            # invoke_hybrid solo disponible si el fork WS2 esta mergeado
            result = copilot_bridge.invoke_hybrid(
                system=system,
                messages=messages,
                on_log=on_log,
                model=model,
                workspace_dir=workspace_dir,
                max_turns=12,
                project_name=project_name,
            )
        elif backend in ("copilot", "vscode_bridge"):
            # Fallback: componer historial como texto plano
            history_text = _messages_to_prose(messages)
            result = copilot_bridge.invoke(
                agent_type="custom",
                system=system,
                user=history_text,
                on_log=on_log,
                model=model,
                project_name=project_name,
            )
        else:
            # mock / cualquier otro backend
            result = copilot_bridge._invoke_mock(
                agent_type="custom",
                on_log=on_log,
                execution_id=None,
                model=model,
            )

        meta = result.metadata or {}
        return jsonify({
            "ok": True,
            "text": result.text,
            "tool_log": meta.get("tool_log") or [],
            "turns": meta.get("turns", 1),
            "model_used": meta.get("model") or model or getattr(config, "COPILOT_MODEL", "copilot"),
            "logs": logs,
        })

    except copilot_bridge.CancelledError:
        abort(409, "cancelled")
    except Exception as exc:
        logger.error("chat_turn error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc), "logs": logs}), 500
