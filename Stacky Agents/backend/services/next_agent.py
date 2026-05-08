"""
FA-42 — Suggested next agent (markov chain on agent transitions).

Después de aprobar un Run, sugerir cuál es el agente que históricamente
los operadores corren a continuación, con qué frecuencia. Aprende de los
caminos populares sin imponer pipeline rígido.

Heurística: para cada transición Agent_A → Agent_B (mismo ticket, dentro
de una ventana de 24h), incrementamos el contador. Devolvemos top-K
sucesores con probabilidad relativa.

Fallback (sin datos): tabla DEFAULT_NEXT con cadena clásica de Stacky.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import asc

from db import session_scope
from models import AgentExecution


# Sucesión clásica del pipeline (cuando no hay data histórica suficiente).
DEFAULT_NEXT: dict[str, list[str]] = {
    "business":   ["functional"],
    "functional": ["technical"],
    "technical":  ["developer"],
    "developer":  ["qa"],
    "qa":         [],
}


@dataclass
class Suggestion:
    agent_type: str
    probability: float
    sample_size: int
    source: str  # "history" | "default"

    def to_dict(self) -> dict:
        return {
            "agent_type": self.agent_type,
            "probability": round(self.probability, 3),
            "sample_size": self.sample_size,
            "source": self.source,
        }


def _collect_transitions(min_sample: int = 10) -> dict[str, dict[str, int]]:
    """Lee la BD y arma una matriz from_agent → next_agent → count."""
    matrix: dict[str, dict[str, int]] = {}
    with session_scope() as session:
        rows = (
            session.query(AgentExecution)
            .filter(AgentExecution.verdict == "approved")
            .order_by(asc(AgentExecution.ticket_id), asc(AgentExecution.started_at))
            .limit(5000)
            .all()
        )
        prev_by_ticket: dict[int, AgentExecution] = {}
        for r in rows:
            prev = prev_by_ticket.get(r.ticket_id)
            if prev and (r.started_at - prev.started_at) < timedelta(hours=24):
                from_a = prev.agent_type
                to_a = r.agent_type
                matrix.setdefault(from_a, {})
                matrix[from_a][to_a] = matrix[from_a].get(to_a, 0) + 1
            prev_by_ticket[r.ticket_id] = r
    # Filtrar columnas con muestra muy chica
    return matrix


def suggest(*, after_agent: str, k: int = 2) -> list[Suggestion]:
    matrix = _collect_transitions()
    row = matrix.get(after_agent, {})
    total = sum(row.values())

    if total >= 5:
        items = sorted(row.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [
            Suggestion(
                agent_type=ag,
                probability=count / total,
                sample_size=total,
                source="history",
            )
            for ag, count in items
        ]

    # Fallback: default chain
    defaults = DEFAULT_NEXT.get(after_agent, [])
    return [
        Suggestion(agent_type=ag, probability=0.5, sample_size=0, source="default")
        for ag in defaults[:k]
    ]
