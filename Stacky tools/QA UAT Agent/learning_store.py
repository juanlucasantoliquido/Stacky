"""
learning_store.py — Store persistente de learnings gobernados para QA UAT.

DISEÑO:
  - Learnings son observaciones derivadas de runs reales.
  - Deben ser APROBADOS por un humano antes de aplicarse.
  - Un learning aprobado puede ser referenciado en futuros runs para
    mejorar selectores, flujos, datos, timeouts, etc.

PERSISTENCIA: data/learning_store.sqlite (compartido entre todos los runs).

SCHEMA:
  learning_candidates:
    id, learning_id, run_id, ticket_id, stage, category, title, description,
    evidence (JSON), proposed_by, source_event_ids (JSON), status, created_at,
    reviewed_at, reviewed_by, rejection_reason, applied_count, last_applied_at

  applied_learnings:
    id, learning_id, run_id, ticket_id, applied_at, applied_by,
    context (JSON), outcome (JSON)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_py_logger = logging.getLogger("stacky.qa_uat.learning_store")

_LEARNING_DB_PATH = Path(__file__).parent / "data" / "learning_store.sqlite"

_STATUSES = frozenset({"candidate", "approved", "rejected", "superseded"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_learning_id() -> str:
    return f"lrn-{uuid.uuid4().hex[:12]}"


_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS learning_candidates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    learning_id         TEXT NOT NULL UNIQUE,
    run_id              TEXT NOT NULL,
    ticket_id           TEXT,
    stage               TEXT,
    category            TEXT NOT NULL,     -- selector_fix | timeout_fix | flow_fix | data_fix | other
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    evidence            TEXT,              -- JSON
    proposed_by         TEXT DEFAULT 'system',
    source_event_ids    TEXT DEFAULT '[]', -- JSON array
    status              TEXT NOT NULL DEFAULT 'candidate',
    created_at          TEXT NOT NULL,
    reviewed_at         TEXT,
    reviewed_by         TEXT,
    rejection_reason    TEXT,
    applied_count       INTEGER DEFAULT 0,
    last_applied_at     TEXT
);

CREATE TABLE IF NOT EXISTS applied_learnings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    learning_id     TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    ticket_id       TEXT,
    applied_at      TEXT NOT NULL,
    applied_by      TEXT DEFAULT 'system',
    context         TEXT DEFAULT '{}',  -- JSON
    outcome         TEXT DEFAULT '{}',  -- JSON: {"status": "ok"|"failed", "details": "..."}
    FOREIGN KEY(learning_id) REFERENCES learning_candidates(learning_id)
);

CREATE INDEX IF NOT EXISTS idx_lrn_status   ON learning_candidates(status);
CREATE INDEX IF NOT EXISTS idx_lrn_category ON learning_candidates(category);
CREATE INDEX IF NOT EXISTS idx_lrn_run_id   ON learning_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_lrn_ticket   ON learning_candidates(ticket_id);
CREATE INDEX IF NOT EXISTS idx_applied_run  ON applied_learnings(run_id);
"""


class LearningStore:
    """
    Store de learnings gobernados.

    Uso:
        store = LearningStore()
        lid = store.add_candidate(
            run_id="uat-70-...", ticket_id=70,
            category="selector_fix",
            title="Selector incorrecto para btnGuardar",
            description="El botón tiene id dinámico, usar texto 'Guardar' en su lugar",
            evidence={"selector_tried": "#btn1", "fallback_works": "#btnGuardar"},
            source_event_ids=["evt-001", "evt-002"],
        )
        store.approve(lid, reviewed_by="juan")
        approved = store.get_approved(ticket_id=70)
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path or _LEARNING_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        try:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.executescript(_DDL)
            self._conn.commit()
        except Exception as exc:
            _py_logger.error("LearningStore: error inicializando DB: %s", exc)
            self._conn = None

    def _exec(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Cursor]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                return self._conn.execute(sql, params)
        except Exception as exc:
            _py_logger.warning("LearningStore exec error: %s", exc)
            return None

    def _commit(self) -> None:
        if self._conn:
            try:
                with self._lock:
                    self._conn.commit()
            except Exception:
                pass

    # ── Candidatos ─────────────────────────────────────────────────────────────

    def add_candidate(
        self,
        run_id: str,
        ticket_id: Any,
        category: str,
        title: str,
        description: str,
        *,
        stage: Optional[str] = None,
        evidence: Optional[dict] = None,
        proposed_by: str = "system",
        source_event_ids: Optional[list[str]] = None,
        learning_id: Optional[str] = None,
    ) -> str:
        """
        Agregar un candidato de learning.

        Devuelve el learning_id.
        Si ya existe un candidato con el mismo título y run_id, devuelve el existente.
        """
        lid = learning_id or _new_learning_id()
        now = _utcnow()

        # Idempotency check: mismo título + run_id
        existing = self._exec(
            "SELECT learning_id FROM learning_candidates WHERE run_id=? AND title=?",
            (run_id, title),
        )
        if existing:
            row = existing.fetchone()
            if row:
                return row[0]

        self._exec(
            """
            INSERT OR IGNORE INTO learning_candidates
            (learning_id, run_id, ticket_id, stage, category, title, description,
             evidence, proposed_by, source_event_ids, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                lid, run_id, str(ticket_id), stage, category, title, description,
                json.dumps(evidence or {}),
                proposed_by,
                json.dumps(source_event_ids or []),
                "candidate",
                now,
            ),
        )
        self._commit()
        return lid

    def approve(self, learning_id: str, *, reviewed_by: str = "operator") -> bool:
        """Aprobar un candidato. Solo puede aplicarse si está en 'candidate'."""
        cur = self._exec(
            "SELECT status FROM learning_candidates WHERE learning_id=?",
            (learning_id,),
        )
        if cur is None:
            return False
        row = cur.fetchone()
        if not row or row[0] not in ("candidate",):
            return False

        self._exec(
            """
            UPDATE learning_candidates
            SET status='approved', reviewed_at=?, reviewed_by=?
            WHERE learning_id=?
            """,
            (_utcnow(), reviewed_by, learning_id),
        )
        self._commit()
        return True

    def reject(
        self,
        learning_id: str,
        *,
        reviewed_by: str = "operator",
        rejection_reason: str = "",
    ) -> bool:
        """Rechazar un candidato."""
        cur = self._exec(
            "SELECT status FROM learning_candidates WHERE learning_id=?",
            (learning_id,),
        )
        if cur is None:
            return False
        row = cur.fetchone()
        if not row:
            return False

        self._exec(
            """
            UPDATE learning_candidates
            SET status='rejected', reviewed_at=?, reviewed_by=?, rejection_reason=?
            WHERE learning_id=?
            """,
            (_utcnow(), reviewed_by, rejection_reason, learning_id),
        )
        self._commit()
        return True

    # ── Consultas ──────────────────────────────────────────────────────────────

    def get_candidates(
        self,
        status: str = "candidate",
        ticket_id: Optional[Any] = None,
    ) -> list[dict]:
        clauses = ["status=?"]
        params: list = [status]
        if ticket_id is not None:
            clauses.append("ticket_id=?")
            params.append(str(ticket_id))
        cur = self._exec(
            f"SELECT * FROM learning_candidates WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
            tuple(params),
        )
        if cur is None:
            return []
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            for f in ("evidence", "source_event_ids"):
                if isinstance(d.get(f), str):
                    try:
                        d[f] = json.loads(d[f])
                    except Exception:
                        pass
            rows.append(d)
        return rows

    def get_approved(
        self,
        ticket_id: Optional[Any] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        clauses = ["status='approved'"]
        params: list = []
        if ticket_id is not None:
            clauses.append("ticket_id=?")
            params.append(str(ticket_id))
        if category:
            clauses.append("category=?")
            params.append(category)
        cur = self._exec(
            f"SELECT * FROM learning_candidates WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
            tuple(params),
        )
        if cur is None:
            return []
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            for f in ("evidence", "source_event_ids"):
                if isinstance(d.get(f), str):
                    try:
                        d[f] = json.loads(d[f])
                    except Exception:
                        pass
            rows.append(d)
        return rows

    # ── Aplicación ─────────────────────────────────────────────────────────────

    def record_application(
        self,
        learning_id: str,
        run_id: str,
        ticket_id: Any,
        *,
        applied_by: str = "system",
        context: Optional[dict] = None,
        outcome: Optional[dict] = None,
    ) -> bool:
        """Registrar que un learning fue aplicado en un run."""
        self._exec(
            """
            INSERT INTO applied_learnings
            (learning_id, run_id, ticket_id, applied_at, applied_by, context, outcome)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                learning_id, run_id, str(ticket_id), _utcnow(),
                applied_by,
                json.dumps(context or {}),
                json.dumps(outcome or {}),
            ),
        )
        self._exec(
            """
            UPDATE learning_candidates
            SET applied_count=applied_count+1, last_applied_at=?
            WHERE learning_id=?
            """,
            (_utcnow(), learning_id),
        )
        self._commit()
        return True

    # ── Stats ──────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Resumen global del store."""
        cur = self._exec(
            "SELECT status, COUNT(*) FROM learning_candidates GROUP BY status"
        )
        by_status: dict = {}
        if cur:
            for row in cur.fetchall():
                by_status[row[0]] = row[1]
        cur2 = self._exec("SELECT COUNT(*) FROM applied_learnings")
        applied_count = 0
        if cur2:
            r = cur2.fetchone()
            applied_count = r[0] if r else 0
        return {
            "candidates": by_status.get("candidate", 0),
            "approved": by_status.get("approved", 0),
            "rejected": by_status.get("rejected", 0),
            "superseded": by_status.get("superseded", 0),
            "total_applications": applied_count,
        }

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
