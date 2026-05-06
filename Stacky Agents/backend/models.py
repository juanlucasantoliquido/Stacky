from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    return json.loads(raw)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ado_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    project: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ado_state: Mapped[str | None] = mapped_column(String(40))
    ado_url: Mapped[str | None] = mapped_column(String(400))
    priority: Mapped[int | None] = mapped_column(Integer)
    work_item_type: Mapped[str | None] = mapped_column(String(40))  # Epic, Task, Bug, etc.
    parent_ado_id: Mapped[int | None] = mapped_column(Integer)      # ADO id of parent Epic
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    executions: Mapped[list["AgentExecution"]] = relationship(back_populates="ticket")

    __table_args__ = (Index("ix_tickets_project_state", "project", "ado_state"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ado_id": self.ado_id,
            "project": self.project,
            "title": self.title,
            "description": self.description,
            "ado_state": self.ado_state,
            "ado_url": self.ado_url,
            "priority": self.priority,
            "work_item_type": self.work_item_type,
            "parent_ado_id": self.parent_ado_id,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PackRun(Base):
    __tablename__ = "pack_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pack_definition_id: Mapped[str] = mapped_column(String(50), nullable=False)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    options_json: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def options(self) -> dict | None:
        return _json_loads(self.options_json)

    @options.setter
    def options(self, value: dict | None) -> None:
        self.options_json = _json_dumps(value)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pack_definition_id": self.pack_definition_id,
            "ticket_id": self.ticket_id,
            "status": self.status,
            "current_step": self.current_step,
            "options": self.options,
            "started_by": self.started_by,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(20))
    input_context_json: Mapped[str] = mapped_column(Text, nullable=False)
    chain_from_json: Mapped[str | None] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    output_format: Mapped[str] = mapped_column(String(20), default="markdown")
    metadata_json: Mapped[str | None] = mapped_column(Text)
    contract_result_json: Mapped[str | None] = mapped_column(Text)  # N1: ContractResult serializado
    error_message: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    pack_run_id: Mapped[int | None] = mapped_column(ForeignKey("pack_runs.id"))
    pack_step: Mapped[int | None] = mapped_column(Integer)

    ticket: Mapped[Ticket] = relationship(back_populates="executions")

    __table_args__ = (
        Index("ix_exec_ticket_started", "ticket_id", "started_at"),
        Index("ix_exec_ticket_agent_status", "ticket_id", "agent_type", "status"),
        Index("ix_exec_pack_run", "pack_run_id"),
        Index("ix_exec_status_started", "status", "started_at"),
    )

    @property
    def input_context(self) -> list[dict]:
        return _json_loads(self.input_context_json) or []

    @input_context.setter
    def input_context(self, value: list[dict]) -> None:
        self.input_context_json = _json_dumps(value or [])

    @property
    def chain_from(self) -> list[int]:
        return _json_loads(self.chain_from_json) or []

    @chain_from.setter
    def chain_from(self, value: list[int]) -> None:
        self.chain_from_json = _json_dumps(value or [])

    @property
    def metadata_dict(self) -> dict:
        return _json_loads(self.metadata_json) or {}

    @metadata_dict.setter
    def metadata_dict(self, value: dict) -> None:
        self.metadata_json = _json_dumps(value or {})

    @property
    def contract_result(self) -> dict | None:
        return _json_loads(self.contract_result_json)

    @contract_result.setter
    def contract_result(self, value: dict | None) -> None:
        self.contract_result_json = _json_dumps(value)

    def duration_ms(self) -> int | None:
        if not self.completed_at or not self.started_at:
            return None
        return int((self.completed_at - self.started_at).total_seconds() * 1000)

    def to_dict(self, include_output: bool = True) -> dict:
        d = {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "verdict": self.verdict,
            "input_context": self.input_context,
            "chain_from": self.chain_from,
            "output_format": self.output_format,
            "metadata": self.metadata_dict,
            "error_message": self.error_message,
            "started_by": self.started_by,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms(),
            "pack_run_id": self.pack_run_id,
            "pack_step": self.pack_step,
            "contract_result": self.contract_result,
        }
        if include_output:
            d["output"] = self.output
        return d


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[int] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(80))
    indent: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("ix_logs_exec_ts", "execution_id", "timestamp"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message,
            "group": self.group_name,
            "indent": self.indent,
        }
