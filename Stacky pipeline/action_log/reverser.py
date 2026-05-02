"""
reverser — Ejecuta la reverse-action de una entrada del action_log.

Registro de handlers de reversión por tool name. Cada handler recibe los
params de la reverse-action y ejecuta la operación de rollback.

Uso:
    from action_log.reverser import reverse_action

    result = reverse_action(action_id="uuid-de-la-accion")
    # result["status"] == "reversed" | "failed"
    # result["reason"] explica qué pasó
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .logger import get_action, mark_entry_reversed, mark_entry_failed, ActionLogEntry


# ── Registry de handlers ──────────────────────────────────────────────────────

# Mapa: tool_name → callable(params: dict) → dict[str, Any]
_REVERSE_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_reverse_handler(
    tool: str,
    handler: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    """
    Registra un handler de rollback para un tool específico.

    Parámetros
    ----------
    tool:
        Nombre del tool tal como aparece en ``reverse_action.tool``.
        Ej: "ado_manager.delete_comment".
    handler:
        Callable(params: dict) → dict con al menos {"ok": bool, "detail": str}.
    """
    _REVERSE_HANDLERS[tool] = handler


# ── Handlers built-in ────────────────────────────────────────────────────────

def _noop_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handler para acciones sin reversión implementada."""
    return {"ok": False, "detail": "No reverse handler registered for this tool"}


# ── API pública ───────────────────────────────────────────────────────────────


def reverse_action(
    action_id: str,
    state_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Revierte una acción registrada en el action_log.

    Parámetros
    ----------
    action_id:
        UUID de la acción a revertir.
    state_dir:
        Directorio de state para buscar el log. None usa el default.
    dry_run:
        Si True, muestra qué se ejecutaría sin hacerlo.

    Devuelve
    --------
    Dict con:
        - ``status``: "reversed" | "failed" | "skipped"
        - ``reason``: descripción
        - ``action_id``: el id procesado
        - ``reverse_tool``: tool que se ejecutó (o None)
        - ``reverse_result``: output del handler (o None)
    """
    entry = get_action(action_id, state_dir=state_dir)
    if entry is None:
        return {
            "status": "failed",
            "reason": f"Acción {action_id!r} no encontrada en el log",
            "action_id": action_id,
            "reverse_tool": None,
            "reverse_result": None,
        }

    if entry.status == "reversed":
        return {
            "status": "skipped",
            "reason": "La acción ya fue revertida anteriormente",
            "action_id": action_id,
            "reverse_tool": None,
            "reverse_result": None,
        }

    if entry.reverse_action is None:
        return {
            "status": "skipped",
            "reason": "La acción no tiene reverse-action definida",
            "action_id": action_id,
            "reverse_tool": None,
            "reverse_result": None,
        }

    reverse_tool = entry.reverse_action["tool"]
    reverse_params = entry.reverse_action.get("params", {})

    if dry_run:
        return {
            "status": "dry_run",
            "reason": f"Ejecutaría: {reverse_tool}({reverse_params})",
            "action_id": action_id,
            "reverse_tool": reverse_tool,
            "reverse_result": None,
        }

    handler = _REVERSE_HANDLERS.get(reverse_tool, _noop_handler)

    try:
        result = handler(reverse_params)
        ok = result.get("ok", True)
        if ok:
            mark_entry_reversed(action_id, state_dir=state_dir)
            return {
                "status": "reversed",
                "reason": result.get("detail", "OK"),
                "action_id": action_id,
                "reverse_tool": reverse_tool,
                "reverse_result": result,
            }
        else:
            mark_entry_failed(action_id, state_dir=state_dir)
            return {
                "status": "failed",
                "reason": result.get("detail", "Handler devolvió ok=False"),
                "action_id": action_id,
                "reverse_tool": reverse_tool,
                "reverse_result": result,
            }
    except Exception as exc:  # noqa: BLE001
        mark_entry_failed(action_id, state_dir=state_dir)
        return {
            "status": "failed",
            "reason": f"Excepción en handler: {exc}",
            "action_id": action_id,
            "reverse_tool": reverse_tool,
            "reverse_result": None,
        }


def list_reversible_actions(
    ticket_id: Optional[int] = None,
    state_dir: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Lista acciones con reverse-action disponible que aún no fueron revertidas.

    Devuelve lista de dicts con keys: id, tool, timestamp, ticket_id, reverse_tool.
    """
    from .logger import list_actions

    entries = list_actions(ticket_id=ticket_id, state_dir=state_dir)
    return [
        {
            "id": e.id,
            "tool": e.tool,
            "timestamp": e.timestamp,
            "ticket_id": e.ticket_id,
            "status": e.status,
            "reverse_tool": e.reverse_action["tool"] if e.reverse_action else None,
        }
        for e in entries
        if e.reverse_action is not None and e.status == "logged"
    ]
