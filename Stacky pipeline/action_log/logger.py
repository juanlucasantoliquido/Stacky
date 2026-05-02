"""
logger — Persistencia JSON-lines de acciones mutativas.

Cada línea del log es un JSON con:
    id, timestamp, actor, tool, params, result, reverse_action, ticket_id, status

El archivo se rota por mes: state/action_log_YYYY-MM.jsonl

Concurrent-safe: append-only + escritura atómica por línea.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# ── Modelo ────────────────────────────────────────────────────────────────────


@dataclass
class ActionLogEntry:
    """Entrada en el log de acciones mutativas."""

    id: str
    timestamp: str
    actor: str
    tool: str
    params: dict[str, Any]
    result: dict[str, Any]
    reverse_action: Optional[dict[str, Any]]  # {"tool": ..., "params": ...}
    ticket_id: Optional[int]
    status: str  # "logged" | "reversed" | "failed"


# ── Paths ─────────────────────────────────────────────────────────────────────


def _default_log_path(now: Optional[datetime] = None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    month_str = now.strftime("%Y-%m")
    state_dir = os.path.join(os.path.dirname(__file__), "..", "state")
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, f"action_log_{month_str}.jsonl")


# ── Escritura ─────────────────────────────────────────────────────────────────


def log_action(
    actor: str,
    tool: str,
    params: dict[str, Any],
    result: dict[str, Any],
    reverse: Optional[tuple[str, dict[str, Any]]] = None,
    ticket_id: Optional[int] = None,
    log_path: Optional[str] = None,
) -> ActionLogEntry:
    """
    Registra una acción mutativa en el log.

    Parámetros
    ----------
    actor:
        Nombre del agente o usuario que ejecuta la acción.
    tool:
        Identificador de la herramienta/operación (ej: "ado_manager.publish_comment").
    params:
        Inputs de la operación.
    result:
        Output de la operación.
    reverse:
        Tupla (tool_name, params_dict) para revertir la acción.
        None si la acción no es reversible.
    ticket_id:
        ID del work item ADO asociado (si aplica).
    log_path:
        Ruta al archivo de log. Si None, usa el path rotado por mes.

    Devuelve
    --------
    ActionLogEntry creada.
    """
    now = datetime.now(timezone.utc)
    entry = ActionLogEntry(
        id=str(uuid.uuid4()),
        timestamp=now.isoformat(),
        actor=actor,
        tool=tool,
        params=params,
        result=result,
        reverse_action=(
            {"tool": reverse[0], "params": reverse[1]} if reverse else None
        ),
        ticket_id=ticket_id,
        status="logged",
    )

    path = log_path or _default_log_path(now)
    _append_entry(path, entry)
    return entry


def _append_entry(path: str, entry: ActionLogEntry) -> None:
    """Append atómico al archivo JSON-lines."""
    line = json.dumps(asdict(entry), ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _update_entry_status(
    path: str, entry_id: str, new_status: str
) -> None:
    """
    Reescribe el archivo actualizando el status de una entrada.
    Operación costosa — solo para rollback (poco frecuente).
    """
    if not os.path.exists(path):
        return
    lines: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
                if record.get("id") == entry_id:
                    record["status"] = new_status
                    raw = json.dumps(record, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
            lines.append(raw)

    # Escribir con backup
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp_path, path)


# ── Lectura ───────────────────────────────────────────────────────────────────


def _iter_all_log_files(state_dir: Optional[str] = None) -> list[str]:
    """Devuelve todos los archivos de log ordenados por nombre (cronológico)."""
    base = state_dir or os.path.join(os.path.dirname(__file__), "..", "state")
    if not os.path.exists(base):
        return []
    return sorted(
        os.path.join(base, f)
        for f in os.listdir(base)
        if f.startswith("action_log_") and f.endswith(".jsonl")
    )


def _load_entries(
    ticket_id: Optional[int] = None,
    state_dir: Optional[str] = None,
) -> list[ActionLogEntry]:
    entries: list[ActionLogEntry] = []
    for log_file in _iter_all_log_files(state_dir):
        with open(log_file, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                    if ticket_id is not None and record.get("ticket_id") != ticket_id:
                        continue
                    entries.append(
                        ActionLogEntry(
                            id=record["id"],
                            timestamp=record["timestamp"],
                            actor=record["actor"],
                            tool=record["tool"],
                            params=record.get("params", {}),
                            result=record.get("result", {}),
                            reverse_action=record.get("reverse_action"),
                            ticket_id=record.get("ticket_id"),
                            status=record.get("status", "logged"),
                        )
                    )
                except (json.JSONDecodeError, KeyError):
                    pass
    return entries


def list_actions(
    ticket_id: Optional[int] = None,
    state_dir: Optional[str] = None,
) -> list[ActionLogEntry]:
    """
    Lista las acciones registradas, opcionalmente filtradas por ticket_id.

    Parámetros
    ----------
    ticket_id:
        Filtrar por work item ADO. None devuelve todas las acciones.
    state_dir:
        Directorio de state. None usa el default.
    """
    return _load_entries(ticket_id=ticket_id, state_dir=state_dir)


def get_action(
    action_id: str,
    state_dir: Optional[str] = None,
) -> Optional[ActionLogEntry]:
    """Obtiene una acción por su UUID."""
    for entry in _load_entries(state_dir=state_dir):
        if entry.id == action_id:
            return entry
    return None


def mark_entry_reversed(
    action_id: str,
    state_dir: Optional[str] = None,
) -> None:
    """Marca una entrada como 'reversed' en el log."""
    base = state_dir or os.path.join(os.path.dirname(__file__), "..", "state")
    for log_file in _iter_all_log_files(base):
        _update_entry_status(log_file, action_id, "reversed")


def mark_entry_failed(
    action_id: str,
    state_dir: Optional[str] = None,
) -> None:
    """Marca una entrada como 'failed' en el log."""
    base = state_dir or os.path.join(os.path.dirname(__file__), "..", "state")
    for log_file in _iter_all_log_files(base):
        _update_entry_status(log_file, action_id, "failed")
