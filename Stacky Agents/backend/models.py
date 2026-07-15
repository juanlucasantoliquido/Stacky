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
    UniqueConstraint,
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
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # May happen with truncated payloads — return the raw string so the
        # record is still usable instead of crashing the API.
        return raw


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ado_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # ID externo genérico del tracker. En ADO hoy coincide con ado_id.
    external_id: Mapped[int | None] = mapped_column(Integer)
    # Compatibilidad temporal: este campo sigue guardando el tracker_project
    # (ej. Strategist_Pacifico / UCollect_Strategist).
    project: Mapped[str] = mapped_column(String(80), nullable=False)
    stacky_project_name: Mapped[str | None] = mapped_column(String(80))
    tracker_type: Mapped[str | None] = mapped_column(String(40), default="azure_devops")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ado_state: Mapped[str | None] = mapped_column(String(40))
    ado_url: Mapped[str | None] = mapped_column(String(400))
    priority: Mapped[int | None] = mapped_column(Integer)
    work_item_type: Mapped[str | None] = mapped_column(String(40))  # Epic, Task, Bug, etc.
    parent_ado_id: Mapped[int | None] = mapped_column(Integer)      # ADO id of parent Epic
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Estado interno de Stacky (independiente de ado_state).
    # Valores: idle | running | completed | error | cancelled
    stacky_status: Mapped[str | None] = mapped_column(String(30), default="idle")
    # P6: asignado en ADO (uniqueName del campo System.AssignedTo).
    # Se sincroniza en cada sync_tickets(). Puede ser NULL si no hay asignado.
    assigned_to_ado: Mapped[str | None] = mapped_column(String(200))

    executions: Mapped[list["AgentExecution"]] = relationship(back_populates="ticket")

    __table_args__ = (
        Index("ix_tickets_project_state", "project", "ado_state"),
        Index("ix_tickets_stacky_project", "stacky_project_name"),
        Index(
            "ux_tickets_stacky_tracker_external",
            "stacky_project_name",
            "tracker_type",
            "external_id",
            unique=True,
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ado_id": self.ado_id,
            "external_id": self.external_id,
            "project": self.project,
            "stacky_project_name": self.stacky_project_name,
            "tracker_type": self.tracker_type,
            "title": self.title,
            "description": self.description,
            "ado_state": self.ado_state,
            "ado_url": self.ado_url,
            "priority": self.priority,
            "work_item_type": self.work_item_type,
            "parent_ado_id": self.parent_ado_id,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "stacky_status": self.stacky_status or "idle",
            "assigned_to_ado": self.assigned_to_ado,
        }


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # P6: campos de identidad ADO y perfil de asignacion
    ado_unique_name: Mapped[str | None] = mapped_column(String(200), unique=True)
    ado_display_name: Mapped[str | None] = mapped_column(String(200))
    # JSON: ["bug", "frontend", "refactor"] — configurables por el operador
    skills_json: Mapped[str | None] = mapped_column(Text)
    # JSON: ["Strategist_Pacifico\\UI"] — areas donde ha trabajado historicamente
    area_paths_json: Mapped[str | None] = mapped_column(Text)
    # Limite maximo de tickets activos que el operador configura por persona
    max_active_tickets: Mapped[int] = mapped_column(Integer, default=5)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "ado_unique_name": self.ado_unique_name,
            "ado_display_name": self.ado_display_name,
            "skills": _json_loads(self.skills_json) or [],
            "area_paths": _json_loads(self.area_paths_json) or [],
            "max_active_tickets": self.max_active_tickets,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TicketStateHistory(Base):
    """Historial de transiciones de estado de tickets sincronizados desde ADO.

    Cada vez que sync_tickets() detecta un cambio en ado_state, se registra
    aqui la transicion. Permite calcular estadisticas historicas de estados
    sin depender de llamadas on-demand a ADO.

    P6-Panel: fuente de verdad para el panel de estadisticas por usuario.
    """
    __tablename__ = "ticket_state_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    ado_id: Mapped[int] = mapped_column(Integer, nullable=False)
    stacky_project_name: Mapped[str | None] = mapped_column(String(80))
    old_state: Mapped[str | None] = mapped_column(String(40))
    new_state: Mapped[str] = mapped_column(String(40), nullable=False)
    assigned_to_ado: Mapped[str | None] = mapped_column(String(200))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_tsh_ticket_id", "ticket_id"),
        Index("ix_tsh_stacky_project_recorded", "stacky_project_name", "recorded_at"),
        Index("ix_tsh_assigned_to", "assigned_to_ado"),
        Index("ix_tsh_recorded_at", "recorded_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "ado_id": self.ado_id,
            "stacky_project_name": self.stacky_project_name,
            "old_state": self.old_state,
            "new_state": self.new_state,
            "assigned_to_ado": self.assigned_to_ado,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


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
    # Fase 1 (plan creacion-tareas-comentarios-100-efectiva): columnas operativas
    # que antes se seteaban como atributos dinamicos y no persistian en DB.
    # html_output_path: ruta relativa al repo del comment.html generado por el agente.
    # completion_source: origen del cierre (agent_gateway | manual | output_watcher | rescue | ...).
    html_output_path: Mapped[str | None] = mapped_column(String(500))
    completion_source: Mapped[str | None] = mapped_column(String(40))

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

    def to_dict(self, include_output: bool = True, include_ticket_context: bool = False) -> dict:
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
        if include_ticket_context:
            # Plan 134 F1: contexto de ticket para vistas globales (panel de runs,
            # notificaciones). Opt-in: el default False deja byte-idéntico a todos
            # los callers existentes. Guard `is not None` por ejecuciones cuyo
            # ticket fue borrado (trap conocida de tasks eliminadas).
            t = self.ticket
            d["project"] = t.stacky_project_name if t is not None else None
            d["ticket_title"] = t.title[:120] if t is not None else None
        if include_output:
            d["output"] = self.output
        return d


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    project: Mapped[str | None] = mapped_column(String(80))
    stages_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    current_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    last_execution_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_pipeline_ticket_status", "ticket_id", "status"),
    )

    @property
    def stages(self) -> list[str]:
        return _json_loads(self.stages_json) or []

    @stages.setter
    def stages(self, value: list[str]) -> None:
        self.stages_json = _json_dumps(value or []) or "[]"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "project": self.project,
            "stages": self.stages,
            "current_stage": self.current_stage,
            "status": self.status,
            "last_execution_id": self.last_execution_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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


class SystemLog(Base):
    """Structured system-wide event log.

    Captures every significant event across the entire Stacky Agents system:
    HTTP requests/responses, agent lifecycle, service calls, integrations,
    errors and frontend events. Designed for post-mortem debugging, auditing
    and operational observability.
    """

    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # When
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    # Severity
    level: Mapped[str] = mapped_column(String(10), nullable=False)          # DEBUG/INFO/WARNING/ERROR/CRITICAL
    # Who generated the event
    source: Mapped[str] = mapped_column(String(120), nullable=False)        # e.g. "agent_runner", "http.middleware"
    action: Mapped[str] = mapped_column(String(120), nullable=False)        # e.g. "agent_started", "http_request"
    # Correlation IDs
    execution_id: Mapped[int | None] = mapped_column(Integer)               # related AgentExecution (no FK — may not exist)
    ticket_id: Mapped[int | None] = mapped_column(Integer)
    user: Mapped[str | None] = mapped_column(String(200))
    request_id: Mapped[str | None] = mapped_column(String(36))              # UUID per HTTP request
    # HTTP-specific
    method: Mapped[str | None] = mapped_column(String(10))
    endpoint: Mapped[str | None] = mapped_column(String(500))
    status_code: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # Payloads (truncated to safe sizes)
    input_json: Mapped[str | None] = mapped_column(Text)                    # ≤ 16 KB
    output_json: Mapped[str | None] = mapped_column(Text)                   # ≤ 16 KB
    error_json: Mapped[str | None] = mapped_column(Text)                    # ≤ 64 KB — full stacktrace
    context_json: Mapped[str | None] = mapped_column(Text)                  # arbitrary extra k/v
    tags_json: Mapped[str | None] = mapped_column(Text)                     # ["batch", "agent", ...]

    __table_args__ = (
        Index("ix_syslog_timestamp", "timestamp"),
        Index("ix_syslog_level_ts", "level", "timestamp"),
        Index("ix_syslog_source_ts", "source", "timestamp"),
        Index("ix_syslog_execution", "execution_id"),
        Index("ix_syslog_ticket", "ticket_id"),
        Index("ix_syslog_request", "request_id"),
    )

    @property
    def input(self) -> Any:
        return _json_loads(self.input_json)

    @property
    def output(self) -> Any:
        return _json_loads(self.output_json)

    @property
    def error(self) -> Any:
        return _json_loads(self.error_json)

    @property
    def context(self) -> dict:
        return _json_loads(self.context_json) or {}

    @property
    def tags(self) -> list:
        return _json_loads(self.tags_json) or []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "level": self.level,
            "source": self.source,
            "action": self.action,
            "execution_id": self.execution_id,
            "ticket_id": self.ticket_id,
            "user": self.user,
            "request_id": self.request_id,
            "method": self.method,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "context": self.context,
            "tags": self.tags,
        }


class AgentPromptVersion(Base):
    """V1.1 — Historial auditable de prompts de agente (.agent.md).

    Los .agent.md están gitignored, por lo que la DB es el único lugar posible
    para historizar qué versión de prompt corrió cada run. Tabla nueva ⇒
    Base.metadata.create_all la crea sin migración destructiva.
    """

    __tablename__ = "agent_prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source: Mapped[str] = mapped_column(String(40), nullable=False)  # import_endpoint | fs_scan

    __table_args__ = (
        UniqueConstraint("filename", "sha256", name="uq_agent_prompt_filename_sha"),
        Index("ix_agent_prompt_filename", "filename"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "sha256": self.sha256,
            "size": len(self.body or ""),
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
            "source": self.source,
        }


class EvalRun(Base):
    """V2.3 — Historial de corridas de evals golden (golden loop).

    Persiste el resultado de cada corrida del daemon programado (o promote) para
    correlacionar score con `prompt_sha` (V1.1) en el tiempo. Tabla nueva ⇒
    Base.metadata.create_all la crea sin migración destructiva.
    """

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    agent_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    scores_json: Mapped[str] = mapped_column(Text, default="[]")
    prompt_sha: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    def to_dict(self) -> dict:
        import json as _json

        try:
            scores = _json.loads(self.scores_json or "[]")
        except (ValueError, TypeError):
            scores = []
        return {
            "id": self.id,
            "ran_at": self.ran_at.isoformat() if self.ran_at else None,
            "agent_type": self.agent_type,
            "passed": self.passed,
            "failed": self.failed,
            "scores": scores,
            "prompt_sha": self.prompt_sha,
        }
