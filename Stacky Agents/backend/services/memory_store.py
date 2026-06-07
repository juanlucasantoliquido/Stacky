"""Memoria colaborativa — Fase A: store local + búsqueda + inyección.

Plan: `docs/plans/plan-memoria-colaborativa-stacky-agents-2026-06-06-v2.md`.

Esta es la capa local (sin Git, sin gate pre-run). Mantiene una memoria
operativa del proyecto (decisiones, patrones, bugs aprendidos, preferencias,
políticas de cliente, resúmenes de sesión) que se puede:

  - guardar / upsertear por `topic_key` (con `revision_count`),
  - buscar por TF-IDF (mismo tokenizer que `services/embeddings.py`, SIN FTS5 —
    el build congelado no tiene FTS5 verificado y el patrón TF-IDF ya está
    probado en `embeddings.py`/`docs_rag.py`),
  - inyectar como bloque de contexto vía `context_enrichment` (user prompt).

Decisiones del v2 que materializa este módulo:
  - Roles = atribución, no autorización: `author_email`/`author_role` se guardan
    para auditoría; no hay enforcement (no existe sustrato de auth).
  - Solo se inyecta `status='active'`. `superseded`/`quarantined`/`draft`/...
    quedan fuera del contexto.
  - `get_context_for_run` es de dos fases: (1) candidatos por TF-IDF + filtro de
    status; (2) supresión por relaciones (oculta el lado viejo de `supersedes` —
    que además se marca `superseded`— y ambos lados de un `conflicts_with`
    activo-activo). Luego aplica caps por agente sobre el contenido.

La capa Git colaborativa (chunks append-only, outbox, push/pull) es Fase E y
NO vive acá.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    or_,
)

from db import Base, session_scope

# Reutilizamos el MISMO tokenizer que el retrieval TF-IDF existente (FA-01) para
# que la búsqueda de memoria se comporte igual que la de ejecuciones/docs.
from services.embeddings import _tokenize  # noqa: F401  (tokenizer compartido)


# ---------------------------------------------------------------------------
# Constantes de dominio
# ---------------------------------------------------------------------------

# Estados. Solo `active` se inyecta al contexto.
INJECTABLE_STATUSES = ("active",)
ALL_STATUSES = (
    "draft",
    "active",
    "needs_review",
    "superseded",
    "rejected",
    "quarantined",
    "deleted",
)

# Scopes que se inyectan a cualquier operador del proyecto. `personal`/`private`
# se excluyen de la inyección automática (requieren contexto de autor; Fase B).
INJECT_SCOPES = ("project", "team", "global")

# Relaciones soportadas (v1 §7.3).
RELATIONS = (
    "related",
    "compatible",
    "scoped",
    "conflicts_with",
    "supersedes",
    "duplicates",
    "not_conflict",
)

# Caps por agente (v1 §9.2): (max_memorias, max_chars). Per-agente autoritativo;
# `max_chars` es un techo absoluto por bloque.
_AGENT_CAPS: dict[str, tuple[int, int]] = {
    "business": (6, 6000),
    "functional": (10, 10000),
    "technical": (12, 12000),
    "developer": (14, 14000),
    "qa": (12, 12000),
    "pm": (12, 12000),
    "critic": (12, 12000),
    "debug": (12, 12000),
}
_DEFAULT_CAP = (10, 10000)


def _caps_for(agent_type: str | None) -> tuple[int, int]:
    return _AGENT_CAPS.get((agent_type or "").strip().lower(), _DEFAULT_CAP)


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class StackyMemoryObservation(Base):
    __tablename__ = "stacky_memory_observations"

    id = Column(Integer, primary_key=True)
    memory_id = Column(String(40), nullable=False, unique=True)
    project = Column(String(80), nullable=False)
    scope = Column(String(20), nullable=False, default="project")
    type = Column(String(40), nullable=False)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    topic_key = Column(String(200))
    status = Column(String(20), nullable=False, default="active")
    confidence = Column(Float)
    source_kind = Column(String(40))
    source_execution_id = Column(Integer)
    source_ticket_id = Column(Integer)
    source_ado_id = Column(Integer)
    source_agent_type = Column(String(40))
    author_email = Column(String(200))
    author_role = Column(String(40))
    tags_json = Column(Text)
    normalized_hash = Column(String(64))
    revision_count = Column(Integer, nullable=False, default=1)
    duplicate_count = Column(Integer, nullable=False, default=1)
    last_seen_at = Column(DateTime)
    review_after = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = Column(DateTime)

    __table_args__ = (
        Index("ix_stacky_mem_project_status", "project", "status"),
        Index("ix_stacky_mem_topic", "project", "scope", "topic_key"),
        Index("ix_stacky_mem_source_exec", "source_execution_id"),
        Index("ix_stacky_mem_hash", "project", "scope", "type", "normalized_hash"),
    )

    def tags(self) -> list[str]:
        try:
            data = json.loads(self.tags_json or "[]")
            return [str(t) for t in data] if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            return []

    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "project": self.project,
            "scope": self.scope,
            "type": self.type,
            "title": self.title,
            "content": self.content,
            "topic_key": self.topic_key,
            "status": self.status,
            "confidence": self.confidence,
            "source_kind": self.source_kind,
            "source_execution_id": self.source_execution_id,
            "source_ticket_id": self.source_ticket_id,
            "source_ado_id": self.source_ado_id,
            "source_agent_type": self.source_agent_type,
            "author_email": self.author_email,
            "author_role": self.author_role,
            "tags": self.tags(),
            "revision_count": self.revision_count,
            "duplicate_count": self.duplicate_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class StackyMemoryRelation(Base):
    __tablename__ = "stacky_memory_relations"

    id = Column(Integer, primary_key=True)
    relation_id = Column(String(40), nullable=False, unique=True)
    project = Column(String(80), nullable=False)
    source_memory_id = Column(String(40), nullable=False)
    target_memory_id = Column(String(40), nullable=False)
    relation = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="judged")
    reason = Column(Text)
    evidence = Column(Text)
    confidence = Column(Float)
    marked_by_actor = Column(String(200))
    marked_by_kind = Column(String(40))
    marked_by_model = Column(String(80))
    source_validation_run_id = Column(Integer)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_stacky_memrel_source", "source_memory_id", "relation"),
        Index("ix_stacky_memrel_target", "target_memory_id", "relation"),
    )

    def to_dict(self) -> dict:
        return {
            "relation_id": self.relation_id,
            "project": self.project,
            "source_memory_id": self.source_memory_id,
            "target_memory_id": self.target_memory_id,
            "relation": self.relation,
            "status": self.status,
            "reason": self.reason,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "marked_by_actor": self.marked_by_actor,
            "marked_by_kind": self.marked_by_kind,
            "marked_by_model": self.marked_by_model,
            "source_validation_run_id": self.source_validation_run_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _normalized_hash(title: str, content: str) -> str:
    norm = _WS_RE.sub(" ", f"{title or ''} {content or ''}".strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _topic_key_filter(query, *, project: str, scope: str, topic_key: str, author_email: str | None):
    """WHERE de unicidad de topic_key, scope-dependiente.

    Para `personal`/`private` la clave incluye `author_email` (si no, dos
    memorias personales de devs distintos se pisarían). Para el resto la clave
    es (project, scope, topic_key).
    """
    q = query.filter(
        StackyMemoryObservation.project == project,
        StackyMemoryObservation.scope == scope,
        StackyMemoryObservation.topic_key == topic_key,
        StackyMemoryObservation.deleted_at.is_(None),
    )
    if scope in ("personal", "private"):
        q = q.filter(StackyMemoryObservation.author_email == author_email)
    return q


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------

def save_observation(
    *,
    project: str,
    type: str,
    title: str,
    content: str,
    scope: str = "project",
    topic_key: str | None = None,
    status: str = "active",
    confidence: float | None = None,
    source_kind: str | None = None,
    source_execution_id: int | None = None,
    source_ticket_id: int | None = None,
    source_ado_id: int | None = None,
    source_agent_type: str | None = None,
    author_email: str | None = None,
    author_role: str | None = None,
    tags: Iterable[str] | None = None,
    expires_at: datetime | None = None,
) -> str:
    """Crea o (si hay `topic_key`) upsertea una memoria. Devuelve el `memory_id`.

    Si se pasa `topic_key` y ya existe una memoria con la misma clave de
    unicidad (scope-dependiente), se actualiza y se incrementa `revision_count`
    en vez de crear una fila nueva.
    """
    if topic_key:
        return upsert_by_topic_key(
            project=project,
            type=type,
            title=title,
            content=content,
            scope=scope,
            topic_key=topic_key,
            status=status,
            confidence=confidence,
            source_kind=source_kind,
            source_execution_id=source_execution_id,
            source_ticket_id=source_ticket_id,
            source_ado_id=source_ado_id,
            source_agent_type=source_agent_type,
            author_email=author_email,
            author_role=author_role,
            tags=tags,
            expires_at=expires_at,
        )

    memory_id = _new_id("mem")
    now = datetime.utcnow()
    with session_scope() as session:
        row = StackyMemoryObservation(
            memory_id=memory_id,
            project=project,
            scope=scope,
            type=type,
            title=title,
            content=content,
            topic_key=topic_key,
            status=status,
            confidence=confidence,
            source_kind=source_kind,
            source_execution_id=source_execution_id,
            source_ticket_id=source_ticket_id,
            source_ado_id=source_ado_id,
            source_agent_type=source_agent_type,
            author_email=author_email,
            author_role=author_role,
            tags_json=json.dumps(list(tags)) if tags else None,
            normalized_hash=_normalized_hash(title, content),
            revision_count=1,
            duplicate_count=1,
            last_seen_at=now,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
    return memory_id


def upsert_by_topic_key(
    *,
    project: str,
    type: str,
    title: str,
    content: str,
    scope: str = "project",
    topic_key: str,
    status: str = "active",
    confidence: float | None = None,
    source_kind: str | None = None,
    source_execution_id: int | None = None,
    source_ticket_id: int | None = None,
    source_ado_id: int | None = None,
    source_agent_type: str | None = None,
    author_email: str | None = None,
    author_role: str | None = None,
    tags: Iterable[str] | None = None,
    expires_at: datetime | None = None,
) -> str:
    """Upsert por `topic_key`. Incrementa `revision_count` si ya existía."""
    now = datetime.utcnow()
    with session_scope() as session:
        existing = (
            _topic_key_filter(
                session.query(StackyMemoryObservation),
                project=project,
                scope=scope,
                topic_key=topic_key,
                author_email=author_email,
            )
            .order_by(StackyMemoryObservation.updated_at.desc())
            .first()
        )
        if existing is not None:
            # No degradar una memoria ya aprobada: una captura DRAFT de un re-run
            # no debe pisar el status ni el contenido de una memoria ACTIVE
            # (la sacaría de la inyección). Promoción draft->active sí procede.
            if existing.status == "active" and status == "draft":
                existing.last_seen_at = now
                existing.updated_at = now
                session.flush()
                return existing.memory_id
            existing.type = type
            existing.title = title
            existing.content = content
            existing.status = status
            if confidence is not None:
                existing.confidence = confidence
            if tags is not None:
                existing.tags_json = json.dumps(list(tags))
            existing.normalized_hash = _normalized_hash(title, content)
            existing.revision_count = (existing.revision_count or 1) + 1
            existing.last_seen_at = now
            existing.updated_at = now
            if expires_at is not None:
                existing.expires_at = expires_at
            session.flush()
            return existing.memory_id

        memory_id = _new_id("mem")
        row = StackyMemoryObservation(
            memory_id=memory_id,
            project=project,
            scope=scope,
            type=type,
            title=title,
            content=content,
            topic_key=topic_key,
            status=status,
            confidence=confidence,
            source_kind=source_kind,
            source_execution_id=source_execution_id,
            source_ticket_id=source_ticket_id,
            source_ado_id=source_ado_id,
            source_agent_type=source_agent_type,
            author_email=author_email,
            author_role=author_role,
            tags_json=json.dumps(list(tags)) if tags else None,
            normalized_hash=_normalized_hash(title, content),
            revision_count=1,
            duplicate_count=1,
            last_seen_at=now,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        return memory_id


def set_status(memory_id: str, status: str) -> bool:
    """Cambia el `status` de una memoria. `deleted` setea también `deleted_at`."""
    with session_scope() as session:
        row = (
            session.query(StackyMemoryObservation)
            .filter(StackyMemoryObservation.memory_id == memory_id)
            .first()
        )
        if row is None:
            return False
        row.status = status
        row.updated_at = datetime.utcnow()
        if status == "deleted" and row.deleted_at is None:
            row.deleted_at = datetime.utcnow()
        return True


def mark_relation(
    *,
    project: str,
    source_memory_id: str,
    target_memory_id: str,
    relation: str,
    reason: str | None = None,
    evidence: str | None = None,
    confidence: float | None = None,
    marked_by_actor: str | None = None,
    marked_by_kind: str = "human",
    marked_by_model: str | None = None,
    status: str = "judged",
) -> str:
    """Registra una relación entre dos memorias.

    Para `supersedes` además marca la memoria TARGET (la vieja) como
    `superseded`, replicando el patrón de `decisions.py` — así el filtro de
    status en la búsqueda ya la excluye y solo hace falta la pasada de
    relaciones para `conflicts_with`.
    """
    if relation not in RELATIONS:
        raise ValueError(f"relación no soportada: {relation}")
    relation_id = _new_id("rel")
    now = datetime.utcnow()
    with session_scope() as session:
        rel = StackyMemoryRelation(
            relation_id=relation_id,
            project=project,
            source_memory_id=source_memory_id,
            target_memory_id=target_memory_id,
            relation=relation,
            status=status,
            reason=reason,
            evidence=evidence,
            confidence=confidence,
            marked_by_actor=marked_by_actor,
            marked_by_kind=marked_by_kind,
            marked_by_model=marked_by_model,
            created_at=now,
            updated_at=now,
        )
        session.add(rel)
        if relation == "supersedes":
            old = (
                session.query(StackyMemoryObservation)
                .filter(StackyMemoryObservation.memory_id == target_memory_id)
                .first()
            )
            if old is not None and old.status == "active":
                old.status = "superseded"
                old.updated_at = now
        session.flush()
    return relation_id


def resolve_conflicts_between(
    *,
    project: str,
    source_memory_id: str,
    target_memory_id: str,
    marked_by_actor: str | None = None,
    reason: str | None = None,
) -> str:
    """Marca un par como `not_conflict` y resuelve conflictos abiertos previos."""
    relation_id = mark_relation(
        project=project,
        source_memory_id=source_memory_id,
        target_memory_id=target_memory_id,
        relation="not_conflict",
        reason=reason,
        marked_by_actor=marked_by_actor,
        marked_by_kind="human",
        status="judged",
    )
    now = datetime.utcnow()
    with session_scope() as session:
        rels = (
            session.query(StackyMemoryRelation)
            .filter(
                StackyMemoryRelation.project == project,
                StackyMemoryRelation.relation == "conflicts_with",
                StackyMemoryRelation.status.notin_(("rejected", "resolved")),
                or_(
                    (
                        (StackyMemoryRelation.source_memory_id == source_memory_id)
                        & (StackyMemoryRelation.target_memory_id == target_memory_id)
                    ),
                    (
                        (StackyMemoryRelation.source_memory_id == target_memory_id)
                        & (StackyMemoryRelation.target_memory_id == source_memory_id)
                    ),
                ),
            )
            .all()
        )
        for rel in rels:
            rel.status = "resolved"
            rel.updated_at = now
    return relation_id


# ---------------------------------------------------------------------------
# Lectura / búsqueda
# ---------------------------------------------------------------------------

def get(memory_id: str) -> dict | None:
    with session_scope() as session:
        row = (
            session.query(StackyMemoryObservation)
            .filter(StackyMemoryObservation.memory_id == memory_id)
            .first()
        )
        return row.to_dict() if row is not None else None


def list_observations(
    *,
    project: str | None = None,
    status: str | None = None,
    scope: str | None = None,
    type: str | None = None,
    limit: int = 200,
) -> list[dict]:
    with session_scope() as session:
        q = session.query(StackyMemoryObservation).filter(
            StackyMemoryObservation.deleted_at.is_(None)
        )
        if project:
            q = q.filter(StackyMemoryObservation.project == project)
        if status:
            q = q.filter(StackyMemoryObservation.status == status)
        if scope:
            q = q.filter(StackyMemoryObservation.scope == scope)
        if type:
            q = q.filter(StackyMemoryObservation.type == type)
        rows = q.order_by(StackyMemoryObservation.updated_at.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def list_relations(
    *,
    project: str | None = None,
    relation: str | None = None,
    status: str | None = None,
    memory_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    with session_scope() as session:
        q = session.query(StackyMemoryRelation)
        if project:
            q = q.filter(StackyMemoryRelation.project == project)
        if relation:
            q = q.filter(StackyMemoryRelation.relation == relation)
        if status:
            q = q.filter(StackyMemoryRelation.status == status)
        if memory_id:
            q = q.filter(
                or_(
                    StackyMemoryRelation.source_memory_id == memory_id,
                    StackyMemoryRelation.target_memory_id == memory_id,
                )
            )
        rows = q.order_by(StackyMemoryRelation.updated_at.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def conflict_graph(*, project: str, status: str | None = None) -> dict:
    """Devuelve nodos/aristas de conflictos abiertos para la UI de curacion."""
    with session_scope() as session:
        rel_q = session.query(StackyMemoryRelation).filter(
            StackyMemoryRelation.project == project,
            StackyMemoryRelation.relation == "conflicts_with",
        )
        if status:
            rel_q = rel_q.filter(StackyMemoryRelation.status == status)
        else:
            rel_q = rel_q.filter(StackyMemoryRelation.status.notin_(("rejected", "resolved")))
        rels = rel_q.order_by(StackyMemoryRelation.updated_at.desc()).limit(500).all()
        ids = {r.source_memory_id for r in rels} | {r.target_memory_id for r in rels}
        rows = []
        if ids:
            rows = (
                session.query(StackyMemoryObservation)
                .filter(
                    StackyMemoryObservation.project == project,
                    StackyMemoryObservation.memory_id.in_(tuple(ids)),
                    StackyMemoryObservation.deleted_at.is_(None),
                )
                .all()
            )
        node_map = {r.memory_id: r.to_dict() for r in rows}
        return {
            "project": project,
            "nodes": list(node_map.values()),
            "edges": [r.to_dict() for r in rels],
        }


def _doc_text(row: StackyMemoryObservation) -> str:
    parts = [row.title or "", row.content or "", row.topic_key or ""]
    parts.extend(row.tags())
    return "\n".join(parts)


def search(
    *,
    project: str,
    query_text: str | None = None,
    scope: str | None = None,
    scopes: Iterable[str] | None = None,
    agent_type: str | None = None,
    types: Iterable[str] | None = None,
    statuses: Iterable[str] = INJECTABLE_STATUSES,
    k: int = 20,
) -> list[dict]:
    """Búsqueda TF-IDF sobre la memoria del proyecto.

    - `topic_key` exacto: si `query_text` empieza con una familia tipo
      `bug/...` (contiene `/` y sin espacios) se prioriza el match exacto por
      `topic_key`.
    - Si no hay query (o no tokeniza), cae a orden por recencia.

    Devuelve dicts con la forma de `to_dict()` más `_score`.
    """
    statuses = tuple(statuses)
    with session_scope() as session:
        q = session.query(StackyMemoryObservation).filter(
            StackyMemoryObservation.project == project,
            StackyMemoryObservation.deleted_at.is_(None),
        )
        if statuses:
            q = q.filter(StackyMemoryObservation.status.in_(statuses))
        if scopes:
            q = q.filter(StackyMemoryObservation.scope.in_(tuple(scopes)))
        elif scope:
            q = q.filter(StackyMemoryObservation.scope == scope)
        if types:
            q = q.filter(StackyMemoryObservation.type.in_(tuple(types)))
        rows = q.order_by(StackyMemoryObservation.updated_at.desc()).limit(2000).all()

        if not rows:
            return []

        # Camino topic_key exacto.
        qt = (query_text or "").strip()
        if qt and "/" in qt and " " not in qt:
            exact = [r for r in rows if (r.topic_key or "") == qt]
            if exact:
                results = []
                for r in exact[:k]:
                    d = r.to_dict()
                    d["_score"] = 1.0
                    results.append(d)
                return results

        query_tokens = _tokenize(qt) if qt else []
        if not query_tokens:
            # Sin query útil → recencia.
            results = []
            for r in rows[:k]:
                d = r.to_dict()
                d["_score"] = 0.0
                results.append(d)
            return results

        # TF-IDF sobre el corpus del proyecto (chico: scan en memoria).
        doc_tfs: list[tuple[StackyMemoryObservation, Counter]] = []
        df: Counter = Counter()
        for r in rows:
            tf = Counter(_tokenize(_doc_text(r)))
            doc_tfs.append((r, tf))
            for term in tf:
                df[term] += 1
        n_docs = len(doc_tfs)
        idf = {t: math.log((1 + n_docs) / (1 + c)) + 1.0 for t, c in df.items()}

        q_tf = Counter(query_tokens)
        q_weighted = {t: c * idf.get(t, 1.0) for t, c in q_tf.items()}
        q_norm = math.sqrt(sum(v * v for v in q_weighted.values()))
        if q_norm == 0:
            return []

        scored: list[tuple[float, StackyMemoryObservation]] = []
        for r, tf in doc_tfs:
            d_weighted = {t: c * idf.get(t, 1.0) for t, c in tf.items()}
            d_norm = math.sqrt(sum(v * v for v in d_weighted.values()))
            if d_norm == 0:
                continue
            common = set(q_weighted) & set(d_weighted)
            if not common:
                continue
            dot = sum(q_weighted[t] * d_weighted[t] for t in common)
            score = dot / (q_norm * d_norm)
            # Señal liviana 0..1: bonus si el agente coincide.
            if agent_type and (r.source_agent_type or "") == agent_type:
                score += 0.05
            if score <= 0:
                continue
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, r in scored[:k]:
            d = r.to_dict()
            d["_score"] = round(score, 4)
            results.append(d)
        return results


def _apply_conflict_suppression(
    project: str, candidates: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Segunda fase: oculta ambos lados de un `conflicts_with` activo-activo.

    (`supersedes` ya se resuelve por status: al crear la relación el lado viejo
    queda `superseded` y el filtro de status lo excluye.)
    Devuelve `(kept, suppressed)`.
    """
    if not candidates:
        return [], []
    ids = {c["memory_id"] for c in candidates}
    suppressed_ids: set[str] = set()
    with session_scope() as session:
        not_conflicts = (
            session.query(StackyMemoryRelation)
            .filter(
                StackyMemoryRelation.project == project,
                StackyMemoryRelation.relation == "not_conflict",
                StackyMemoryRelation.status.notin_(("rejected", "resolved")),
                or_(
                    StackyMemoryRelation.source_memory_id.in_(tuple(ids)),
                    StackyMemoryRelation.target_memory_id.in_(tuple(ids)),
                ),
            )
            .all()
        )
        allowed_pairs = {
            frozenset((rel.source_memory_id, rel.target_memory_id))
            for rel in not_conflicts
        }
        rels = (
            session.query(StackyMemoryRelation)
            .filter(
                StackyMemoryRelation.project == project,
                StackyMemoryRelation.relation == "conflicts_with",
                StackyMemoryRelation.status.notin_(("rejected", "resolved")),
                or_(
                    StackyMemoryRelation.source_memory_id.in_(tuple(ids)),
                    StackyMemoryRelation.target_memory_id.in_(tuple(ids)),
                ),
            )
            .all()
        )
        for rel in rels:
            pair = frozenset((rel.source_memory_id, rel.target_memory_id))
            if pair in allowed_pairs:
                continue
            if rel.source_memory_id in ids and rel.target_memory_id in ids:
                suppressed_ids.add(rel.source_memory_id)
                suppressed_ids.add(rel.target_memory_id)
    kept = [c for c in candidates if c["memory_id"] not in suppressed_ids]
    suppressed = [c for c in candidates if c["memory_id"] in suppressed_ids]
    return kept, suppressed


def _render_memory(items: list[dict]) -> str:
    lines: list[str] = []
    for it in items:
        header = f"### {it['title']}"
        meta_bits = [it.get("type")]
        if it.get("topic_key"):
            meta_bits.append(it["topic_key"])
        meta = " · ".join([b for b in meta_bits if b])
        if meta:
            header += f"  ({meta})"
        lines.append(header)
        lines.append((it.get("content") or "").strip())
        lines.append("")
    return "\n".join(lines).strip()


def get_context_for_run(
    *,
    project: str | None,
    agent_type: str | None,
    query_text: str | None,
    inject_scopes: Iterable[str] = INJECT_SCOPES,
    max_chars: int | None = None,
) -> dict:
    """Arma el bloque de memoria operativa para una ejecución.

    Devuelve:
      {
        "content": str,          # texto a inyectar (vacío si no hay nada)
        "hits": int,             # candidatos activos antes de supresión
        "active_hits": int,      # inyectados finalmente
        "suppressed_hits": int,  # ocultados por conflicto
        "memory_ids": [str, ...] # inyectados
      }
    """
    empty = {"content": "", "hits": 0, "active_hits": 0, "suppressed_hits": 0, "memory_ids": []}
    if not project:
        return empty

    max_memories, agent_max_chars = _caps_for(agent_type)
    char_cap = min(max_chars, agent_max_chars) if max_chars else agent_max_chars

    candidates = search(
        project=project,
        query_text=query_text,
        scopes=tuple(inject_scopes),
        agent_type=agent_type,
        statuses=INJECTABLE_STATUSES,
        k=max(max_memories * 3, 30),
    )
    if not candidates:
        return empty

    kept, suppressed = _apply_conflict_suppression(project, candidates)
    if not kept:
        return {**empty, "hits": len(candidates), "suppressed_hits": len(suppressed)}

    # Cap por cantidad.
    kept = kept[:max_memories]

    # Cap por chars: ir agregando hasta el techo (drop de menor rank primero).
    selected: list[dict] = []
    running = 0
    for it in kept:
        body = (it.get("content") or "")
        cost = len(it.get("title") or "") + len(body) + 64
        if selected and running + cost > char_cap:
            break
        selected.append(it)
        running += cost

    if not selected:
        return {**empty, "hits": len(candidates), "suppressed_hits": len(suppressed)}

    content = _render_memory(selected)
    if len(content) > char_cap:
        content = content[:char_cap].rstrip() + "\n…"

    return {
        "content": content,
        "hits": len(candidates),
        "active_hits": len(selected),
        "suppressed_hits": len(suppressed),
        "memory_ids": [it["memory_id"] for it in selected],
    }
