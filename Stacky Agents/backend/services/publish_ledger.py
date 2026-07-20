"""publish_ledger.py — Plan 153. Ledger transaccional de publicaciones a ADO.

Reemplaza el mecanismo R1.3 de markers en metadata_json. El INSERT con UNIQUE
sobre execution_id ES el lock: no hay check previo, no hay carrera.
El desbloqueo de filas pending/failed es SIEMPRE una accion humana (api/publish_ledger).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, session_scope

logger = logging.getLogger("stacky.publish_ledger")

STATUS_PENDING = "pending"
STATUS_POSTED = "posted"
STATUS_FAILED = "failed"

STALE_MINUTES = 30  # umbral de "stale" para el sweep de solo-lectura

_MIGRATION_SENTINEL_ID = -153  # centinela: id negativo (nunca colisiona con execution_id real, autoincrement > 0)


class PublishLedgerEntry(Base):
    __tablename__ = "publish_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # pending | posted | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    ado_ids: Mapped[str | None] = mapped_column(Text)   # JSON list[int]
    error: Mapped[str | None] = mapped_column(Text)      # truncado a 500 chars
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="runtime")  # runtime | migration

    def to_dict(self) -> dict:
        try:
            ado_ids = json.loads(self.ado_ids) if self.ado_ids else None
        except Exception:  # noqa: BLE001
            ado_ids = None
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "ado_ids": ado_ids,
            "error": self.error,
            "source": self.source,
        }


def try_acquire(execution_id: int) -> str:
    """INSERT-primero. 'acquired' si esta llamada gano el lock;
    'replay_pending' | 'replay_posted' | 'replay_failed' | 'replay_unknown' si ya existia fila.
    Excepciones NO-IntegrityError PROPAGAN (el caller decide el fallback)."""
    try:
        with session_scope() as session:
            session.add(PublishLedgerEntry(
                execution_id=int(execution_id), status=STATUS_PENDING, source="runtime",
            ))
            session.flush()
        return "acquired"
    except IntegrityError:
        with session_scope() as session:
            row = (
                session.query(PublishLedgerEntry)
                .filter(PublishLedgerEntry.execution_id == int(execution_id))
                .one_or_none()
            )
            status = row.status if row is not None else "unknown"
        return f"replay_{status}"


def mark_posted(execution_id: int, ado_id: int | None, record_id: int | None = None) -> bool:
    with session_scope() as session:
        row = (
            session.query(PublishLedgerEntry)
            .filter(PublishLedgerEntry.execution_id == int(execution_id))
            .one_or_none()
        )
        if row is None:
            return False
        row.status = STATUS_POSTED
        row.ado_ids = json.dumps([int(ado_id)]) if ado_id is not None else None
        row.error = None
    return True


def mark_failed(execution_id: int, error: str) -> bool:
    with session_scope() as session:
        row = (
            session.query(PublishLedgerEntry)
            .filter(PublishLedgerEntry.execution_id == int(execution_id))
            .one_or_none()
        )
        if row is None:
            return False
        row.status = STATUS_FAILED
        row.error = (error or "")[:500]
    return True


def release(execution_id: int) -> bool:
    """Borra la fila (usado en dos casos: publish 'skipped' que no debe dejar
    fantasma pending, y la accion humana re-publicar antes de reintentar)."""
    with session_scope() as session:
        row = (
            session.query(PublishLedgerEntry)
            .filter(PublishLedgerEntry.execution_id == int(execution_id))
            .one_or_none()
        )
        if row is None:
            return False
        session.delete(row)
    return True


def snapshot_stuck(stale_minutes: int = STALE_MINUTES) -> dict:
    """SOLO LECTURA (el 'sweep'). Devuelve:
    {"pending_stale": [to_dict...], "failed": [to_dict...],
     "counts": {"pending": n, "pending_stale": n, "failed": n, "posted": n}}
    pending_stale = status=='pending' AND updated_at < utcnow - stale_minutes."""
    threshold = datetime.utcnow() - timedelta(minutes=stale_minutes)
    pending_stale: list[dict] = []
    failed: list[dict] = []
    counts = {"pending": 0, "pending_stale": 0, "failed": 0, "posted": 0}
    with session_scope() as session:
        rows = session.query(PublishLedgerEntry).all()
        for row in rows:
            if row.status == STATUS_PENDING:
                counts["pending"] += 1
                if row.updated_at is not None and row.updated_at < threshold:
                    counts["pending_stale"] += 1
                    pending_stale.append(row.to_dict())
            elif row.status == STATUS_FAILED:
                counts["failed"] += 1
                failed.append(row.to_dict())
            elif row.status == STATUS_POSTED:
                counts["posted"] += 1
    return {"pending_stale": pending_stale, "failed": failed, "counts": counts}


def count_persist_failures(since: datetime) -> int:
    """Metrica exacta para harness-health: filas status=='pending' con created_at >= since."""
    with session_scope() as session:
        return (
            session.query(PublishLedgerEntry)
            .filter(PublishLedgerEntry.status == STATUS_PENDING)
            .filter(PublishLedgerEntry.created_at >= since)
            .count()
        )


def migrate_legacy_markers() -> dict:
    """One-shot idempotente. Lee markers legacy publish_intent 'pending' de
    AgentExecution.metadata_json y los materializa como filas del ledger.
    NUNCA muta metadata_json (historia inmutable): la idempotencia es la
    existencia de la fila (UNIQUE execution_id). NUNCA postea a ADO.

    Short-circuit por centinela: tras la primera corrida exitosa se inserta una
    fila centinela (execution_id=-153, source='migration_sentinel', status='posted').
    En arranques subsiguientes un unico SELECT indexado detecta el centinela y
    retorna sin el scan LIKE de toda la tabla. Es seguro porque tras F1
    _attempt_publish ya NO escribe markers legacy nuevos: no aparecen markers
    'pending' despues del deploy."""
    from models import AgentExecution
    from services.ado_publisher import AgentHtmlPublish

    # Short-circuit: si el centinela ya existe, la migracion ya corrio => salir barato.
    with session_scope() as session:
        _already = (
            session.query(PublishLedgerEntry.id)
            .filter(PublishLedgerEntry.execution_id == _MIGRATION_SENTINEL_ID)
            .first()
        )
    if _already is not None:
        return {"migrated_posted": 0, "migrated_pending": 0, "skipped": 0, "sentinel_skip": True}

    migrated_posted = 0
    migrated_pending = 0
    skipped = 0
    with session_scope() as session:
        rows = (
            session.query(AgentExecution.id, AgentExecution.metadata_json)
            .filter(AgentExecution.metadata_json.contains('"publish_intent"'))
            .all()
        )
        existing_ids = {r.execution_id for r in session.query(PublishLedgerEntry.execution_id).all()}
        ok_publishes = {
            p.execution_id: p.ado_id
            for p in session.query(AgentHtmlPublish)
            .filter(AgentHtmlPublish.status == "ok")
            .all()
            if p.execution_id is not None
        }
        for exec_id, md_raw in rows:
            try:
                marker = (json.loads(md_raw or "{}").get("publish_intent") or {}).get("marker")
            except Exception:  # noqa: BLE001
                marker = None
            if marker != "pending" or exec_id in existing_ids:
                skipped += 1
                continue
            if exec_id in ok_publishes:
                session.add(PublishLedgerEntry(
                    execution_id=exec_id, status=STATUS_POSTED, source="migration",
                    ado_ids=json.dumps([ok_publishes[exec_id]]),
                ))
                migrated_posted += 1
            else:
                session.add(PublishLedgerEntry(
                    execution_id=exec_id, status=STATUS_PENDING, source="migration",
                ))
                migrated_pending += 1
    # sellar el centinela para short-circuitear los proximos arranques.
    try:
        with session_scope() as session:
            session.add(PublishLedgerEntry(
                execution_id=_MIGRATION_SENTINEL_ID, status=STATUS_POSTED, source="migration_sentinel",
            ))
            session.flush()
    except IntegrityError:
        pass  # carrera improbable (2 arranques simultaneos): el UNIQUE garantiza 1 solo centinela
    return {"migrated_posted": migrated_posted, "migrated_pending": migrated_pending, "skipped": skipped}
