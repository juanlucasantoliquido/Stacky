"""
Stacky Centralized Structured Logger
=====================================

Writes every significant event across the entire Stacky Agents system to the
`system_logs` table. All calls are non-blocking: events are enqueued and
persisted asynchronously by a dedicated background writer thread.

Fail-safe guarantee: if the queue is full (extreme load), the event is written
synchronously so NO event is ever silently dropped.

Usage
-----
    from services.stacky_logger import logger

    # Generic leveled methods
    logger.info("agent_runner", "agent_started", execution_id=42, ticket_id=7)
    logger.error("ado_client", "api_call_failed", exc=exc, ticket_id=7)

    # HTTP request / response pair (called from middleware)
    logger.request("GET", "/api/tickets", 200, 45, user="dev@local", request_id=rid)

    # Agent lifecycle events
    logger.agent_event("agent_completed", execution_id=42, ticket_id=7,
                       duration_ms=1234, output_data={"chars": 400})

    # External integration calls (ADO, Git, etc.)
    logger.integration_call("ado", "create_comment", ticket_id=7, duration_ms=200)

    # New request ID (call in before_request hook)
    rid = logger.new_request_id()

Retention
---------
    Set SYSLOG_RETENTION_DAYS env var (default: 90).
    Call logger.purge_old_logs() periodically or via DELETE /api/logs/purge.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

_std = logging.getLogger("stacky.syslog")

# ── tunables ───────────────────────────────────────────────────────────────
INPUT_MAX_BYTES = 16_384        # 16 KB  — input / context payloads
OUTPUT_MAX_BYTES = 16_384       # 16 KB  — output payloads
ERROR_MAX_BYTES = 65_536        # 64 KB  — full stacktraces
QUEUE_MAX = 10_000              # max enqueued events before fail-safe sync write
BATCH_SIZE = 50                 # rows per DB flush
FLUSH_INTERVAL_SEC = 2.0        # max seconds between DB flushes
RETENTION_DAYS = int(os.getenv("SYSLOG_RETENTION_DAYS", "90"))

# Keys whose values are redacted before persisting (case-insensitive match)
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password", "passwd", "token", "secret", "pat", "authorization",
    "x-api-key", "apikey", "api_key", "ado_pat", "copilot_token",
    "access_token", "refresh_token", "bearer",
})

_STOP = object()  # sentinel to stop the writer thread


@dataclass
class _FlushSignal:
    """Sentinel put into the queue to force an immediate flush.

    When the writer encounters it, it flushes the current batch and then
    sets ``done`` so that the caller of ``flush_now()`` can unblock.
    """
    done: threading.Event = field(default_factory=threading.Event)


# ── helpers ────────────────────────────────────────────────────────────────

def _truncate(value: Any, max_bytes: int) -> str | None:
    """Serialize value to JSON and truncate to max_bytes UTF-8 bytes."""
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "…[truncated]"


def _mask_dict(d: dict) -> dict:
    """Recursively redact sensitive keys, returning a new dict."""
    out: dict = {}
    for k, v in d.items():
        if k.lower() in _SENSITIVE_KEYS:
            out[k] = "***REDACTED***"
        elif isinstance(v, dict):
            out[k] = _mask_dict(v)
        elif isinstance(v, list):
            out[k] = [_mask_dict(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def _format_error(exc: BaseException | None) -> dict | None:
    if exc is None:
        return None
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }


# ── event dataclass ────────────────────────────────────────────────────────

@dataclass
class LogEvent:
    level: str
    source: str
    action: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    execution_id: int | None = None
    ticket_id: int | None = None
    user: str | None = None
    request_id: str | None = None
    method: str | None = None
    endpoint: str | None = None
    status_code: int | None = None
    duration_ms: int | None = None
    input_data: Any = None
    output_data: Any = None
    error_exc: BaseException | None = None
    context_data: dict | None = None
    tags: list[str] | None = None


# ── core logger ────────────────────────────────────────────────────────────

class _StackyLogger:
    """Singleton structured logger with async background DB writer."""

    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue(maxsize=QUEUE_MAX)
        self._local = threading.local()
        self._thread = threading.Thread(
            target=self._writer_loop,
            daemon=True,
            name="stacky-syslog-writer",
        )
        self._thread.start()
        atexit.register(self._flush_on_exit)

    # ── request correlation ─────────────────────────────────────────────

    @property
    def current_request_id(self) -> str | None:
        return getattr(self._local, "request_id", None)

    def new_request_id(self) -> str:
        """Generate and store a new UUID for the current thread's request."""
        rid = str(uuid.uuid4())
        self._local.request_id = rid
        return rid

    def clear_request_id(self) -> None:
        self._local.request_id = None

    # ── public logging API ──────────────────────────────────────────────

    def debug(self, source: str, action: str, **kwargs: Any) -> None:
        self._emit("DEBUG", source, action, **kwargs)

    def info(self, source: str, action: str, **kwargs: Any) -> None:
        self._emit("INFO", source, action, **kwargs)

    def warning(self, source: str, action: str, **kwargs: Any) -> None:
        self._emit("WARNING", source, action, **kwargs)

    def error(self, source: str, action: str, **kwargs: Any) -> None:
        self._emit("ERROR", source, action, **kwargs)

    def critical(self, source: str, action: str, **kwargs: Any) -> None:
        self._emit("CRITICAL", source, action, **kwargs)

    # ── specialised helpers ─────────────────────────────────────────────

    def request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration_ms: int,
        *,
        user: str | None = None,
        request_id: str | None = None,
        input_data: Any = None,
        output_data: Any = None,
        tags: list[str] | None = None,
    ) -> None:
        """Log a completed HTTP request/response pair."""
        if status_code >= 500:
            level = "ERROR"
        elif status_code >= 400:
            level = "WARNING"
        else:
            level = "INFO"
        self._enqueue(LogEvent(
            level=level,
            source="http.middleware",
            action="http_request",
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            duration_ms=duration_ms,
            user=user,
            request_id=request_id or self.current_request_id,
            input_data=input_data,
            output_data=output_data,
            tags=tags or ["http"],
        ))

    def agent_event(
        self,
        action: str,
        execution_id: int,
        ticket_id: int | None = None,
        user: str | None = None,
        *,
        level: str = "INFO",
        input_data: Any = None,
        output_data: Any = None,
        error_exc: BaseException | None = None,
        context_data: dict | None = None,
        duration_ms: int | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Log an agent lifecycle event (started, completed, failed, cached, cancelled)."""
        self._enqueue(LogEvent(
            level=level,
            source="agent_runner",
            action=action,
            execution_id=execution_id,
            ticket_id=ticket_id,
            user=user,
            request_id=self.current_request_id,
            input_data=input_data,
            output_data=output_data,
            error_exc=error_exc,
            context_data=context_data,
            duration_ms=duration_ms,
            tags=tags or ["agent"],
        ))

    def integration_call(
        self,
        service: str,
        action: str,
        *,
        level: str = "INFO",
        input_data: Any = None,
        output_data: Any = None,
        error_exc: BaseException | None = None,
        duration_ms: int | None = None,
        execution_id: int | None = None,
        ticket_id: int | None = None,
        user: str | None = None,
    ) -> None:
        """Log a call to an external service (ADO, Git, LLM, BD, etc.)."""
        self._enqueue(LogEvent(
            level=level,
            source=f"integration.{service}",
            action=action,
            execution_id=execution_id,
            ticket_id=ticket_id,
            user=user,
            request_id=self.current_request_id,
            input_data=input_data,
            output_data=output_data,
            error_exc=error_exc,
            duration_ms=duration_ms,
            tags=["integration", service],
        ))

    # ── internal ────────────────────────────────────────────────────────

    def _emit(self, level: str, source: str, action: str, **kwargs: Any) -> None:
        exc: BaseException | None = kwargs.pop("exc", None) or kwargs.pop("error_exc", None)
        tags: list[str] | None = kwargs.pop("tags", None)
        input_data: Any = kwargs.pop("input_data", None)
        output_data: Any = kwargs.pop("output_data", None)
        execution_id: int | None = kwargs.pop("execution_id", None)
        ticket_id: int | None = kwargs.pop("ticket_id", None)
        user: str | None = kwargs.pop("user", None)
        request_id: str | None = kwargs.pop("request_id", self.current_request_id)
        duration_ms: int | None = kwargs.pop("duration_ms", None)
        # remaining kwargs → context
        context_data: dict | None = dict(kwargs) if kwargs else None

        self._enqueue(LogEvent(
            level=level,
            source=source,
            action=action,
            execution_id=execution_id,
            ticket_id=ticket_id,
            user=user,
            request_id=request_id,
            duration_ms=duration_ms,
            input_data=input_data,
            output_data=output_data,
            error_exc=exc,
            context_data=context_data,
            tags=tags,
        ))

    def _enqueue(self, event: LogEvent) -> None:
        try:
            self._q.put_nowait(event)
        except queue.Full:
            _std.warning("syslog queue full — writing synchronously to avoid loss")
            self._persist_batch([event])

    # ── background writer ───────────────────────────────────────────────

    def _writer_loop(self) -> None:
        batch: list[LogEvent] = []
        last_flush = time.monotonic()

        while True:
            timeout = max(0.05, FLUSH_INTERVAL_SEC - (time.monotonic() - last_flush))
            try:
                event = self._q.get(timeout=timeout)
            except queue.Empty:
                event = None

            if event is _STOP:
                if batch:
                    self._persist_batch(batch)
                return

            if isinstance(event, _FlushSignal):
                # Flush current batch immediately, then signal the waiter
                if batch:
                    self._persist_batch(batch)
                    batch = []
                    last_flush = time.monotonic()
                event.done.set()
                continue

            if event is not None:
                batch.append(event)

            now = time.monotonic()
            should_flush = (
                len(batch) >= BATCH_SIZE
                or (now - last_flush) >= FLUSH_INTERVAL_SEC
            )
            if should_flush and batch:
                self._persist_batch(batch)
                batch = []
                last_flush = now

    def _persist_batch(self, events: list[LogEvent]) -> None:
        # Import here to avoid circular import at module load time
        from db import session_scope
        from models import SystemLog

        try:
            with session_scope() as session:
                for evt in events:
                    # Prepare and mask payload fields
                    inp = None
                    if evt.input_data is not None:
                        masked_in = _mask_dict(evt.input_data) if isinstance(evt.input_data, dict) else evt.input_data
                        inp = _truncate(masked_in, INPUT_MAX_BYTES)

                    out = None
                    if evt.output_data is not None:
                        masked_out = _mask_dict(evt.output_data) if isinstance(evt.output_data, dict) else evt.output_data
                        out = _truncate(masked_out, OUTPUT_MAX_BYTES)

                    err = None
                    error_dict = _format_error(evt.error_exc)
                    if error_dict:
                        err = _truncate(error_dict, ERROR_MAX_BYTES)

                    ctx = None
                    if evt.context_data:
                        masked_ctx = _mask_dict(evt.context_data)
                        ctx = _truncate(masked_ctx, INPUT_MAX_BYTES)

                    row = SystemLog(
                        timestamp=evt.timestamp,
                        level=evt.level,
                        source=evt.source,
                        action=evt.action,
                        execution_id=evt.execution_id,
                        ticket_id=evt.ticket_id,
                        user=evt.user,
                        request_id=evt.request_id,
                        method=evt.method,
                        endpoint=evt.endpoint,
                        status_code=evt.status_code,
                        duration_ms=evt.duration_ms,
                        input_json=inp,
                        output_json=out,
                        error_json=err,
                        context_json=ctx,
                        tags_json=json.dumps(evt.tags) if evt.tags else None,
                    )
                    session.add(row)
        except Exception:
            _std.exception("syslog failed to persist batch of %d events", len(events))

    def _flush_on_exit(self) -> None:
        """Drain remaining queued events before process exits."""
        remaining: list[LogEvent] = []
        while True:
            try:
                evt = self._q.get_nowait()
                if evt is not _STOP and evt is not None:
                    remaining.append(evt)
            except queue.Empty:
                break
        if remaining:
            self._persist_batch(remaining)

    def flush_now(self, timeout: float = 5.0) -> None:
        """Force an immediate flush of all pending events.

        Puts a ``_FlushSignal`` sentinel at the END of the queue.  When the
        background writer reaches it, it flushes its current in-memory batch
        (which contains all events enqueued before this call) and then signals
        completion.  This call blocks until the writer confirms the flush.

        Intended for tests and graceful shutdown.
        """
        signal = _FlushSignal()
        self._q.put(signal)
        signal.done.wait(timeout=timeout)

    # ── maintenance ─────────────────────────────────────────────────────

    def purge_old_logs(self, days: int = RETENTION_DAYS) -> int:
        """Delete SystemLog rows older than `days` days. Returns count deleted."""
        from db import session_scope
        from models import SystemLog

        cutoff = datetime.utcnow() - timedelta(days=days)
        try:
            with session_scope() as session:
                deleted: int = (
                    session.query(SystemLog)
                    .filter(SystemLog.timestamp < cutoff)
                    .delete(synchronize_session=False)
                )
                return deleted
        except Exception:
            _std.exception("syslog purge failed")
            return 0


# ── singleton ───────────────────────────────────────────────────────────────

logger = _StackyLogger()
