"""
sse_bus.py — Puente entre ``pipeline_events.EventStore`` y Server-Sent Events
para el dashboard.

Exporta:
    - ``event_stream(...)`` — generator apto para Flask ``Response`` con
      ``mimetype='text/event-stream'``. Drena eventos del bus, formatea en SSE,
      emite heartbeats cada 15s, respeta ``Last-Event-ID`` y soporta replay
      desde el JSONL cuando un cliente se reconecta.
    - ``format_sse(...)`` — helper puro para tests.

Formato SSE:

    id: <event_num>
    event: <kind>
    data: <json>
    \n

``<event_num>`` es un entero monótono por cliente (no global); se incrementa
por cada línea emitida y se usa para ``Last-Event-ID``. El JSON incluye el
``execution_id`` y el resto del PipelineEvent.
"""

from __future__ import annotations

import json
import logging
import queue
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Generator, Iterable

from pipeline_events import EventStore, PipelineEvent, read_events

logger = logging.getLogger("stacky.sse")

HEARTBEAT_INTERVAL_SEC = 15
REPLAY_WINDOW_MINUTES = 10   # al reconectar, cuánto tiempo atrás consultamos el JSONL


# ── Helpers de formato ───────────────────────────────────────────────────────

def format_sse(event_id: int, kind: str, data: dict[str, Any]) -> str:
    """Serializa un evento en formato SSE. Usar desde tests."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    lines = [
        f"id: {event_id}",
        f"event: {kind}",
        f"data: {payload}",
        "",
        "",
    ]
    return "\n".join(lines)


def format_comment(comment: str) -> str:
    """Los comentarios SSE (líneas que empiezan con ':') se usan para heartbeats."""
    return f": {comment}\n\n"


def _event_to_dict(ev: PipelineEvent | dict[str, Any]) -> dict[str, Any]:
    if isinstance(ev, dict):
        return ev
    try:
        return ev.model_dump(mode="json", exclude_none=True)  # type: ignore[attr-defined]
    except AttributeError:
        return {k: v for k, v in ev.__dict__.items() if v is not None}


# ── Stream generator ─────────────────────────────────────────────────────────

def event_stream(
    *,
    last_event_id: str | None = None,
    ticket_id: str | None = None,
    kind_filter: str | None = None,
    max_seconds: int | None = None,
) -> Generator[str, None, None]:
    """
    Generator listo para enchufar a Flask::

        return Response(event_stream(...), mimetype='text/event-stream')

    - Si ``last_event_id`` (header ``Last-Event-ID`` HTTP) viene seteado,
      intenta hacer replay desde el JSONL de los últimos ``REPLAY_WINDOW_MINUTES``.
    - Siempre arranca con un evento ``hello`` para testeo de conectividad.
    - Heartbeats cada ``HEARTBEAT_INTERVAL_SEC`` para mantener la conexión viva.
    - ``max_seconds`` (opcional): corta el stream tras N segundos (usado en tests).

    Todos los filtros son por-subscriber: no mutan el bus ni afectan a otros clientes.
    """
    event_num = _parse_last_event_id(last_event_id)
    start_wall = time.time()

    # Subscribe FIRST (para no perder eventos entre replay y stream vivo).
    sub_queue = EventStore.instance().subscribe(maxsize=500)
    try:
        # Hello — evento de apertura con metadata útil para el cliente
        event_num += 1
        yield format_sse(event_num, "hello", {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticket_id": ticket_id,
            "kind_filter": kind_filter,
            "replay_window_minutes": REPLAY_WINDOW_MINUTES,
        })

        # Replay si hay Last-Event-ID
        if last_event_id:
            replayed = _replay(ticket_id=ticket_id, kind_filter=kind_filter)
            for rev in replayed:
                event_num += 1
                yield format_sse(event_num, rev.get("kind", "event"), rev)

        last_hb = time.monotonic()
        while True:
            # Corte por max_seconds (tests)
            if max_seconds is not None and (time.time() - start_wall) > max_seconds:
                yield format_comment("stream-ended")
                return

            # Heartbeat
            if time.monotonic() - last_hb >= HEARTBEAT_INTERVAL_SEC:
                yield format_comment(f"heartbeat {datetime.now(timezone.utc).isoformat()}")
                last_hb = time.monotonic()

            # Drenaje no-bloqueante con timeout corto
            try:
                ev = sub_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            data = _event_to_dict(ev)
            # Filtros por-subscriber
            if ticket_id and data.get("ticket_id") != ticket_id:
                continue
            if kind_filter and data.get("kind") != kind_filter:
                continue

            event_num += 1
            yield format_sse(event_num, data.get("kind", "event"), data)
    except GeneratorExit:
        # Cliente desconectó
        return
    except Exception as e:  # pragma: no cover — defensivo
        logger.debug("event_stream error: %s", e)
        yield format_comment(f"error: {e}")
    finally:
        try:
            EventStore.instance().unsubscribe(sub_queue)
        except Exception:
            pass


# ── Internals ────────────────────────────────────────────────────────────────

def _parse_last_event_id(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def _replay(*, ticket_id: str | None, kind_filter: str | None) -> Iterable[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(minutes=REPLAY_WINDOW_MINUTES)
    try:
        return read_events(
            ticket_id=ticket_id,
            kind=kind_filter,
            since=since,
            limit=500,
            days_back=2,
        )
    except Exception as e:  # pragma: no cover
        logger.debug("replay falló: %s", e)
        return []
