"""
Servicio de gestión de estados internos de tickets en Stacky.

Responsabilidades:
- Mantener `stacky_status` en la tabla `tickets` (estado actual, query O(1)).
- Registrar cada transición en `ticket_status_events` (historial append-only).
- Exponer hooks pre/post ejecución llamados desde `agent_runner`.
- Proveer un registro extensible de hooks adicionales (pre/post) para
  funcionalidades futuras (SSE, ADO publish, notificaciones, etc.).

Estados válidos de stacky_status:
  idle        → Ningún agente corriendo, ticket disponible (valor por defecto).
  running     → Un agente está en ejecución activa sobre este ticket.
  completed   → La última ejecución terminó correctamente.
  error       → La última ejecución terminó en error.
  cancelled   → La última ejecución fue cancelada por el operador.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, session_scope
from models import Ticket

logger = logging.getLogger("stacky.ticket_status")

VALID_STATUSES = frozenset({"idle", "running", "completed", "error", "cancelled"})


# ── Modelo ORM ────────────────────────────────────────────────────────────────


class TicketStatusEvent(Base):
    """Historial append-only de transiciones de estado de tickets en Stacky."""

    __tablename__ = "ticket_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable porque puede ser un cambio manual (sin ejecución asociada)
    execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="SET NULL")
    )
    agent_type: Mapped[str | None] = mapped_column(String(30))
    old_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(200), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    # Texto libre para contexto adicional (mensajes de error, motivos, etc.)
    reason: Mapped[str | None] = mapped_column(Text)
    # JSON arbitrario para hooks futuros y auditoría extendida
    metadata_json: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_tse_ticket_ts", "ticket_id", "changed_at"),
        Index("ix_tse_execution", "execution_id"),
        Index("ix_tse_new_status", "new_status"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "execution_id": self.execution_id,
            "agent_type": self.agent_type,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "changed_by": self.changed_by,
            "changed_at": self.changed_at.isoformat(),
            "reason": self.reason,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else None,
        }


# ── API pública del servicio ───────────────────────────────────────────────────


def set_status(
    ticket_id: int,
    new_status: str,
    *,
    changed_by: str,
    execution_id: int | None = None,
    agent_type: str | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
) -> TicketStatusEvent:
    """Actualiza stacky_status en Ticket y registra la transición en el historial.

    No lanza excepción si el ticket no existe: loguea advertencia y retorna None.
    """
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Estado inválido: '{new_status}'. Válidos: {sorted(VALID_STATUSES)}")

    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            logger.warning("set_status: ticket_id=%d no encontrado — ignorado", ticket_id)
            return None  # type: ignore[return-value]

        old_status = getattr(ticket, "stacky_status", None)

        # Evitar duplicar eventos si el estado no cambió
        if old_status == new_status:
            logger.debug(
                "set_status: ticket_id=%d ya estaba en '%s' — sin cambio", ticket_id, new_status
            )

        ticket.stacky_status = new_status  # type: ignore[attr-defined]

        event = TicketStatusEvent(
            ticket_id=ticket_id,
            execution_id=execution_id,
            agent_type=agent_type,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            reason=reason,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        session.add(event)
        session.flush()

        logger.info(
            "ticket_id=%d: '%s' → '%s' (exec=%s, by=%s)",
            ticket_id,
            old_status,
            new_status,
            execution_id,
            changed_by,
        )
        return event


def get_current_status(ticket_id: int) -> str | None:
    """Devuelve el stacky_status actual del ticket, o None si no existe."""
    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            return None
        return getattr(ticket, "stacky_status", None) or "idle"


def get_history(ticket_id: int, limit: int = 50) -> list[dict]:
    """Devuelve el historial de transiciones del ticket, más recientes primero."""
    with session_scope() as session:
        rows = (
            session.query(TicketStatusEvent)
            .filter(TicketStatusEvent.ticket_id == ticket_id)
            .order_by(TicketStatusEvent.changed_at.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]


def get_running_tickets() -> list[int]:
    """Retorna lista de ticket_ids cuyo stacky_status es 'running'.

    Útil para el startup recovery y para bloquear ejecuciones simultáneas.
    """
    with session_scope() as session:
        rows = (
            session.query(Ticket.id)
            .filter(Ticket.stacky_status == "running")  # type: ignore[attr-defined]
            .all()
        )
        return [r[0] for r in rows]


# ── Hooks de ciclo de vida ─────────────────────────────────────────────────────


def on_execution_start(
    *,
    ticket_id: int,
    execution_id: int,
    agent_type: str,
    user: str,
) -> None:
    """Hook pre-ejecución: se llama justo antes de lanzar el thread del agente.

    Marca el ticket como 'running' y ejecuta hooks adicionales registrados.
    """
    set_status(
        ticket_id,
        "running",
        changed_by=user,
        execution_id=execution_id,
        agent_type=agent_type,
        reason=f"Agent {agent_type} started (execution_id={execution_id})",
    )
    _run_pre_hooks(ticket_id=ticket_id, execution_id=execution_id, agent_type=agent_type, user=user)


def on_execution_end(
    *,
    ticket_id: int,
    execution_id: int,
    final_status: str,
    agent_type: str | None = None,
    error: str | None = None,
) -> None:
    """Hook post-ejecución: se llama al terminar el agente (cualquier outcome).

    Actualiza el estado del ticket y ejecuta hooks adicionales registrados.
    """
    reason = error if error else f"Execution {execution_id} ended: {final_status}"
    metadata = {"error": error} if error else None

    set_status(
        ticket_id,
        final_status,
        changed_by="system",
        execution_id=execution_id,
        agent_type=agent_type,
        reason=reason,
        metadata=metadata,
    )
    _run_post_hooks(
        ticket_id=ticket_id,
        execution_id=execution_id,
        final_status=final_status,
        agent_type=agent_type,
        error=error,
    )


# ── Registro de hooks extensibles ─────────────────────────────────────────────

# Cada callable recibe: ticket_id, execution_id, agent_type, user
_PRE_HOOKS: list[Callable] = []

# Cada callable recibe: ticket_id, execution_id, final_status, agent_type, error
_POST_HOOKS: list[Callable] = []


def register_pre_hook(fn: Callable) -> None:
    """Registra un callable a ejecutar antes de cada ejecución de agente.

    La firma esperada: fn(*, ticket_id, execution_id, agent_type, user, **kwargs)
    Los hooks nunca bloquean la ejecución principal: los errores se loguean.
    """
    _PRE_HOOKS.append(fn)
    logger.debug("pre_hook registrado: %s", getattr(fn, "__name__", repr(fn)))


def register_post_hook(fn: Callable) -> None:
    """Registra un callable a ejecutar después de cada ejecución de agente.

    La firma esperada: fn(*, ticket_id, execution_id, final_status, agent_type, error, **kwargs)
    Los hooks nunca bloquean la ejecución principal: los errores se loguean.
    """
    _POST_HOOKS.append(fn)
    logger.debug("post_hook registrado: %s", getattr(fn, "__name__", repr(fn)))


def _run_pre_hooks(**kwargs: Any) -> None:
    for hook in _PRE_HOOKS:
        try:
            hook(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pre_hook '%s' falló: %s", getattr(hook, "__name__", "?"), exc)


def _run_post_hooks(**kwargs: Any) -> None:
    for hook in _POST_HOOKS:
        try:
            hook(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("post_hook '%s' falló: %s", getattr(hook, "__name__", "?"), exc)


# ── Startup recovery ───────────────────────────────────────────────────────────


def recover_stale_running_tickets(trigger: str = "startup") -> list[dict]:
    """Corrige tickets con stacky_status='running' cuya ejecución ya terminó.

    Extiende el comportamiento original (P1) con:
    - Soporte para ejecuciones activas con timeout (EXECUTION_TIMEOUT_MINUTES).
    - completion_source='recovery' en AgentExecution si el campo existe (P2).
    - Detalle por ticket retornado como lista de dicts (compatibilidad §B-3).
    - Trigger registrado en evento (startup | manual | reaper).

    Retorna lista de dicts con detalle de cada corrección.
    """
    import os as _os
    from datetime import timedelta
    from models import AgentExecution  # import local para evitar ciclo

    timeout_minutes = int(_os.getenv("EXECUTION_TIMEOUT_MINUTES", "120"))
    timeout_cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)

    details: list[dict] = []

    with session_scope() as session:
        # --- Caso A: tickets marcados running pero con ejecuciones ya terminadas ---
        stale_tickets = (
            session.query(Ticket)
            .filter(Ticket.stacky_status == "running")  # type: ignore[attr-defined]
            .all()
        )
        for ticket in stale_tickets:
            last_exec = (
                session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == ticket.id)
                .order_by(AgentExecution.started_at.desc())
                .first()
            )
            if last_exec and last_exec.status in ("completed", "error", "cancelled"):
                recovered_status = last_exec.status
                ticket.stacky_status = recovered_status  # type: ignore[attr-defined]

                # Marcar completion_source si el campo existe (P2)
                if hasattr(last_exec, "completion_source") and not last_exec.completion_source:
                    last_exec.completion_source = "recovery"

                event = TicketStatusEvent(
                    ticket_id=ticket.id,
                    execution_id=last_exec.id,
                    agent_type=last_exec.agent_type,
                    old_status="running",
                    new_status=recovered_status,
                    changed_by=f"system:recovery:{trigger}",
                    reason=f"Recovered stale 'running' status [{trigger}]",
                )
                session.add(event)
                details.append({
                    "ticket_id": ticket.id,
                    "ado_id": ticket.ado_id,
                    "old_status": "running",
                    "new_status": recovered_status,
                    "execution_id": last_exec.id,
                    "agent_type": last_exec.agent_type,
                    "kind": "execution_ended",
                    "reason": "Last execution was already terminal",
                    "trigger": trigger,
                })
                logger.info(
                    "recovery[%s]: ticket_id=%d → '%s' (last_exec=%d)",
                    trigger, ticket.id, recovered_status, last_exec.id,
                )

            elif last_exec is None:
                # Ticket marcado como running pero sin ejecuciones — resetear a idle
                ticket.stacky_status = "idle"  # type: ignore[attr-defined]
                event = TicketStatusEvent(
                    ticket_id=ticket.id,
                    old_status="running",
                    new_status="idle",
                    changed_by=f"system:recovery:{trigger}",
                    reason=f"No executions found for ticket marked as running [{trigger}]",
                )
                session.add(event)
                details.append({
                    "ticket_id": ticket.id,
                    "ado_id": ticket.ado_id,
                    "old_status": "running",
                    "new_status": "idle",
                    "execution_id": None,
                    "agent_type": None,
                    "kind": "no_execution",
                    "reason": "No executions found — reset to idle",
                    "trigger": trigger,
                })
                logger.info(
                    "recovery[%s]: ticket_id=%d sin ejecuciones → 'idle'",
                    trigger, ticket.id,
                )

        # --- Caso B: ejecuciones activas con timeout (Reaper) ---
        timed_out_execs = (
            session.query(AgentExecution)
            .filter(
                AgentExecution.status.in_(["running", "queued"]),
                AgentExecution.started_at < timeout_cutoff,
            )
            .all()
        )
        for exec_row in timed_out_execs:
            old_exec_status = exec_row.status
            exec_row.status = "error"
            exec_row.completed_at = datetime.utcnow()
            exec_row.error_message = (
                f"Ejecución cerrada por timeout ({timeout_minutes} min) vía reaper [{trigger}]"
            )
            # Marcar completion_source='recovery' (P2)
            if hasattr(exec_row, "completion_source"):
                exec_row.completion_source = "recovery"

            # También corregir stacky_status del ticket si está running
            ticket_of_exec = session.get(Ticket, exec_row.ticket_id)
            if ticket_of_exec and ticket_of_exec.stacky_status == "running":
                ticket_of_exec.stacky_status = "error"
                event = TicketStatusEvent(
                    ticket_id=exec_row.ticket_id,
                    execution_id=exec_row.id,
                    agent_type=exec_row.agent_type,
                    old_status="running",
                    new_status="error",
                    changed_by=f"system:reaper:{trigger}",
                    reason=f"Execution timed out after {timeout_minutes} min [{trigger}]",
                )
                session.add(event)

            details.append({
                "ticket_id": exec_row.ticket_id,
                "ado_id": getattr(ticket_of_exec, "ado_id", None) if ticket_of_exec else None,
                "old_status": old_exec_status,
                "new_status": "error",
                "execution_id": exec_row.id,
                "agent_type": exec_row.agent_type,
                "kind": "execution_timeout",
                "reason": f"Execution running for >{timeout_minutes} min",
                "trigger": trigger,
                "completion_source": "recovery",
            })
            logger.warning(
                "reaper[%s]: exec_id=%d ticket_id=%d timed_out after %d min",
                trigger, exec_row.id, exec_row.ticket_id, timeout_minutes,
            )

    return details


def stop_stale_recovery() -> None:
    """No-op compatibility shim — el recovery es on-demand, no hay thread que detener.

    Existe para compatibilidad con tests que importan esta función.
    """
    pass
