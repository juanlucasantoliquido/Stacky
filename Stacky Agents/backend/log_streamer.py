"""
Buffer in-memory de logs por execution_id + soporte SSE.

Cada ejecución abre un buffer (cola). Los productores empujan eventos;
los consumidores SSE leen desde un cursor. Al cerrar la ejecución, los logs
se persisten a la tabla `execution_logs`.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator

from db import session_scope
from models import ExecutionLog


@dataclass
class LogEvent:
    timestamp: datetime
    level: str
    message: str
    group: str | None = None
    indent: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message,
            "group": self.group,
            "indent": self.indent,
        }


@dataclass
class _Buffer:
    events: list[LogEvent] = field(default_factory=list)
    closed: bool = False
    listeners: list[queue.Queue] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


_buffers: dict[int, _Buffer] = {}
_buffers_lock = threading.Lock()


def open(execution_id: int) -> None:
    with _buffers_lock:
        _buffers.setdefault(execution_id, _Buffer())


def push(execution_id: int, level: str, message: str, group: str | None = None, indent: int = 0) -> None:
    buf = _get(execution_id)
    if buf is None:
        return
    event = LogEvent(timestamp=datetime.utcnow(), level=level, message=message, group=group, indent=indent)
    with buf.lock:
        buf.events.append(event)
        for listener in list(buf.listeners):
            try:
                listener.put_nowait(event)
            except queue.Full:
                pass


def logger_for(execution_id: int):
    def log(level: str, message: str, group: str | None = None, indent: int = 0) -> None:
        push(execution_id, level, message, group, indent)
    return log


def close(execution_id: int) -> None:
    buf = _get(execution_id)
    if buf is None:
        return
    with buf.lock:
        buf.closed = True
        for listener in list(buf.listeners):
            try:
                listener.put_nowait(None)
            except queue.Full:
                pass
    _persist(execution_id, buf)


def snapshot(execution_id: int) -> list[dict]:
    """Devuelve los logs actuales (in-memory + BD si ya se cerró)."""
    buf = _get(execution_id)
    if buf is not None:
        with buf.lock:
            return [e.to_dict() for e in buf.events]
    with session_scope() as session:
        rows = session.query(ExecutionLog).filter_by(execution_id=execution_id).order_by(ExecutionLog.timestamp).all()
        return [r.to_dict() for r in rows]


def stream(execution_id: int) -> Iterator[dict]:
    """
    Generator usado por el endpoint SSE. Devuelve eventos en formato dict.
    Termina cuando el buffer se cierra (closed=True y queue vacía).
    """
    buf = _get(execution_id)
    if buf is None:
        for ev in snapshot(execution_id):
            yield ev
        yield {"type": "completed"}
        return

    listener: queue.Queue = queue.Queue(maxsize=10000)
    with buf.lock:
        for e in buf.events:
            listener.put_nowait(e)
        if buf.closed:
            listener.put_nowait(None)
        else:
            buf.listeners.append(listener)

    try:
        while True:
            try:
                event = listener.get(timeout=15.0)
            except queue.Empty:
                yield {"type": "ping"}
                continue
            if event is None:
                yield {"type": "completed"}
                return
            yield event.to_dict()
    finally:
        with buf.lock:
            if listener in buf.listeners:
                buf.listeners.remove(listener)


def _get(execution_id: int) -> _Buffer | None:
    with _buffers_lock:
        return _buffers.get(execution_id)


def _persist(execution_id: int, buf: _Buffer) -> None:
    if not buf.events:
        _drop(execution_id)
        return
    with session_scope() as session:
        for ev in buf.events:
            session.add(
                ExecutionLog(
                    execution_id=execution_id,
                    timestamp=ev.timestamp,
                    level=ev.level,
                    message=ev.message,
                    group_name=ev.group,
                    indent=ev.indent,
                )
            )
    _drop(execution_id)


def _drop(execution_id: int) -> None:
    with _buffers_lock:
        _buffers.pop(execution_id, None)


def reconcile_orphans() -> int:
    """Marcar como error las ejecuciones que quedaron en running tras un crash."""
    from datetime import timedelta
    from models import AgentExecution

    cutoff = datetime.utcnow() - timedelta(hours=1)
    fixed = 0
    with session_scope() as session:
        rows = (
            session.query(AgentExecution)
            .filter(AgentExecution.status == "running", AgentExecution.started_at < cutoff)
            .all()
        )
        for row in rows:
            row.status = "error"
            row.error_message = "process killed (reconciled at startup)"
            row.completed_at = datetime.utcnow()
            fixed += 1
    return fixed
