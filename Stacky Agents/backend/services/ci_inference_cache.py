"""Plan 71 F2 — Caché de inferencia CI.

Tabla SQLAlchemy CIInferenceCache con helpers get_cached/set_cached.
Se registra en models.Base para que create_all la cree automáticamente.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, Session

from db import Base

logger = logging.getLogger("stacky.services.ci_inference_cache")


class CIInferenceCache(Base):
    """Caché de resultados de inferencia CI por (tracker_type, item_id, ref).

    Tabla nueva → Base.metadata.create_all la crea sin migración destructiva.
    """

    __tablename__ = "ci_inference_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracker_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="ci", nullable=False)
    cached_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_ci_cache_key", "tracker_type", "item_id", "ref"),
    )


# ---------------------------------------------------------------------------
# Session helper (parcheable en tests)
# ---------------------------------------------------------------------------

def _get_session() -> Session:
    from db import session_scope  # noqa: PLC0415
    # Usamos Session directa para compatibilidad con tests que parchean esto
    from db import engine as _engine  # noqa: PLC0415
    return Session(_engine)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def get_cached(
    tracker_type: str,
    item_id: str,
    ref: Optional[str],
    ttl_minutes: int = 60,
) -> Optional[dict]:
    """Retorna el resultado cacheado si no ha expirado, o None."""
    try:
        session = _get_session()
        with session:
            row = (
                session.query(CIInferenceCache)
                .filter(
                    CIInferenceCache.tracker_type == tracker_type,
                    CIInferenceCache.item_id == item_id,
                    CIInferenceCache.ref == ref,
                )
                .order_by(CIInferenceCache.cached_at.desc())
                .first()
            )
            if row is None:
                return None
            cutoff = datetime.utcnow() - timedelta(minutes=ttl_minutes)
            if row.cached_at < cutoff:
                return None
            try:
                return json.loads(row.result_json)
            except (ValueError, TypeError):
                return None
    except Exception:
        logger.exception("ci_inference_cache.get_cached falló")
        return None


def set_cached(
    tracker_type: str,
    item_id: str,
    ref: Optional[str],
    result: dict,
    source: str,
) -> None:
    """Persiste o actualiza el resultado cacheado."""
    try:
        session = _get_session()
        with session:
            # Eliminar entrada anterior si existe
            session.query(CIInferenceCache).filter(
                CIInferenceCache.tracker_type == tracker_type,
                CIInferenceCache.item_id == item_id,
                CIInferenceCache.ref == ref,
            ).delete(synchronize_session=False)

            row = CIInferenceCache(
                tracker_type=tracker_type,
                item_id=item_id,
                ref=ref,
                result_json=json.dumps(result, ensure_ascii=False),
                source=source,
                cached_at=datetime.utcnow(),
            )
            session.add(row)
            session.commit()
    except Exception:
        logger.exception("ci_inference_cache.set_cached falló")
