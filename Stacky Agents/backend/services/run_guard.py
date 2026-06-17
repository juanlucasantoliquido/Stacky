"""V0.2 — Guard anti-duplicados en el launch.

Detecta si ya hay un run activo (preparing/running) para el mismo
ticket_id + agent_type. El endpoint de launch lo usa para devolver 409
salvo que el payload traiga force=true.

PURO respecto de Flask: recibe la session; no abre transacciones propias.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models import AgentExecution

# Estados considerados "activos" (un run en estos NO terminó).
# Alineado con services/agent_completion.py y services/manifest_watcher.py.
ACTIVE_STATUSES = ("preparing", "running", "queued")


def find_active_run(session, ticket_id: int, agent_type: str):
    """Devuelve la AgentExecution activa más reciente para ticket+agente, o None.

    Activa = status en ACTIVE_STATUSES. Runs en estado terminal
    (completed/error/needs_review) no bloquean.
    """
    from models import AgentExecution

    return (
        session.query(AgentExecution)
        .filter(
            AgentExecution.ticket_id == ticket_id,
            AgentExecution.agent_type == agent_type,
            AgentExecution.status.in_(ACTIVE_STATUSES),
        )
        .order_by(AgentExecution.id.desc())
        .first()
    )
