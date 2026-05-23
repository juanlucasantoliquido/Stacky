"""C11 — Eventos estructurados de ejecución para Replay timeline.

Persiste eventos JSONL por execution_id en `data/events/<execution_id>.jsonl`.
Cada llamada `record()` agrega una línea con timestamp relativo al inicio.

Diseño:
  - Append-only. Nunca reescribe ni borra; un Replay debe ser auditable.
  - Best-effort: fallos de IO se loguean pero no levantan al caller.
  - El reader (`load_events`) tolera líneas corruptas saltándolas.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from runtime_paths import data_dir

logger = logging.getLogger("stacky.execution_events")

_LOCK = threading.Lock()


def _events_dir() -> Path:
    path = data_dir() / "events"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _event_file(execution_id: int) -> Path:
    return _events_dir() / f"{execution_id}.jsonl"


def record(execution_id: int, kind: str, payload: dict | None = None) -> None:
    """Agrega un evento al timeline de una ejecución.

    `kind` debe ser short-string estable: 'started', 'context_resolved',
    'prompt_built', 'llm_call', 'tool_invocation', 'output_chunk',
    'completed', 'error', 'cancelled', etc.
    """
    if execution_id is None:
        return
    event = {
        "kind": kind,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "payload": payload or {},
    }
    line = json.dumps(event, ensure_ascii=False)
    file = _event_file(execution_id)
    try:
        with _LOCK:
            with file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError as exc:
        logger.warning("execution_events: write failed for %s: %s", execution_id, exc)


def load_events(execution_id: int) -> list[dict]:
    """Lee todos los eventos de una ejecución. Devuelve lista en orden."""
    file = _event_file(execution_id)
    if not file.exists():
        return []
    events: list[dict] = []
    try:
        with file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.warning("execution_events: read failed for %s: %s", execution_id, exc)
    return events


def normalize_for_replay(events: list[dict]) -> list[dict]:
    """Calcula `t_relative_ms` por evento, basado en el primer timestamp."""
    if not events:
        return []
    try:
        start = datetime.fromisoformat(events[0]["timestamp"].rstrip("Z"))
    except (KeyError, ValueError):
        return events
    out = []
    for ev in events:
        try:
            ts = datetime.fromisoformat(ev["timestamp"].rstrip("Z"))
            ev = {**ev, "t_relative_ms": int((ts - start).total_seconds() * 1000)}
        except (KeyError, ValueError):
            pass
        out.append(ev)
    return out
