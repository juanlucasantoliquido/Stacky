"""
pipeline_events.py — Bus de eventos estructurados del pipeline Stacky.

Persistencia: JSONL rotativo por día en data/pipeline_events_YYYY-MM-DD.jsonl
Retención: 30 días (archivos viejos se limpian al levantar el módulo).

Arquitectura:
    - ``PipelineEvent``       → modelo Pydantic canónico (validado, serializable).
    - ``EventStore``          → writer JSONL thread-safe con queue asíncrona.
    - ``emit(...)``           → API pública de alto nivel, fire-and-forget, nunca
                                 rompe el caller. Dispara a disco **y** al SSE bus.

Correlación por ``execution_id`` (UUID4 corto de 8 chars en logs, completo en JSONL).

Compatible con Python 3.11+, pydantic v2.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

try:
    from pydantic import BaseModel, Field, ConfigDict
except Exception as _exc:  # pragma: no cover - pydantic es requerido pero no rompemos el import
    BaseModel = object  # type: ignore[misc,assignment]
    Field = lambda *a, **kw: None  # type: ignore[assignment]
    ConfigDict = dict  # type: ignore[misc,assignment]
    logging.getLogger("stacky.events").warning(
        "pipeline_events: pydantic no disponible (%s) — eventos en modo degradado", _exc,
    )

logger = logging.getLogger("stacky.events")

# ── Paths ────────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).resolve().parent
_DATA_DIR = _BASE_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_RETENTION_DAYS = 30
_FILE_PREFIX    = "pipeline_events_"
_FILE_SUFFIX    = ".jsonl"
_LEGACY_FILE    = _DATA_DIR / "pipeline_events.jsonl"  # stub compat

EventKind = Literal[
    "action_started",
    "action_progress",
    "action_done",
    "action_error",
    "notification",
    "state_transition",
    "estimation_recorded",
    "estimation_actualized",
]

EventPhase = Literal[
    "pm", "dev", "tester", "dba", "tl", "deploy", "sync", "other"
]

ErrorKind = Literal[
    "technical", "functional", "auth", "network", "data", "user"
]


# ── Modelo canónico ──────────────────────────────────────────────────────────

class PipelineEvent(BaseModel):  # type: ignore[misc]
    """Evento estructurado del pipeline (esquema canónico)."""

    model_config = ConfigDict(extra="ignore")  # type: ignore[call-arg]

    ts: datetime
    execution_id: str
    parent_execution_id: str | None = None
    kind: EventKind
    ticket_id: str | None = None
    project: str | None = None
    action: str | None = None
    subaction: str | None = None
    phase: EventPhase | None = None
    pct: int | None = None
    duration_ms: int | None = None
    error_kind: ErrorKind | None = None
    message: str | None = None
    user_friendly: str | None = None
    stack: str | None = None
    detail: str | None = None
    correlation: dict[str, str] = Field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────

def new_execution_id() -> str:
    """UUID4 completo — se trunca a 8 chars solo en logs."""
    return str(uuid.uuid4())


def short_id(execution_id: str) -> str:
    """Primeros 8 chars del execution_id para logs humanos."""
    return execution_id[:8] if execution_id else "-"


def _current_file_path() -> Path:
    return _DATA_DIR / f"{_FILE_PREFIX}{date.today().isoformat()}{_FILE_SUFFIX}"


def _serialize(event: PipelineEvent) -> str:
    """Serializa un event a una línea JSON (sin BOM, UTF-8)."""
    try:
        data = event.model_dump(mode="json", exclude_none=True)  # type: ignore[attr-defined]
    except AttributeError:
        # Fallback para entornos sin pydantic — reconstruye desde __dict__
        data = {k: v for k, v in event.__dict__.items() if v is not None}
        if isinstance(data.get("ts"), datetime):
            data["ts"] = data["ts"].isoformat()
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


# ── Event store (writer async) ───────────────────────────────────────────────

class EventStore:
    """
    Writer JSONL thread-safe con queue interna.

    - ``emit()``   pone el evento en una queue y retorna inmediatamente.
    - Un worker daemon dedicado drena la queue y escribe a disco.
    - Nunca propaga excepciones al caller — cualquier error se loguea a DEBUG.
    - Expone ``subscribe()`` para que el SSE bus reciba eventos en vivo.
    """

    _singleton: "EventStore | None" = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self._queue: queue.Queue[PipelineEvent | None] = queue.Queue(maxsize=10_000)
        self._write_lock = threading.Lock()
        self._subscribers: list[queue.Queue[PipelineEvent]] = []
        self._subscribers_lock = threading.Lock()
        self._started = False
        self._worker: threading.Thread | None = None
        self._cleanup_done = False

    # ── Singleton accessor ────────────────────────────────────────────────
    @classmethod
    def instance(cls) -> "EventStore":
        with cls._singleton_lock:
            if cls._singleton is None:
                cls._singleton = cls()
                cls._singleton.start()
            return cls._singleton

    # ── Lifecycle ─────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._cleanup_old_files()
        self._worker = threading.Thread(
            target=self._drain_loop,
            daemon=True,
            name="stacky-events-writer",
        )
        self._worker.start()
        logger.debug("EventStore worker iniciado (file=%s)", _current_file_path().name)

    # ── Emit API ──────────────────────────────────────────────────────────
    def emit(self, event: PipelineEvent) -> None:
        """Encola un evento para persistencia + broadcast SSE. No propaga errores."""
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.debug("EventStore queue llena — descartando evento")
        except Exception as e:  # pragma: no cover — defensivo
            logger.debug("EventStore.emit falló: %s", e)

    # ── Subscribers (SSE) ─────────────────────────────────────────────────
    def subscribe(self, maxsize: int = 200) -> queue.Queue[PipelineEvent]:
        q: queue.Queue[PipelineEvent] = queue.Queue(maxsize=maxsize)
        with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[PipelineEvent]) -> None:
        with self._subscribers_lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    # ── Reads ─────────────────────────────────────────────────────────────
    def read_events(
        self,
        *,
        ticket_id: str | None = None,
        kind: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
        days_back: int = 7,
    ) -> list[dict[str, Any]]:
        """Lee eventos del JSONL filtrando por ticket/kind/since. Barre hasta `days_back` archivos."""
        out: list[dict[str, Any]] = []
        today = date.today()
        for offset in range(days_back):
            d = today - timedelta(days=offset)
            p = _DATA_DIR / f"{_FILE_PREFIX}{d.isoformat()}{_FILE_SUFFIX}"
            if not p.exists():
                continue
            try:
                with p.open("r", encoding="utf-8") as f:
                    for raw in f:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            ev = json.loads(raw)
                        except Exception:
                            continue
                        if ticket_id and ev.get("ticket_id") != ticket_id:
                            continue
                        if kind and ev.get("kind") != kind:
                            continue
                        if since:
                            try:
                                ts = datetime.fromisoformat(ev.get("ts", ""))
                                if ts < since:
                                    continue
                            except Exception:
                                pass
                        out.append(ev)
            except Exception as e:  # pragma: no cover
                logger.debug("read_events no pudo leer %s: %s", p, e)
        # Ordenar ascendente por ts y limitar a los últimos ``limit``
        out.sort(key=lambda e: e.get("ts", ""))
        if limit and len(out) > limit:
            out = out[-limit:]
        return out

    # ── Internals ─────────────────────────────────────────────────────────
    def _drain_loop(self) -> None:
        while True:
            try:
                ev = self._queue.get(timeout=30)
            except queue.Empty:
                continue
            if ev is None:
                continue
            self._persist(ev)
            self._broadcast(ev)

    def _persist(self, event: PipelineEvent) -> None:
        try:
            path = _current_file_path()
            line = _serialize(event)
            with self._write_lock:
                with path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:  # pragma: no cover — defensivo
            logger.debug("EventStore._persist falló: %s", e)

    def _broadcast(self, event: PipelineEvent) -> None:
        with self._subscribers_lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                # Drop el evento para ese subscriber — cliente muy lento
                logger.debug("Subscriber queue full — drop evento")
            except Exception as e:  # pragma: no cover
                logger.debug("broadcast falló a subscriber: %s", e)

    def _cleanup_old_files(self) -> None:
        if self._cleanup_done:
            return
        self._cleanup_done = True
        try:
            cutoff = date.today() - timedelta(days=_RETENTION_DAYS)
            for p in _DATA_DIR.glob(f"{_FILE_PREFIX}*{_FILE_SUFFIX}"):
                try:
                    stem = p.stem.replace(_FILE_PREFIX, "")
                    d = date.fromisoformat(stem)
                    if d < cutoff:
                        p.unlink(missing_ok=True)
                        logger.debug("EventStore rotación: eliminado %s", p.name)
                except Exception:
                    continue
        except Exception as e:  # pragma: no cover
            logger.debug("cleanup old files falló: %s", e)


# ── API pública de alto nivel ────────────────────────────────────────────────

def emit(
    *,
    kind: EventKind,
    execution_id: str | None = None,
    parent_execution_id: str | None = None,
    ticket_id: str | None = None,
    project: str | None = None,
    action: str | None = None,
    subaction: str | None = None,
    phase: EventPhase | None = None,
    pct: int | None = None,
    duration_ms: int | None = None,
    error_kind: ErrorKind | None = None,
    message: str | None = None,
    user_friendly: str | None = None,
    stack: str | None = None,
    detail: str | None = None,
    correlation: dict[str, str] | None = None,
    ts: datetime | None = None,
) -> PipelineEvent | None:
    """
    Emite un evento al bus. Fire-and-forget: nunca rompe el caller.

    Retorna el PipelineEvent emitido (útil para tests) o ``None`` si falló la construcción.
    """
    try:
        event = PipelineEvent(
            ts=ts or datetime.now(timezone.utc),
            execution_id=execution_id or new_execution_id(),
            parent_execution_id=parent_execution_id,
            kind=kind,
            ticket_id=ticket_id,
            project=project,
            action=action,
            subaction=subaction,
            phase=phase,
            pct=pct,
            duration_ms=duration_ms,
            error_kind=error_kind,
            message=message,
            user_friendly=user_friendly,
            stack=stack,
            detail=detail,
            correlation=correlation or {},
        )
    except Exception as e:
        logger.debug("pipeline_events.emit: construcción de evento falló: %s", e)
        return None

    EventStore.instance().emit(event)
    return event


def read_events(**kwargs: Any) -> list[dict[str, Any]]:
    """Wrapper público sobre EventStore.read_events."""
    return EventStore.instance().read_events(**kwargs)


def subscribe(maxsize: int = 200) -> queue.Queue[PipelineEvent]:
    """Subscribe al bus para recibir eventos en vivo (usado por SSE)."""
    return EventStore.instance().subscribe(maxsize=maxsize)


def unsubscribe(q: queue.Queue[PipelineEvent]) -> None:
    EventStore.instance().unsubscribe(q)
