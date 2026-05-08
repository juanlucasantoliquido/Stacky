"""
FA-12 — Best-output few-shot examples.

Para cada Run, inyecta 1-2 outputs aprobados previos del mismo agent_type
en el sistema prompt como ejemplos. El agente aprende el estilo de la empresa
sin retraining: copia patrones, formato, nivel de detalle.

Reglas:
- Solo execs `verdict='approved'`.
- Excluye execs del mismo ticket (sin chivar).
- Prefiere execs con contract score alto y confidence alta.
- Cap por longitud para no inflar tokens (max ~1500 tokens por ejemplo).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from db import session_scope
from models import AgentExecution, Ticket


@dataclass
class FewShotExample:
    execution_id: int
    agent_type: str
    title_hint: str
    output: str

    def to_prompt(self) -> str:
        return (
            f"<example exec_id=\"{self.execution_id}\" hint=\"{self.title_hint}\">\n"
            f"{self.output}\n"
            f"</example>"
        )


def _safe_score(metadata_json: str | None, contract_json: str | None) -> tuple[int, int]:
    """Extrae (contract_score, confidence) si existen; sino devuelve (-1, -1)."""
    contract_score = -1
    conf = -1
    if contract_json:
        try:
            contract_score = int(json.loads(contract_json).get("score", -1))
        except Exception:
            pass
    if metadata_json:
        try:
            md = json.loads(metadata_json)
            conf = int(md.get("confidence", {}).get("overall", -1))
        except Exception:
            pass
    return contract_score, conf


def pick_examples(
    *,
    agent_type: str,
    project: str | None = None,
    exclude_ticket_id: int | None = None,
    k: int = 2,
    max_chars_per_example: int = 6000,
) -> list[FewShotExample]:
    """Selecciona top-K mejores execs aprobadas para usar como few-shot."""
    with session_scope() as session:
        q = (
            session.query(AgentExecution, Ticket)
            .join(Ticket, Ticket.id == AgentExecution.ticket_id)
            .filter(AgentExecution.agent_type == agent_type)
            .filter(AgentExecution.verdict == "approved")
            .filter(AgentExecution.output.isnot(None))
        )
        if project:
            q = q.filter(Ticket.project == project)
        if exclude_ticket_id is not None:
            q = q.filter(AgentExecution.ticket_id != exclude_ticket_id)
        rows = q.order_by(AgentExecution.started_at.desc()).limit(50).all()

        scored: list[tuple[float, AgentExecution, Ticket]] = []
        for execution, ticket in rows:
            cs, conf = _safe_score(execution.metadata_json, execution.contract_result_json)
            # Score combinado, sin penalizar si falta dato
            score = (cs if cs >= 0 else 70) * 0.6 + (conf if conf >= 0 else 70) * 0.4
            scored.append((score, execution, ticket))
        scored.sort(key=lambda t: t[0], reverse=True)

        examples: list[FewShotExample] = []
        for _, execution, ticket in scored[: k * 3]:  # margen para skipping
            text = execution.output or ""
            if len(text) > max_chars_per_example:
                text = text[:max_chars_per_example] + "\n\n[…truncado para few-shot]"
            examples.append(
                FewShotExample(
                    execution_id=execution.id,
                    agent_type=execution.agent_type,
                    title_hint=(ticket.title or "")[:80],
                    output=text,
                )
            )
            if len(examples) >= k:
                break
        return examples


def build_prefix(examples: list[FewShotExample]) -> str:
    if not examples:
        return ""
    body = "\n\n".join(e.to_prompt() for e in examples)
    return (
        "## Ejemplos de outputs aprobados (few-shot)\n"
        "Estos son outputs reales aprobados del mismo agente en este proyecto. "
        "Adoptá su estilo, estructura y nivel de detalle.\n\n"
        f"{body}\n\n"
        "## Fin de ejemplos\n"
    )
