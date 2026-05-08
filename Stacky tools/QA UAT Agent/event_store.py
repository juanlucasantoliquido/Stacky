"""
event_store.py — Persistencia dual SQLite + JSONL para eventos de QA UAT Agent.

Principio de persistencia robusta:
  1. Todo evento se escribe en events.sqlite Y events.jsonl.
  2. Si SQLite falla → escribir en JSONL y en dead_letters.jsonl, continuar.
  3. Si JSONL también falla → BLOCKED (el run se detiene).

Thread-safe. Nunca lanza excepciones al exterior — los errores internos
se registran en dead_letters.jsonl o en el log de Python.

Estructura de archivos por run:
  evidence/<ticket_id>/<run_id>/
  ├── events.sqlite
  ├── events.jsonl
  └── dead_letters.jsonl
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_py_logger = logging.getLogger("stacky.qa_uat.event_store")

# ── Schema SQLite ──────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL UNIQUE,
    schema_version  TEXT NOT NULL DEFAULT '1.0',
    run_id          TEXT NOT NULL,
    ticket_id       TEXT,
    trace_id        TEXT,
    span_id         TEXT,
    parent_event_id TEXT,
    causation_event_id TEXT,
    correlation_id  TEXT,
    seq_global      INTEGER,
    seq_run         INTEGER NOT NULL,
    ts              TEXT NOT NULL,
    monotonic_ms    INTEGER,
    source          TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    category        TEXT NOT NULL,
    stage           TEXT,
    action          TEXT,
    status          TEXT,
    level           TEXT NOT NULL DEFAULT 'info',
    message         TEXT NOT NULL,
    payload         TEXT,          -- JSON string
    artifact_refs   TEXT,          -- JSON array string
    learning_eligible INTEGER DEFAULT 0,
    redaction_applied INTEGER DEFAULT 0,
    redacted_fields TEXT,          -- JSON array string
    duration_ms     INTEGER,
    raw_json        TEXT NOT NULL  -- full event JSON for exact replay
);

CREATE INDEX IF NOT EXISTS idx_events_run_id    ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_ticket_id ON events(ticket_id);
CREATE INDEX IF NOT EXISTS idx_events_category  ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_stage     ON events(stage);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_source    ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_ts        ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_seq_run   ON events(seq_run);

CREATE TABLE IF NOT EXISTS artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id     TEXT NOT NULL UNIQUE,
    run_id          TEXT NOT NULL,
    ticket_id       TEXT,
    artifact_type   TEXT NOT NULL,
    path            TEXT NOT NULL,
    sha256          TEXT,
    size_bytes      INTEGER,
    created_by_event_id TEXT,
    scenario_id     TEXT,
    ts              TEXT NOT NULL,
    extra           TEXT           -- JSON
);

CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type   ON artifacts(artifact_type);

CREATE TABLE IF NOT EXISTS run_state (
    run_id          TEXT PRIMARY KEY,
    ticket_id       TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    current_stage   TEXT,
    last_completed_stage TEXT,
    last_event_id   TEXT,
    resume_from     TEXT,
    blocked_reason  TEXT,
    waiting_for_human INTEGER DEFAULT 0,
    started_at      TEXT,
    updated_at      TEXT,
    extra           TEXT           -- JSON
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    stage           TEXT NOT NULL,
    status          TEXT NOT NULL,  -- 'completed' | 'failed' | 'blocked'
    event_id        TEXT,
    ts              TEXT NOT NULL,
    payload         TEXT,           -- JSON
    UNIQUE(run_id, stage)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_run_id ON checkpoints(run_id);
"""


# ── EventStore ────────────────────────────────────────────────────────────────

class EventStore:
    """
    Almacén dual de eventos: SQLite + JSONL con fallback a dead_letters.

    Un EventStore por run_id. Obtener via EventStoreFactory.get().
    """

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self._lock = threading.Lock()
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._jsonl_fh: Optional[Any] = None
        self._dead_fh: Optional[Any] = None
        self._sqlite_ok = False
        self._jsonl_ok = False
        self._closed = False
        self._init()

    def _init(self) -> None:
        """Inicializar directorio, SQLite y JSONL."""
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            _py_logger.error("EventStore: no se puede crear directorio %s: %s", self.run_dir, exc)
            return

        # SQLite
        try:
            db_path = self.run_dir / "events.sqlite"
            self._sqlite_conn = sqlite3.connect(str(db_path), check_same_thread=False)
            self._sqlite_conn.executescript(_DDL)
            self._sqlite_conn.commit()
            self._sqlite_ok = True
            _py_logger.debug("EventStore SQLite: %s", db_path)
        except Exception as exc:
            _py_logger.warning("EventStore: SQLite init falló: %s", exc)
            self._sqlite_ok = False

        # JSONL
        try:
            jsonl_path = self.run_dir / "events.jsonl"
            self._jsonl_fh = open(jsonl_path, "a", encoding="utf-8", buffering=1)  # noqa: WPS515
            self._jsonl_ok = True
            _py_logger.debug("EventStore JSONL: %s", jsonl_path)
        except Exception as exc:
            _py_logger.warning("EventStore: JSONL init falló: %s", exc)
            self._jsonl_ok = False

        # Dead letters (abrir lazy)
        try:
            dead_path = self.run_dir / "dead_letters.jsonl"
            self._dead_fh = open(dead_path, "a", encoding="utf-8", buffering=1)  # noqa: WPS515
        except Exception as exc:
            _py_logger.warning("EventStore: dead_letters init falló: %s", exc)

    # ── Escritura de eventos ───────────────────────────────────────────────────

    def write_event(self, event: dict) -> bool:
        """
        Escribir un evento en SQLite + JSONL.

        Retorna True si persistió al menos en JSONL.
        Retorna False si ambas escrituras fallaron (caller debe BLOCK el run).
        """
        with self._lock:
            if self._closed:
                _py_logger.warning("EventStore: write_event en store cerrado")
                return False

            raw_json = json.dumps(event, ensure_ascii=False)
            sqlite_written = False
            jsonl_written = False

            # Intentar SQLite
            if self._sqlite_ok and self._sqlite_conn is not None:
                try:
                    self._write_sqlite(event, raw_json)
                    sqlite_written = True
                except Exception as exc:
                    _py_logger.warning("EventStore: SQLite write falló: %s", exc)
                    self._sqlite_ok = False
                    self._write_dead_letter(event, raw_json, error=str(exc), backend="sqlite")

            # Intentar JSONL (siempre, independiente de SQLite)
            if self._jsonl_fh is not None:
                try:
                    self._jsonl_fh.write(raw_json + "\n")
                    jsonl_written = True
                except Exception as exc:
                    _py_logger.error("EventStore: JSONL write falló: %s", exc)
                    self._write_dead_letter(event, raw_json, error=str(exc), backend="jsonl")

            return jsonl_written or sqlite_written

    def _write_sqlite(self, event: dict, raw_json: str) -> None:
        """Insertar evento en tabla events de SQLite."""
        conn = self._sqlite_conn
        redaction = event.get("redaction", {})
        conn.execute(
            """
            INSERT OR IGNORE INTO events (
                event_id, schema_version, run_id, ticket_id, trace_id, span_id,
                parent_event_id, causation_event_id, correlation_id,
                seq_global, seq_run, ts, monotonic_ms,
                source, event_type, category, stage, action, status, level, message,
                payload, artifact_refs, learning_eligible,
                redaction_applied, redacted_fields, duration_ms, raw_json
            ) VALUES (
                :event_id, :schema_version, :run_id, :ticket_id, :trace_id, :span_id,
                :parent_event_id, :causation_event_id, :correlation_id,
                :seq_global, :seq_run, :ts, :monotonic_ms,
                :source, :event_type, :category, :stage, :action, :status, :level, :message,
                :payload, :artifact_refs, :learning_eligible,
                :redaction_applied, :redacted_fields, :duration_ms, :raw_json
            )
            """,
            {
                "event_id": event.get("event_id", ""),
                "schema_version": event.get("schema_version", "1.0"),
                "run_id": event.get("run_id", ""),
                "ticket_id": str(event.get("ticket_id", "")),
                "trace_id": event.get("trace_id"),
                "span_id": event.get("span_id"),
                "parent_event_id": event.get("parent_event_id"),
                "causation_event_id": event.get("causation_event_id"),
                "correlation_id": event.get("correlation_id"),
                "seq_global": event.get("seq_global"),
                "seq_run": event.get("seq_run", 0),
                "ts": event.get("ts", ""),
                "monotonic_ms": event.get("monotonic_ms"),
                "source": event.get("source", ""),
                "event_type": event.get("event_type", ""),
                "category": event.get("category", ""),
                "stage": event.get("stage"),
                "action": event.get("action"),
                "status": event.get("status"),
                "level": event.get("level", "info"),
                "message": event.get("message", ""),
                "payload": json.dumps(event.get("payload", {}), ensure_ascii=False),
                "artifact_refs": json.dumps(event.get("artifact_refs", []), ensure_ascii=False),
                "learning_eligible": 1 if event.get("learning_eligible") else 0,
                "redaction_applied": 1 if redaction.get("applied") else 0,
                "redacted_fields": json.dumps(redaction.get("fields", []), ensure_ascii=False),
                "duration_ms": event.get("duration_ms"),
                "raw_json": raw_json,
            },
        )
        conn.commit()

    def _write_dead_letter(self, event: dict, raw_json: str, error: str, backend: str) -> None:
        """Escribir en dead_letters.jsonl cuando falla la persistencia principal."""
        if self._dead_fh is None:
            return
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "backend_failed": backend,
            "error": error,
            "event_id": event.get("event_id", ""),
            "run_id": event.get("run_id", ""),
            "raw_json": raw_json[:2000],  # truncar para no inflar el archivo
        }
        try:
            self._dead_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ── Artifact registry ──────────────────────────────────────────────────────

    def register_artifact(self, artifact: dict) -> bool:
        """Registrar un artifact en la tabla artifacts de SQLite."""
        if not self._sqlite_ok or self._sqlite_conn is None:
            return False
        try:
            with self._lock:
                self._sqlite_conn.execute(
                    """
                    INSERT OR REPLACE INTO artifacts (
                        artifact_id, run_id, ticket_id, artifact_type, path,
                        sha256, size_bytes, created_by_event_id, scenario_id, ts, extra
                    ) VALUES (
                        :artifact_id, :run_id, :ticket_id, :artifact_type, :path,
                        :sha256, :size_bytes, :created_by_event_id, :scenario_id, :ts, :extra
                    )
                    """,
                    {
                        "artifact_id": artifact.get("artifact_id", ""),
                        "run_id": artifact.get("run_id", ""),
                        "ticket_id": str(artifact.get("ticket_id", "")),
                        "artifact_type": artifact.get("type", artifact.get("artifact_type", "")),
                        "path": artifact.get("path", ""),
                        "sha256": artifact.get("sha256"),
                        "size_bytes": artifact.get("size_bytes"),
                        "created_by_event_id": artifact.get("created_by_event_id"),
                        "scenario_id": artifact.get("scenario_id"),
                        "ts": artifact.get("ts", datetime.now(timezone.utc).isoformat()),
                        "extra": json.dumps(artifact.get("extra", {}), ensure_ascii=False),
                    },
                )
                self._sqlite_conn.commit()
            return True
        except Exception as exc:
            _py_logger.warning("EventStore: artifact register falló: %s", exc)
            return False

    # ── Run state ─────────────────────────────────────────────────────────────

    def upsert_run_state(self, run_id: str, **kwargs: Any) -> bool:
        """Actualizar run_state en SQLite."""
        if not self._sqlite_ok or self._sqlite_conn is None:
            return False
        try:
            with self._lock:
                now = datetime.now(timezone.utc).isoformat()
                self._sqlite_conn.execute(
                    """
                    INSERT INTO run_state (run_id, ticket_id, status, current_stage,
                        last_completed_stage, last_event_id, resume_from, blocked_reason,
                        waiting_for_human, started_at, updated_at, extra)
                    VALUES (:run_id, :ticket_id, :status, :current_stage,
                        :last_completed_stage, :last_event_id, :resume_from, :blocked_reason,
                        :waiting_for_human, :started_at, :updated_at, :extra)
                    ON CONFLICT(run_id) DO UPDATE SET
                        ticket_id            = COALESCE(:ticket_id, ticket_id),
                        status               = COALESCE(:status, status),
                        current_stage        = COALESCE(:current_stage, current_stage),
                        last_completed_stage = COALESCE(:last_completed_stage, last_completed_stage),
                        last_event_id        = COALESCE(:last_event_id, last_event_id),
                        resume_from          = COALESCE(:resume_from, resume_from),
                        blocked_reason       = COALESCE(:blocked_reason, blocked_reason),
                        waiting_for_human    = COALESCE(:waiting_for_human, waiting_for_human),
                        updated_at           = :updated_at,
                        extra                = COALESCE(:extra, extra)
                    """,
                    {
                        "run_id": run_id,
                        "ticket_id": str(kwargs.get("ticket_id", "")),
                        "status": kwargs.get("status"),
                        "current_stage": kwargs.get("current_stage"),
                        "last_completed_stage": kwargs.get("last_completed_stage"),
                        "last_event_id": kwargs.get("last_event_id"),
                        "resume_from": kwargs.get("resume_from"),
                        "blocked_reason": kwargs.get("blocked_reason"),
                        "waiting_for_human": 1 if kwargs.get("waiting_for_human") else 0,
                        "started_at": kwargs.get("started_at", now),
                        "updated_at": now,
                        "extra": json.dumps(kwargs.get("extra", {}), ensure_ascii=False),
                    },
                )
                self._sqlite_conn.commit()
            return True
        except Exception as exc:
            _py_logger.warning("EventStore: run_state upsert falló: %s", exc)
            return False

    def upsert_checkpoint(self, run_id: str, stage: str, status: str,
                          event_id: Optional[str] = None, payload: Optional[dict] = None) -> bool:
        """Escribir o actualizar checkpoint de stage en SQLite."""
        if not self._sqlite_ok or self._sqlite_conn is None:
            return False
        try:
            with self._lock:
                self._sqlite_conn.execute(
                    """
                    INSERT INTO checkpoints (run_id, stage, status, event_id, ts, payload)
                    VALUES (:run_id, :stage, :status, :event_id, :ts, :payload)
                    ON CONFLICT(run_id, stage) DO UPDATE SET
                        status   = :status,
                        event_id = COALESCE(:event_id, event_id),
                        ts       = :ts,
                        payload  = COALESCE(:payload, payload)
                    """,
                    {
                        "run_id": run_id,
                        "stage": stage,
                        "status": status,
                        "event_id": event_id,
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "payload": json.dumps(payload or {}, ensure_ascii=False),
                    },
                )
                self._sqlite_conn.commit()
            return True
        except Exception as exc:
            _py_logger.warning("EventStore: checkpoint upsert falló: %s", exc)
            return False

    # ── Query helpers ──────────────────────────────────────────────────────────

    def get_events(self, run_id: str, category: Optional[str] = None,
                   stage: Optional[str] = None, limit: int = 10_000) -> list[dict]:
        """Consultar eventos de un run desde SQLite."""
        if not self._sqlite_ok or self._sqlite_conn is None:
            return []
        try:
            with self._lock:
                clauses = ["run_id = ?"]
                params: list = [run_id]
                if category:
                    clauses.append("category = ?")
                    params.append(category)
                if stage:
                    clauses.append("stage = ?")
                    params.append(stage)
                where = " AND ".join(clauses)
                cursor = self._sqlite_conn.execute(
                    f"SELECT raw_json FROM events WHERE {where} ORDER BY seq_run LIMIT ?",
                    params + [limit],
                )
                return [json.loads(row[0]) for row in cursor.fetchall()]
        except Exception as exc:
            _py_logger.warning("EventStore: get_events falló: %s", exc)
            return []

    def count_events(self, run_id: str) -> int:
        """Contar eventos de un run."""
        if not self._sqlite_ok or self._sqlite_conn is None:
            return 0
        try:
            with self._lock:
                cursor = self._sqlite_conn.execute(
                    "SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,)
                )
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Forzar flush de buffers."""
        with self._lock:
            if self._jsonl_fh:
                try:
                    self._jsonl_fh.flush()
                except Exception:
                    pass
            if self._dead_fh:
                try:
                    self._dead_fh.flush()
                except Exception:
                    pass

    def close(self) -> None:
        """Cerrar todos los handles. Idempotente."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for fh in (self._jsonl_fh, self._dead_fh):
                if fh is not None:
                    try:
                        fh.flush()
                        fh.close()
                    except Exception:
                        pass
            if self._sqlite_conn is not None:
                try:
                    self._sqlite_conn.close()
                except Exception:
                    pass
            self._sqlite_conn = None
            self._jsonl_fh = None
            self._dead_fh = None

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ── Factory (singleton por run_dir) ───────────────────────────────────────────

_store_registry: dict[str, EventStore] = {}
_store_registry_lock = threading.Lock()


class EventStoreFactory:
    @staticmethod
    def get(run_dir: Path) -> EventStore:
        """Obtener o crear el EventStore para un run_dir dado (singleton)."""
        key = str(run_dir.resolve())
        with _store_registry_lock:
            if key not in _store_registry:
                _store_registry[key] = EventStore(run_dir)
            return _store_registry[key]

    @staticmethod
    def close_all() -> None:
        """Cerrar todos los stores registrados."""
        with _store_registry_lock:
            for store in _store_registry.values():
                store.close()
            _store_registry.clear()
