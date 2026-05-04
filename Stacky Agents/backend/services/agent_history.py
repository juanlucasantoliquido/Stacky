"""
agent_history — Historial de tickets por agente VS Code.

Cada agente VS Code está representado por un archivo `.agent.md` (ej:
"DevPacifico.agent.md"). Las ejecuciones registradas en BD usan la taxonomía
legada de `agent_type` ("business", "functional", "technical", "developer",
"qa", "custom"). Este servicio:

1. Mapea filename → agent_type usando heurística de keywords (mismo criterio
   que `EmployeeCard.inferType` en el frontend).
2. Consulta `agent_executions` filtrando por ese agent_type, agrupa por
   ticket y devuelve la última ejecución de cada ticket.

Limitación conocida: la relación filename → agent_type es many-to-one, así
que dos agentes VS Code que mapean al mismo `agent_type` (ej. dos agentes
de tipo "developer") compartirán el historial. Esto se documenta en el
contrato y en la UI; una mejora futura puede agregar `agent_filename` como
columna en `AgentExecution` para discriminar finamente.

Esta función es read-only y no muta nada.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from models import AgentExecution, Ticket


# Lista canónica de tipos legados, alineada con `agents.list_agents()` y
# `frontend/src/types.ts`. "custom" no se infiere automáticamente.
LEGACY_AGENT_TYPES: tuple[str, ...] = (
    "business",
    "functional",
    "technical",
    "developer",
    "qa",
)


def infer_legacy_type(filename: str) -> str:
    """Heurística filename → agent_type.

    Espejo de `inferType()` en `frontend/src/components/EmployeeCard.tsx`.
    Mantener ambos sincronizados.
    """
    f = (filename or "").lower()
    if "business" in f or "negocio" in f:
        return "business"
    if "functional" in f or "funcional" in f:
        return "functional"
    if "technical" in f or "tecnic" in f:
        return "technical"
    if "dev" in f or "desarrollador" in f:
        return "developer"
    if "qa" in f or "test" in f:
        return "qa"
    return "custom"


@dataclass
class TicketHistoryEntry:
    """Una entrada del historial: un ticket con su última ejecución para el agente."""

    ticket_id: int
    ado_id: int
    title: str
    project: str | None
    ado_state: str | None
    ado_url: str | None
    last_execution_id: int
    last_execution_status: str
    last_execution_verdict: str | None
    last_execution_started_at: str | None
    last_execution_completed_at: str | None
    last_execution_duration_ms: int | None
    executions_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "ado_id": self.ado_id,
            "title": self.title,
            "project": self.project,
            "ado_state": self.ado_state,
            "ado_url": self.ado_url,
            "last_execution_id": self.last_execution_id,
            "last_execution_status": self.last_execution_status,
            "last_execution_verdict": self.last_execution_verdict,
            "last_execution_started_at": self.last_execution_started_at,
            "last_execution_completed_at": self.last_execution_completed_at,
            "last_execution_duration_ms": self.last_execution_duration_ms,
            "executions_count": self.executions_count,
        }


def history_for_filename(
    session: Session,
    filename: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Devuelve historial de tickets para un agente VS Code.

    Parámetros
    ----------
    session : Session
        Sesión SQLAlchemy abierta (la maneja el caller).
    filename : str
        Nombre del archivo .agent.md (ej: "DevPacifico.agent.md").
    limit : int
        Máximo de tickets a devolver.

    Retorna
    -------
    dict con la forma:
        {
            "agent_filename": str,
            "inferred_agent_type": str,
            "mapping_note": str,
            "tickets": [TicketHistoryEntry.to_dict()],
            "total_executions": int,
        }
    """
    agent_type = infer_legacy_type(filename)

    if agent_type == "custom":
        # No tenemos forma de filtrar ejecuciones "custom" por filename concreto;
        # devolvemos vacío con nota explicativa.
        return {
            "agent_filename": filename,
            "inferred_agent_type": agent_type,
            "mapping_note": (
                "Este agente no encaja en la taxonomía legada (business/functional/"
                "technical/developer/qa). El historial sólo registra ejecuciones del "
                "Workbench legado y aún no captura lanzamientos via VS Code Chat."
            ),
            "tickets": [],
            "total_executions": 0,
        }

    # Obtener todas las ejecuciones del tipo, agrupadas por ticket.
    rows: list[AgentExecution] = (
        session.query(AgentExecution)
        .filter(AgentExecution.agent_type == agent_type)
        .order_by(AgentExecution.started_at.desc())
        .all()
    )

    by_ticket: dict[int, list[AgentExecution]] = {}
    for row in rows:
        by_ticket.setdefault(row.ticket_id, []).append(row)

    # Conservar orden: los tickets aparecen ordenados por fecha de su última ejecución.
    ordered_ticket_ids = list(by_ticket.keys())

    if not ordered_ticket_ids:
        return {
            "agent_filename": filename,
            "inferred_agent_type": agent_type,
            "mapping_note": _mapping_note(agent_type),
            "tickets": [],
            "total_executions": 0,
        }

    # Cargar metadatos de los tickets en un solo query.
    tickets: dict[int, Ticket] = {
        t.id: t
        for t in session.query(Ticket)
        .filter(Ticket.id.in_(ordered_ticket_ids))
        .all()
    }

    entries: list[TicketHistoryEntry] = []
    for ticket_id in ordered_ticket_ids[:limit]:
        execs = by_ticket[ticket_id]
        last = execs[0]  # ya viene ordenado desc por started_at
        ticket = tickets.get(ticket_id)
        entries.append(
            TicketHistoryEntry(
                ticket_id=ticket_id,
                ado_id=ticket.ado_id if ticket else 0,
                title=ticket.title if ticket else f"(ticket {ticket_id} no encontrado)",
                project=ticket.project if ticket else None,
                ado_state=ticket.ado_state if ticket else None,
                ado_url=ticket.ado_url if ticket else None,
                last_execution_id=last.id,
                last_execution_status=last.status,
                last_execution_verdict=last.verdict,
                last_execution_started_at=(
                    last.started_at.isoformat() if last.started_at else None
                ),
                last_execution_completed_at=(
                    last.completed_at.isoformat() if last.completed_at else None
                ),
                last_execution_duration_ms=last.duration_ms(),
                executions_count=len(execs),
            )
        )

    return {
        "agent_filename": filename,
        "inferred_agent_type": agent_type,
        "mapping_note": _mapping_note(agent_type),
        "tickets": [e.to_dict() for e in entries],
        "total_executions": sum(len(v) for v in by_ticket.values()),
    }


def _mapping_note(agent_type: str) -> str:
    """Texto explicativo sobre el alcance del historial para un agent_type."""
    return (
        f"El historial muestra ejecuciones del Workbench legado mapeadas a "
        f"`agent_type={agent_type}`. Si tenés varios agentes VS Code que mapean "
        f"al mismo tipo, compartirán historial. Lanzamientos via VS Code Chat "
        f"(/open-chat) aún no se registran."
    )
