"""
quarantine_registry.py — Quarantine Registry for QA UAT Agent.

Manages flaky tests with explicit TTL, owner, and reason.
A quarantine without TTL or without owner cannot be created.

Storage: SQLite in data/quarantine.db (JSON fallback if SQLite unavailable).

Rules:
  - TTL max: 14 days from created_at
  - owner required — no owner → ValueError
  - expires_at required — no TTL → ValueError
  - Expired quarantine fails the gate (not renewed automatically)
  - APP category blocked without force=True

Usage:
    from quarantine_registry import QuarantineRegistry, QuarantineEntry
    import datetime

    registry = QuarantineRegistry()
    entry = registry.add_quarantine(QuarantineEntry(
        test_id="RF-008-CA-01",
        scenario_id="RF-008-CA-01",
        screen="FrmDetalleClie.aspx",
        category="NAV",
        reason="FLAKY_SELECTOR",
        owner="qa_automation",
        ttl_days=7,
    ))
    print(registry.is_quarantined("RF-008-CA-01"))  # True
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("stacky.qa_uat.quarantine_registry")

_MAX_TTL_DAYS = 14
_DB_PATH = Path(__file__).parent / "data" / "quarantine.db"
_JSON_FALLBACK_PATH = Path(__file__).parent / "data" / "quarantine.json"

_VALID_CATEGORIES = frozenset(["NAV", "DATA", "GEN", "OPS", "ENV", "APP", "OBS", "PIP", "SEC"])
_VALID_STATUSES = frozenset(["active", "resolved", "expired"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_dt(s: str) -> datetime:
    """Parse ISO datetime string to aware datetime (UTC)."""
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # Try without microseconds
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


# ── Entry dataclass ───────────────────────────────────────────────────────────

@dataclass
class QuarantineEntry:
    """
    Represents a quarantined test.

    Mandatory: test_id, scenario_id, category, reason, owner, ttl_days.
    Optional: screen, evidence_path, linked_ticket.
    """
    test_id: str
    scenario_id: str
    category: str
    reason: str
    owner: str
    ttl_days: int
    # Auto-set
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    screen: Optional[str] = None
    created_at: str = field(default_factory=_utcnow)
    expires_at: str = ""          # computed in __post_init__
    status: str = "active"
    evidence_path: Optional[str] = None
    linked_ticket: Optional[int] = None

    def __post_init__(self) -> None:
        # Validate required fields
        if not self.owner or not self.owner.strip():
            raise ValueError("QuarantineEntry: 'owner' is required and cannot be empty")
        if not self.ttl_days or self.ttl_days <= 0:
            raise ValueError("QuarantineEntry: 'ttl_days' is required and must be > 0")
        if self.ttl_days > _MAX_TTL_DAYS:
            raise ValueError(
                f"QuarantineEntry: ttl_days={self.ttl_days} exceeds maximum of {_MAX_TTL_DAYS} days"
            )
        if self.category not in _VALID_CATEGORIES:
            raise ValueError(
                f"QuarantineEntry: category '{self.category}' invalid. "
                f"Valid: {sorted(_VALID_CATEGORIES)}"
            )

        # Compute expires_at if not explicitly set
        if not self.expires_at:
            created = _parse_dt(self.created_at)
            expires = created + timedelta(days=self.ttl_days)
            self.expires_at = expires.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def is_expired(self) -> bool:
        """Return True if the quarantine has passed its expires_at datetime."""
        try:
            exp = _parse_dt(self.expires_at)
            return datetime.now(timezone.utc) >= exp
        except Exception:
            return False

    def days_remaining(self) -> int:
        """Return days until expiry (negative if already expired)."""
        try:
            exp = _parse_dt(self.expires_at)
            delta = exp - datetime.now(timezone.utc)
            return int(delta.total_seconds() / 86400)
        except Exception:
            return 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_expired"] = self.is_expired()
        d["days_remaining"] = self.days_remaining()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "QuarantineEntry":
        # Strip computed fields that are not constructor params
        clean = {k: v for k, v in d.items() if k not in ("is_expired", "days_remaining")}
        # ttl_days may not be stored — compute from timestamps
        if "ttl_days" not in clean or not clean["ttl_days"]:
            try:
                created = _parse_dt(clean.get("created_at", ""))
                expires = _parse_dt(clean.get("expires_at", ""))
                clean["ttl_days"] = max(1, int((expires - created).total_seconds() / 86400))
            except Exception:
                clean["ttl_days"] = _MAX_TTL_DAYS
        obj = cls.__new__(cls)
        for k, v in clean.items():
            setattr(obj, k, v)
        return obj


# ── Summary dataclass ─────────────────────────────────────────────────────────

@dataclass
class QuarantineSummary:
    active_count: int
    expired_unresolved_count: int
    resolved_count: int
    oldest_active_days: Optional[int]
    categories: dict[str, int]
    owners: dict[str, int]
    generated_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Registry ──────────────────────────────────────────────────────────────────

class QuarantineRegistry:
    """
    Manages quarantine entries with SQLite storage (JSON fallback).

    All mutating methods emit an event dict suitable for execution.jsonl.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        json_path: Optional[Path] = None,
    ) -> None:
        self._db_path = db_path or _DB_PATH
        self._json_path = json_path or _JSON_FALLBACK_PATH
        self._use_sqlite = self._try_init_sqlite()

    # ── Initialisation ─────────────────────────────────────────────────────────

    def _try_init_sqlite(self) -> bool:
        """Try to initialise SQLite storage. Returns True on success."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._connect()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quarantine (
                    id TEXT PRIMARY KEY,
                    test_id TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    screen TEXT,
                    category TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    ttl_days INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    evidence_path TEXT,
                    linked_ticket INTEGER,
                    resolution_note TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scenario ON quarantine(scenario_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_status ON quarantine(status)"
            )
            conn.commit()
            conn.close()
            _logger.debug("quarantine_registry: SQLite storage initialised at %s", self._db_path)
            return True
        except Exception as exc:
            _logger.warning(
                "quarantine_registry: SQLite unavailable (%s) — using JSON fallback", exc
            )
            return False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    # ── JSON fallback helpers ──────────────────────────────────────────────────

    def _load_json(self) -> list[dict]:
        if not self._json_path.exists():
            return []
        try:
            return json.loads(self._json_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_json(self, entries: list[dict]) -> None:
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        self._json_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_quarantine(
        self,
        entry: QuarantineEntry,
        force: bool = False,
    ) -> QuarantineEntry:
        """
        Add a quarantine entry.

        Raises ValueError for APP category without force=True.
        Raises ValueError if owner or ttl_days are invalid (propagates from dataclass).
        """
        if entry.category == "APP" and not force:
            raise ValueError(
                "Quarantining APP category requires explicit force=True. "
                "APP failures indicate real product defects and need developer approval."
            )

        if self._use_sqlite:
            self._sqlite_insert(entry)
        else:
            records = self._load_json()
            records.append(entry.to_dict())
            self._save_json(records)

        _logger.info(
            "quarantine_registry: added %s owner=%s ttl=%dd expires=%s",
            entry.test_id, entry.owner, entry.ttl_days, entry.expires_at,
        )
        return entry

    def get_active_quarantines(self) -> list[QuarantineEntry]:
        """Return all entries with status='active' that have NOT expired."""
        entries = self._load_all_by_status("active")
        # Do not auto-expire here — caller calls expire_old_quarantines() explicitly
        return [e for e in entries if not e.is_expired()]

    def expire_old_quarantines(self) -> list[QuarantineEntry]:
        """
        Find active entries that have passed their expires_at.
        Mark them as 'expired' and return them.
        """
        if self._use_sqlite:
            return self._sqlite_expire()
        else:
            return self._json_expire()

    def resolve_quarantine(
        self,
        quarantine_id: str,
        resolution_note: str,
    ) -> QuarantineEntry:
        """Mark a quarantine as resolved. Raises KeyError if not found."""
        if self._use_sqlite:
            return self._sqlite_resolve(quarantine_id, resolution_note)
        else:
            return self._json_resolve(quarantine_id, resolution_note)

    def is_quarantined(self, scenario_id: str) -> bool:
        """
        Return True if scenario_id has an ACTIVE (non-expired) quarantine.

        This is the gate check called during the pipeline.
        """
        if self._use_sqlite:
            return self._sqlite_is_quarantined(scenario_id)
        else:
            active = self.get_active_quarantines()
            return any(e.scenario_id == scenario_id for e in active)

    def get_quarantine_summary(self) -> QuarantineSummary:
        """Return aggregate health metrics for the dashboard."""
        all_entries = self._load_all_entries()

        active = [e for e in all_entries if e.status == "active" and not e.is_expired()]
        expired_unresolved = [
            e for e in all_entries if e.status == "active" and e.is_expired()
        ]
        resolved = [e for e in all_entries if e.status == "resolved"]

        oldest_days: Optional[int] = None
        if active:
            try:
                oldest = min(
                    (_parse_dt(e.created_at) for e in active),
                    default=datetime.now(timezone.utc),
                )
                oldest_days = int((datetime.now(timezone.utc) - oldest).total_seconds() / 86400)
            except Exception:
                pass

        categories: dict[str, int] = {}
        owners: dict[str, int] = {}
        for e in active:
            categories[e.category] = categories.get(e.category, 0) + 1
            owners[e.owner] = owners.get(e.owner, 0) + 1

        return QuarantineSummary(
            active_count=len(active),
            expired_unresolved_count=len(expired_unresolved),
            resolved_count=len(resolved),
            oldest_active_days=oldest_days,
            categories=categories,
            owners=owners,
        )

    def build_quarantine_event(self, entry: QuarantineEntry) -> dict:
        """Return the execution.jsonl event dict for a quarantine addition."""
        return {
            "event": "test_quarantined",
            "test_id": entry.test_id,
            "scenario_id": entry.scenario_id,
            "reason": entry.reason,
            "category": entry.category,
            "owner": entry.owner,
            "created_at": entry.created_at,
            "expires_at": entry.expires_at,
            "ttl_days": entry.ttl_days,
            "screen": entry.screen,
            "linked_ticket": entry.linked_ticket,
        }

    def emit_quarantine_event(self, exec_logger, entry: QuarantineEntry) -> None:
        """Emit test_quarantined event to execution.jsonl."""
        if exec_logger is None:
            return
        try:
            evt = self.build_quarantine_event(entry)
            exec_logger.event("test_quarantined", {k: v for k, v in evt.items() if k != "event"})
        except Exception as exc:
            _logger.debug("quarantine_registry: emit event failed: %s", exc)

    # ── SQLite implementation ──────────────────────────────────────────────────

    def _sqlite_insert(self, entry: QuarantineEntry) -> None:
        conn = self._connect()
        conn.execute("""
            INSERT INTO quarantine
              (id, test_id, scenario_id, screen, category, reason, owner,
               created_at, expires_at, ttl_days, status, evidence_path, linked_ticket)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            entry.id, entry.test_id, entry.scenario_id, entry.screen,
            entry.category, entry.reason, entry.owner,
            entry.created_at, entry.expires_at, entry.ttl_days,
            entry.status, entry.evidence_path, entry.linked_ticket,
        ))
        conn.commit()
        conn.close()

    def _sqlite_load_by_status(self, status: str) -> list[QuarantineEntry]:
        try:
            conn = self._connect()
            rows = conn.execute(
                "SELECT * FROM quarantine WHERE status=?", (status,)
            ).fetchall()
            cols = [d[0] for d in conn.execute("SELECT * FROM quarantine LIMIT 0").description or []]
            conn.close()
            if not cols:
                cols = [
                    "id", "test_id", "scenario_id", "screen", "category", "reason", "owner",
                    "created_at", "expires_at", "ttl_days", "status",
                    "evidence_path", "linked_ticket", "resolution_note",
                ]
            return [QuarantineEntry.from_dict(dict(zip(cols, r))) for r in rows]
        except Exception as exc:
            _logger.warning("quarantine_registry: SQLite load failed: %s", exc)
            return []

    def _sqlite_load_all(self) -> list[QuarantineEntry]:
        try:
            conn = self._connect()
            cur = conn.execute("SELECT * FROM quarantine")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            conn.close()
            return [QuarantineEntry.from_dict(dict(zip(cols, r))) for r in rows]
        except Exception as exc:
            _logger.warning("quarantine_registry: SQLite load_all failed: %s", exc)
            return []

    def _sqlite_expire(self) -> list[QuarantineEntry]:
        now_str = _utcnow()
        try:
            conn = self._connect()
            cur = conn.execute(
                "SELECT * FROM quarantine WHERE status='active' AND expires_at <= ?",
                (now_str,),
            )
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            expired = [QuarantineEntry.from_dict(dict(zip(cols, r))) for r in rows]
            if expired:
                ids = [e.id for e in expired]
                conn.executemany(
                    "UPDATE quarantine SET status='expired' WHERE id=?",
                    [(i,) for i in ids],
                )
                conn.commit()
            conn.close()
            for e in expired:
                e.status = "expired"
            return expired
        except Exception as exc:
            _logger.warning("quarantine_registry: SQLite expire failed: %s", exc)
            return []

    def _sqlite_resolve(self, qid: str, note: str) -> QuarantineEntry:
        conn = self._connect()
        cur = conn.execute("SELECT * FROM quarantine WHERE id=?", (qid,))
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        if not row:
            conn.close()
            raise KeyError(f"QuarantineEntry '{qid}' not found")
        entry = QuarantineEntry.from_dict(dict(zip(cols, row)))
        conn.execute(
            "UPDATE quarantine SET status='resolved', resolution_note=? WHERE id=?",
            (note, qid),
        )
        conn.commit()
        conn.close()
        entry.status = "resolved"
        return entry

    def _sqlite_is_quarantined(self, scenario_id: str) -> bool:
        now_str = _utcnow()
        try:
            conn = self._connect()
            row = conn.execute(
                "SELECT id FROM quarantine WHERE scenario_id=? AND status='active' AND expires_at > ? LIMIT 1",
                (scenario_id, now_str),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    # ── JSON fallback implementation ───────────────────────────────────────────

    def _load_all_by_status(self, status: str) -> list[QuarantineEntry]:
        if self._use_sqlite:
            return self._sqlite_load_by_status(status)
        return [
            QuarantineEntry.from_dict(r)
            for r in self._load_json()
            if r.get("status") == status
        ]

    def _load_all_entries(self) -> list[QuarantineEntry]:
        if self._use_sqlite:
            return self._sqlite_load_all()
        return [QuarantineEntry.from_dict(r) for r in self._load_json()]

    def _json_expire(self) -> list[QuarantineEntry]:
        records = self._load_json()
        now = datetime.now(timezone.utc)
        expired = []
        for r in records:
            if r.get("status") == "active":
                try:
                    exp = _parse_dt(r["expires_at"])
                    if now >= exp:
                        r["status"] = "expired"
                        expired.append(QuarantineEntry.from_dict(r))
                except Exception:
                    pass
        self._save_json(records)
        return expired

    def _json_resolve(self, qid: str, note: str) -> QuarantineEntry:
        records = self._load_json()
        for r in records:
            if r.get("id") == qid:
                r["status"] = "resolved"
                r["resolution_note"] = note
                self._save_json(records)
                return QuarantineEntry.from_dict(r)
        raise KeyError(f"QuarantineEntry '{qid}' not found")


# ── Module-level convenience singleton ────────────────────────────────────────

_registry: Optional[QuarantineRegistry] = None


def get_registry() -> QuarantineRegistry:
    """Return the module-level singleton QuarantineRegistry."""
    global _registry
    if _registry is None:
        _registry = QuarantineRegistry()
    return _registry
