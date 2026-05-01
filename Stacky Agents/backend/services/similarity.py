"""
FA-45 + FA-14 — Similar past executions + Output graveyard search.

Búsqueda de ejecuciones por similitud textual sobre input_context y output.
Fase 3 actual: Jaccard sobre n-grams de palabras (sin embeddings).
Fase 6 (FA-01): reemplazar por embeddings + pgvector / FAISS.

Uso:
- FA-45: dado un ticket + agent_type, devuelve top-K execs similares aprobadas.
- FA-14: dado un texto query, devuelve top-K execs descartadas (graveyard).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import or_

from db import session_scope
from models import AgentExecution, Ticket


_TOKEN_RE = re.compile(r"[a-záéíóúñ0-9]{3,}", re.IGNORECASE)


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _exec_text(execution: AgentExecution) -> str:
    """Combina contexto + output en un solo string para tokenizar."""
    parts: list[str] = []
    for block in (execution.input_context or []):
        if block.get("title"):
            parts.append(block["title"])
        if block.get("content"):
            parts.append(block["content"])
    if execution.output:
        parts.append(execution.output)
    return "\n".join(parts)


@dataclass
class SimilarHit:
    execution_id: int
    ticket_ado_id: int
    agent_type: str
    score: float
    started_at: str | None
    verdict: str | None
    snippet: str

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "ticket_ado_id": self.ticket_ado_id,
            "agent_type": self.agent_type,
            "score": round(self.score, 3),
            "started_at": self.started_at,
            "verdict": self.verdict,
            "snippet": self.snippet,
        }


def _build_snippet(text: str, query_tokens: set[str], max_len: int = 220) -> str:
    """Devuelve un fragmento del texto donde aparezcan tokens de la query."""
    if not text:
        return ""
    lower = text.lower()
    best_pos = 0
    best_hits = 0
    window = 220
    for pos in range(0, max(1, len(text) - window), window // 2):
        chunk = lower[pos:pos + window]
        hits = sum(1 for t in query_tokens if t in chunk)
        if hits > best_hits:
            best_hits = hits
            best_pos = pos
    snippet = text[best_pos:best_pos + max_len].strip().replace("\n", " ")
    if best_pos > 0:
        snippet = "…" + snippet
    if best_pos + max_len < len(text):
        snippet = snippet + "…"
    return snippet


# ---------------------------------------------------------------------------
# FA-45 — similar approved executions for a ticket+agent
# ---------------------------------------------------------------------------

def find_similar(
    *,
    ticket_id: int,
    agent_type: str | None = None,
    limit: int = 5,
    min_score: float = 0.05,
) -> list[SimilarHit]:
    """Top-K execs aprobadas con verdict=approved similares al ticket dado.
    Excluye execs del mismo ticket. Útil para auto-fill inteligente."""
    with session_scope() as session:
        ref_ticket = session.get(Ticket, ticket_id)
        if ref_ticket is None:
            return []
        ref_text = " ".join([ref_ticket.title or "", ref_ticket.description or ""])
        ref_tokens = _tokenize(ref_text)
        if not ref_tokens:
            return []

        q = (
            session.query(AgentExecution, Ticket)
            .join(Ticket, Ticket.id == AgentExecution.ticket_id)
            .filter(AgentExecution.ticket_id != ticket_id)
            .filter(AgentExecution.verdict == "approved")
        )
        if agent_type:
            q = q.filter(AgentExecution.agent_type == agent_type)
        rows = q.order_by(AgentExecution.started_at.desc()).limit(200).all()

        hits: list[SimilarHit] = []
        for execution, ticket in rows:
            ex_text = _exec_text(execution)
            ex_tokens = _tokenize(ex_text + " " + (ticket.title or ""))
            score = _jaccard(ref_tokens, ex_tokens)
            if score < min_score:
                continue
            hits.append(
                SimilarHit(
                    execution_id=execution.id,
                    ticket_ado_id=ticket.ado_id,
                    agent_type=execution.agent_type,
                    score=score,
                    started_at=execution.started_at.isoformat() if execution.started_at else None,
                    verdict=execution.verdict,
                    snippet=_build_snippet(ex_text, ref_tokens),
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]


# ---------------------------------------------------------------------------
# FA-14 — graveyard: search discarded outputs
# ---------------------------------------------------------------------------

def search_graveyard(
    *,
    query: str,
    agent_type: str | None = None,
    limit: int = 10,
    min_score: float = 0.05,
) -> list[SimilarHit]:
    """Busca outputs descartados ('discarded' status o discarded verdict, o errors)
    cuya texto sea similar al query. Útil para evitar repetir soluciones rechazadas."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    with session_scope() as session:
        q = (
            session.query(AgentExecution, Ticket)
            .join(Ticket, Ticket.id == AgentExecution.ticket_id)
            .filter(
                or_(
                    AgentExecution.verdict == "discarded",
                    AgentExecution.status == "discarded",
                    AgentExecution.status == "error",
                )
            )
        )
        if agent_type:
            q = q.filter(AgentExecution.agent_type == agent_type)
        rows = q.order_by(AgentExecution.started_at.desc()).limit(300).all()

        hits: list[SimilarHit] = []
        for execution, ticket in rows:
            ex_text = _exec_text(execution)
            ex_tokens = _tokenize(ex_text + " " + (ticket.title or ""))
            score = _jaccard(query_tokens, ex_tokens)
            if score < min_score:
                continue
            hits.append(
                SimilarHit(
                    execution_id=execution.id,
                    ticket_ado_id=ticket.ado_id,
                    agent_type=execution.agent_type,
                    score=score,
                    started_at=execution.started_at.isoformat() if execution.started_at else None,
                    verdict=execution.verdict or execution.status,
                    snippet=_build_snippet(ex_text, query_tokens),
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]
