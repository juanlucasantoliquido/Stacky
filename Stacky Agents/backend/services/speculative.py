"""
FA-36 — Speculative pre-execution.

Mientras el operador edita el contexto, el backend pre-ejecuta el agente
en background con el contexto actual (debounced 5s). Cuando el operador
hace click en Run:
  - Si el contexto no cambió → respuesta inmediata desde el spec-result.
  - Si cambió → se usa el resultado como cache candidate o se descarta.

API:
  POST /api/agents/speculate  →  { spec_id }  (dispara en background)
  GET  /api/agents/speculate/:spec_id  →  { status, result? }
  DELETE /api/agents/speculate/:spec_id  →  cancel
  POST /api/agents/run con spec_id  →  si el hash coincide, devuelve spec-result

Tabla `spec_executions`:
  id, agent_type, ticket_id, input_hash, status, output, created_at, expires_at

TTL: 10 minutos (después de eso ya no vale).
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from db import Base, session_scope
from services.output_cache import compute_key

SPEC_TTL_MINUTES = 10


class SpecExecution(Base):
    __tablename__ = "spec_executions"

    id = Column(Integer, primary_key=True)
    agent_type = Column(String(20), nullable=False)
    ticket_id = Column(Integer, nullable=False)
    input_hash = Column(String(64), nullable=False)
    status = Column(String(20), default="running")  # running | completed | cancelled | expired
    output = Column(Text)
    output_format = Column(String(20), default="markdown")
    started_by = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)

    __table_args__ = (Index("ix_spec_hash", "agent_type", "input_hash"),)

    def to_dict(self, include_output: bool = False) -> dict:
        d = {
            "id": self.id,
            "agent_type": self.agent_type,
            "ticket_id": self.ticket_id,
            "input_hash": self.input_hash,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
        if include_output:
            d["output"] = self.output
            d["output_format"] = self.output_format
        return d


_cancelled: set[int] = set()


def start(
    *,
    agent_type: str,
    ticket_id: int,
    context_blocks: list[dict],
    started_by: str,
) -> int:
    """Inicia una ejecución especulativa en background. Devuelve spec_id."""
    input_hash = compute_key(agent_type=agent_type, blocks=context_blocks)
    now = datetime.utcnow()

    with session_scope() as session:
        existing = (
            session.query(SpecExecution)
            .filter_by(agent_type=agent_type, input_hash=input_hash, status="running")
            .first()
        )
        if existing:
            return existing.id

        row = SpecExecution(
            agent_type=agent_type,
            ticket_id=ticket_id,
            input_hash=input_hash,
            status="running",
            started_by=started_by,
            created_at=now,
            expires_at=now + timedelta(minutes=SPEC_TTL_MINUTES),
        )
        session.add(row)
        session.flush()
        spec_id = row.id

    threading.Thread(
        target=_run_spec,
        args=(spec_id, agent_type, context_blocks),
        daemon=True,
    ).start()
    return spec_id


def _run_spec(spec_id: int, agent_type: str, blocks: list[dict]) -> None:
    import agents as _agents
    import copilot_bridge

    a = _agents.get(agent_type)
    if a is None:
        _mark(spec_id, "cancelled")
        return
    try:
        def noop_log(*a, **k):
            pass

        result = a.run(blocks, log=noop_log, execution_id=None)
        if spec_id in _cancelled:
            _mark(spec_id, "cancelled")
            return
        with session_scope() as session:
            row = session.get(SpecExecution, spec_id)
            if row:
                row.output = result.output
                row.output_format = result.output_format
                row.status = "completed"
    except Exception:  # noqa: BLE001
        _mark(spec_id, "cancelled")


def _mark(spec_id: int, status: str) -> None:
    with session_scope() as session:
        row = session.get(SpecExecution, spec_id)
        if row:
            row.status = status


def get(spec_id: int) -> dict | None:
    with session_scope() as session:
        row = session.get(SpecExecution, spec_id)
        if row is None:
            return None
        if row.expires_at and datetime.utcnow() > row.expires_at:
            row.status = "expired"
        return row.to_dict(include_output=True)


def cancel(spec_id: int) -> None:
    _cancelled.add(spec_id)
    _mark(spec_id, "cancelled")


def claim(
    *,
    agent_type: str,
    context_blocks: list[dict],
) -> dict | None:
    """
    Busca un spec completado con el mismo hash. Si existe y no expiró,
    devuelve el resultado listo para usarse como output de Run.
    """
    input_hash = compute_key(agent_type=agent_type, blocks=context_blocks)
    with session_scope() as session:
        row = (
            session.query(SpecExecution)
            .filter_by(agent_type=agent_type, input_hash=input_hash, status="completed")
            .order_by(SpecExecution.created_at.desc())
            .first()
        )
        if row is None:
            return None
        if row.expires_at and datetime.utcnow() > row.expires_at:
            row.status = "expired"
            return None
        return row.to_dict(include_output=True)
