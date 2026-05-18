"""SQLAlchemy models para PM Intelligence Suite — Fase 1 MVP.

Solo 3 tablas (no 10): pm_sprint_snapshots, pm_risk_items, pm_work_item_comments.
El resto del modelo de datos del plan v1 se agrega cuando exista demanda real
y datos para sustentarlo.

Contratos en docs/11_PM_INTELLIGENCE_SUITE.md §3.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


class PmSprintSnapshot(Base):
    """Snapshot inmutable de KPIs de un sprint en un momento dado.

    `snapshot_json` contiene los KPIs serializados según contrato §2 del plan v2.
    Cada llamada a sync-ado genera una fila nueva (history is append-only).
    """

    __tablename__ = "pm_sprint_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project: Mapped[str] = mapped_column(String(80), nullable=False)
    sprint_id: Mapped[str] = mapped_column(String(200), nullable=False)
    sprint_name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="ado_live")
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_pm_sprint_project_captured", "project", "captured_at"),
        Index("ix_pm_sprint_project_sprint", "project", "sprint_id"),
    )

    @property
    def snapshot(self) -> dict:
        return _json_loads(self.snapshot_json) or {}

    @snapshot.setter
    def snapshot(self, value: dict) -> None:
        self.snapshot_json = _json_dumps(value or {})

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "sprint_id": self.sprint_id,
            "sprint_name": self.sprint_name,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "snapshot": self.snapshot,
            "source": self.source,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
        }


class PmRiskItem(Base):
    """Riesgo detectado por reglas deterministas (Fase 1) o IA advisory (Fase 2+).

    `ai_enriched=False` por defecto — solo cambia cuando un componente IA con
    evals pasados agrega información. `acknowledged_by` registra el operador
    humano que reconoció el riesgo (no resuelve, solo acknowledges).
    """

    __tablename__ = "pm_risk_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project: Mapped[str] = mapped_column(String(80), nullable=False)
    sprint_id: Mapped[str | None] = mapped_column(String(200))
    risk_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    affected_items_json: Mapped[str | None] = mapped_column(Text)
    rule: Mapped[str | None] = mapped_column(String(100))
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(200))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    ai_enriched: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_pm_risk_project_sprint", "project", "sprint_id"),
        Index("ix_pm_risk_detected", "detected_at"),
    )

    @property
    def affected_items(self) -> list[int]:
        return _json_loads(self.affected_items_json) or []

    @affected_items.setter
    def affected_items(self, value: list[int]) -> None:
        self.affected_items_json = _json_dumps(value or [])

    def to_dict(self) -> dict:
        return {
            "risk_id": self.risk_id,
            "project": self.project,
            "sprint_id": self.sprint_id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "affected_items": self.affected_items,
            "rule": self.rule,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "ai_enriched": self.ai_enriched,
        }


class PmWorkItemComment(Base):
    """Indexador de comentarios de work items.

    `text_plain` SIEMPRE viene pre-procesado con HTML strip + pii_masker.mask().
    El texto crudo NO se persiste. Campos `sentiment_*` quedan en NULL hasta
    Fase 2 (cuando los eval fixtures de comment_sentiment estén verdes).
    """

    __tablename__ = "pm_work_item_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ado_id: Mapped[int] = mapped_column(Integer, nullable=False)
    project: Mapped[str] = mapped_column(String(80), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200))
    comment_date: Mapped[date | None] = mapped_column(Date)
    text_plain: Mapped[str | None] = mapped_column(Text)
    ai_analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    sentiment_label: Mapped[str | None] = mapped_column(String(20))
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_pm_comments_ado", "ado_id"),
        Index("ix_pm_comments_project_date", "project", "comment_date"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ado_id": self.ado_id,
            "project": self.project,
            "author": self.author,
            "comment_date": self.comment_date.isoformat() if self.comment_date else None,
            "text_plain": self.text_plain,
            "ai_analyzed": self.ai_analyzed,
            "sentiment_label": self.sentiment_label,
            "sentiment_score": self.sentiment_score,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
        }

