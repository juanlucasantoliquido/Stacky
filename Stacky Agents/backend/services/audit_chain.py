"""
FA-39 — Audit immutability con HMAC hash chain.

Cada AgentExecution queda encadenada criptográficamente con la anterior
del mismo ticket, formando una cadena hash similar a blockchain.

Hash de un nodo:
  HMAC-SHA256(key=AUDIT_SECRET, msg=SHA256(exec_id | ticket_id | agent_type |
              started_at | output_hash | prev_chain_hash))

Tamper detection:
  Si alguien modifica el output de la exec N, su hash cambia, lo que rompe
  la cadena de la exec N+1 en adelante. `verify_chain(ticket_id)` detecta
  la ruptura y devuelve exactamente dónde.

Tabla `audit_entries`:
  exec_id, ticket_id, node_hash, prev_hash, output_hash, computed_at

No requiere clave externa — se computa de forma independiente para que
incluso si alguien borra la tabla se pueda re-calcular desde las execs.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from db import Base, session_scope
from models import AgentExecution


AUDIT_SECRET = os.getenv("AUDIT_SECRET", "stacky-agents-audit-default-secret-change-in-prod")
GENESIS_HASH = "0" * 64


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id = Column(Integer, primary_key=True)
    execution_id = Column(Integer, nullable=False, unique=True)
    ticket_id = Column(Integer, nullable=False)
    node_hash = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=False)
    output_hash = Column(String(64))
    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_audit_ticket", "ticket_id", "computed_at"),)

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "ticket_id": self.ticket_id,
            "node_hash": self.node_hash,
            "prev_hash": self.prev_hash,
            "output_hash": self.output_hash,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
        }


@dataclass
class ChainVerifyResult:
    valid: bool
    length: int
    first_tampered_exec_id: int | None
    detail: str

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "length": self.length,
            "first_tampered_exec_id": self.first_tampered_exec_id,
            "detail": self.detail,
        }


def _output_hash(output: str | None) -> str:
    return hashlib.sha256((output or "").encode("utf-8")).hexdigest()


def _node_hash(
    exec_id: int,
    ticket_id: int,
    agent_type: str,
    started_at: str,
    out_hash: str,
    prev_hash: str,
) -> str:
    payload = json.dumps(
        {
            "exec_id": exec_id,
            "ticket_id": ticket_id,
            "agent_type": agent_type,
            "started_at": started_at,
            "output_hash": out_hash,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
    ).encode("utf-8")
    return _hmac.new(AUDIT_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def seal(execution_id: int) -> str | None:
    """
    Crea o actualiza la AuditEntry para la exec dada.
    Debe llamarse después de que la exec esté en estado 'completed'.
    Devuelve el node_hash generado.
    """
    with session_scope() as session:
        exec_row = session.get(AgentExecution, execution_id)
        if exec_row is None:
            return None

        # Buscar el hash previo en el mismo ticket
        prev = (
            session.query(AuditEntry)
            .filter_by(ticket_id=exec_row.ticket_id)
            .order_by(AuditEntry.computed_at.desc())
            .first()
        )
        prev_hash = prev.node_hash if prev else GENESIS_HASH
        out_hash = _output_hash(exec_row.output)
        started = (
            exec_row.started_at.isoformat()
            if exec_row.started_at
            else "1970-01-01T00:00:00"
        )
        nhash = _node_hash(
            exec_id=exec_row.id,
            ticket_id=exec_row.ticket_id,
            agent_type=exec_row.agent_type,
            started_at=started,
            out_hash=out_hash,
            prev_hash=prev_hash,
        )

        existing = session.query(AuditEntry).filter_by(execution_id=execution_id).first()
        if existing:
            existing.node_hash = nhash
            existing.output_hash = out_hash
            existing.computed_at = datetime.utcnow()
        else:
            session.add(
                AuditEntry(
                    execution_id=execution_id,
                    ticket_id=exec_row.ticket_id,
                    node_hash=nhash,
                    prev_hash=prev_hash,
                    output_hash=out_hash,
                )
            )
        return nhash


def verify_chain(ticket_id: int) -> ChainVerifyResult:
    """
    Recorre la cadena de auditoría del ticket y re-computa cada hash
    comparándolo contra los outputs actuales en DB.
    """
    with session_scope() as session:
        entries = (
            session.query(AuditEntry)
            .filter_by(ticket_id=ticket_id)
            .order_by(AuditEntry.computed_at)
            .all()
        )
        if not entries:
            return ChainVerifyResult(valid=True, length=0, first_tampered_exec_id=None,
                                     detail="sin entradas de auditoría")

        prev_hash = GENESIS_HASH
        for e in entries:
            exec_row = session.get(AgentExecution, e.execution_id)
            if exec_row is None:
                return ChainVerifyResult(
                    valid=False, length=len(entries),
                    first_tampered_exec_id=e.execution_id,
                    detail=f"exec {e.execution_id} no existe en la tabla",
                )
            current_out_hash = _output_hash(exec_row.output)
            started = (
                exec_row.started_at.isoformat()
                if exec_row.started_at
                else "1970-01-01T00:00:00"
            )
            expected = _node_hash(
                exec_id=e.execution_id,
                ticket_id=e.ticket_id,
                agent_type=exec_row.agent_type,
                started_at=started,
                out_hash=current_out_hash,
                prev_hash=prev_hash,
            )
            if expected != e.node_hash:
                return ChainVerifyResult(
                    valid=False, length=len(entries),
                    first_tampered_exec_id=e.execution_id,
                    detail=f"hash mismatch en exec {e.execution_id} — posible tampering",
                )
            prev_hash = e.node_hash

    return ChainVerifyResult(valid=True, length=len(entries),
                             first_tampered_exec_id=None, detail="chain OK")
