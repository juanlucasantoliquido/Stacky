"""
FA-01 — Cross-ticket retrieval con embeddings (baseline TF-IDF).

Implementación pure-Python sin dependencias externas: TF-IDF cosine
similarity con vocabulario incremental. Mejor que el Jaccard de FA-45
(captura importancia de términos raros, descarta stop-words).

Cuando se sume sentence-transformers o pgvector, sólo cambia este módulo —
la API (`top_k`) sigue idéntica.

Tabla `execution_embeddings`:
  execution_id, term_freqs_json (CSV: term:count), doc_norm

El IDF se computa on-the-fly al hacer `top_k` desde el corpus actual.
Cache por hora.
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import Column, DateTime, Float, Index, Integer, Text
from datetime import datetime

from db import Base, session_scope
from models import AgentExecution, Ticket


_TOKEN_RE = re.compile(r"[a-záéíóúñ0-9]{3,}", re.IGNORECASE)
_STOPWORDS = {
    "the", "and", "for", "que", "con", "los", "las", "del", "una", "este",
    "esta", "como", "por", "para", "esto", "que", "all", "any", "are", "but",
    "not", "you", "his", "her", "him", "she", "they", "their",
    "ese", "esa", "eso", "ser", "haber", "tener", "fue", "muy",
}


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")
            if t.lower() not in _STOPWORDS]


class ExecutionEmbedding(Base):
    __tablename__ = "execution_embeddings"

    id = Column(Integer, primary_key=True)
    execution_id = Column(Integer, nullable=False, unique=True)
    term_freqs_json = Column(Text, nullable=False)
    doc_norm = Column(Float, nullable=False, default=0.0)
    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_embeddings_exec", "execution_id"),)


def _compute_tf(text: str) -> tuple[Counter, float]:
    tokens = _tokenize(text)
    if not tokens:
        return Counter(), 0.0
    tf = Counter(tokens)
    norm = math.sqrt(sum(c * c for c in tf.values()))
    return tf, norm


def index_execution(execution_id: int) -> None:
    """Computa y persiste el embedding TF para una exec."""
    with session_scope() as session:
        ex = session.get(AgentExecution, execution_id)
        if ex is None:
            return
        text_parts: list[str] = []
        for b in ex.input_context or []:
            if b.get("title"):
                text_parts.append(b["title"])
            if isinstance(b.get("content"), str):
                text_parts.append(b["content"])
        if ex.output:
            text_parts.append(ex.output)
        text = "\n".join(text_parts)

        tf, norm = _compute_tf(text)
        if not tf:
            return
        existing = session.query(ExecutionEmbedding).filter_by(
            execution_id=execution_id
        ).first()
        if existing is None:
            existing = ExecutionEmbedding(execution_id=execution_id)
            session.add(existing)
        existing.term_freqs_json = json.dumps(dict(tf))
        existing.doc_norm = norm
        existing.computed_at = datetime.utcnow()


@dataclass
class SemanticHit:
    execution_id: int
    ticket_ado_id: int
    agent_type: str
    score: float
    snippet: str

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "ticket_ado_id": self.ticket_ado_id,
            "agent_type": self.agent_type,
            "score": round(self.score, 3),
            "snippet": self.snippet,
        }


_idf_cache: dict[str, float] = {}
_idf_cache_built_at: float = 0
_IDF_TTL = 600.0  # 10 min


def _idf_corpus() -> dict[str, float]:
    """IDF (inverse document frequency) global computado del corpus actual."""
    global _idf_cache, _idf_cache_built_at
    if (time.time() - _idf_cache_built_at) < _IDF_TTL and _idf_cache:
        return _idf_cache

    df: Counter = Counter()
    n_docs = 0
    with session_scope() as session:
        embs = session.query(ExecutionEmbedding).all()
        n_docs = len(embs)
        for e in embs:
            try:
                terms = json.loads(e.term_freqs_json or "{}")
                for t in terms:
                    df[t] += 1
            except Exception:
                continue
    if n_docs == 0:
        return {}
    _idf_cache = {
        t: math.log((1 + n_docs) / (1 + c)) + 1.0 for t, c in df.items()
    }
    _idf_cache_built_at = time.time()
    return _idf_cache


def _query_vector(text: str, idf: dict[str, float]) -> tuple[dict[str, float], float]:
    tokens = _tokenize(text)
    if not tokens:
        return {}, 0.0
    tf = Counter(tokens)
    weighted = {t: c * idf.get(t, 1.0) for t, c in tf.items()}
    norm = math.sqrt(sum(v * v for v in weighted.values()))
    return weighted, norm


def top_k(
    *,
    query_text: str,
    agent_type: str | None = None,
    exclude_ticket_id: int | None = None,
    only_approved: bool = True,
    k: int = 5,
) -> list[SemanticHit]:
    """Retorna top-K execs más similares al query_text usando TF-IDF cosine."""
    if not query_text or not query_text.strip():
        return []
    idf = _idf_corpus()
    qvec, qnorm = _query_vector(query_text, idf)
    if qnorm == 0 or not qvec:
        return []

    hits: list[tuple[float, AgentExecution, Ticket]] = []
    with session_scope() as session:
        q = session.query(ExecutionEmbedding).join(
            AgentExecution, AgentExecution.id == ExecutionEmbedding.execution_id
        ).join(Ticket, Ticket.id == AgentExecution.ticket_id)
        if agent_type:
            q = q.filter(AgentExecution.agent_type == agent_type)
        if exclude_ticket_id is not None:
            q = q.filter(AgentExecution.ticket_id != exclude_ticket_id)
        if only_approved:
            q = q.filter(AgentExecution.verdict == "approved")

        embs = q.limit(500).all()
        for emb in embs:
            try:
                doc_tf = json.loads(emb.term_freqs_json or "{}")
            except Exception:
                continue
            doc_weighted = {t: c * idf.get(t, 1.0) for t, c in doc_tf.items()}
            doc_norm = math.sqrt(sum(v * v for v in doc_weighted.values()))
            if doc_norm == 0:
                continue
            common = set(qvec) & set(doc_weighted)
            if not common:
                continue
            dot = sum(qvec[t] * doc_weighted[t] for t in common)
            score = dot / (qnorm * doc_norm)
            if score < 0.05:
                continue
            ex = session.get(AgentExecution, emb.execution_id)
            if ex is None:
                continue
            tk = session.get(Ticket, ex.ticket_id)
            if tk is None:
                continue
            hits.append((score, ex, tk))

        hits.sort(key=lambda t: t[0], reverse=True)
        results: list[SemanticHit] = []
        for score, ex, tk in hits[:k]:
            snippet = (ex.output or "")[:240].replace("\n", " ")
            results.append(SemanticHit(
                execution_id=ex.id,
                ticket_ado_id=tk.ado_id,
                agent_type=ex.agent_type,
                score=score,
                snippet=snippet,
            ))
        return results


def reindex_all() -> int:
    """Re-indexa todas las execs aprobadas. Para uso administrativo."""
    count = 0
    with session_scope() as session:
        ids = [e.id for e in session.query(AgentExecution).filter(
            AgentExecution.output.isnot(None)
        ).all()]
    for eid in ids:
        index_execution(eid)
        count += 1
    global _idf_cache_built_at
    _idf_cache_built_at = 0  # invalidate
    return count
