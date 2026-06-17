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
from services import pii_masker


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

# Tipos que los servicios FA-* ya inyectan por el SYSTEM prompt
# (decisions/anti_patterns/glossary/style). Para NO doble-inyectar el mismo
# conocimiento por el USER prompt (plan v2 §6/B5), el bloque `stacky-memory`
# los EXCLUYE de la inyección. Siguen guardándose/listándose/validándose: el
# filtro es solo del canal de inyección, no del store.
_SYSTEM_PROMPT_TYPES = frozenset(
    {"decision", "anti_pattern", "glossary", "term", "preference", "style"}
)

# V1.5 (B5) — Fuente ÚNICA de verdad del doble canal: los tipos que el filtro de
# inyección excluye del USER prompt son exactamente los que `POST /api/memory`
# rechaza (canal USER). La garantía pasa de convención a estructura: un solo set
# gobierna ambos lados. Alias público para que la API no toque el _privado.
RESERVED_TYPES = _SYSTEM_PROMPT_TYPES

# M3.1 — Tipos inyectables por el canal USER (informativo para la UI). NO es un
# allowlist que bloquee el alta (cualquier type no reservado se acepta): es la
# guía de tipos esperados, con `directive` como ciudadano de primera clase.
INJECTABLE_TYPES = (
    "bugfix",
    "pattern",
    "policy",
    "client_policy",
    "session_summary",
    "directive",
)

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


# M0.1 — Override configurable de caps vía STACKY_MEMORY_CAPS_JSON (env, OFF
# default = ""). Shape: {"developer": [16, 16000], ...}. El override es MERGE
# sobre _AGENT_CAPS: un agente ausente conserva su cap actual. Fail-safe: ante
# cualquier malformación se ignora la entrada inválida (o todo el JSON) y se cae
# a los defaults — mismo patrón que pricing._load_prices. Se cachea el parse por
# proceso, keyed por el valor crudo del env, para no parsear en cada run y para
# reflejar el hot-apply de flags sin reiniciar.
_CAPS_OVERRIDE_CACHE: dict[str, dict[str, tuple[int, int]]] = {}


def _invalidate_caps_cache() -> None:
    """Limpia el cache del override de caps (tras hot-apply de flags)."""
    _CAPS_OVERRIDE_CACHE.clear()


def _parse_caps_override(raw: str) -> dict[str, tuple[int, int]]:
    """Parsea STACKY_MEMORY_CAPS_JSON a {agent: (max_mem, max_chars)}.

    Ignora entradas inválidas (no [int, int] con ambos > 0). Ante JSON
    inválido o shape de tope no-dict, devuelve {} (todo a defaults).
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    parsed: dict[str, tuple[int, int]] = {}
    for agent, val in data.items():
        try:
            if not isinstance(val, (list, tuple)) or len(val) != 2:
                continue
            a, b = int(val[0]), int(val[1])
            if a <= 0 or b <= 0:
                continue
            parsed[str(agent).strip().lower()] = (a, b)
        except Exception:  # noqa: BLE001
            continue
    return parsed


def _load_caps_override() -> dict[str, tuple[int, int]]:
    import os

    raw = os.getenv("STACKY_MEMORY_CAPS_JSON", "") or ""
    if raw not in _CAPS_OVERRIDE_CACHE:
        _CAPS_OVERRIDE_CACHE.clear()  # cache de 1 entrada keyed por raw actual
        _CAPS_OVERRIDE_CACHE[raw] = _parse_caps_override(raw)
    return _CAPS_OVERRIDE_CACHE[raw]


def _caps_for(agent_type: str | None) -> tuple[int, int]:
    key = (agent_type or "").strip().lower()
    override = _load_caps_override()
    if key in override:
        return override[key]
    return _AGENT_CAPS.get(key, _DEFAULT_CAP)


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
    # M1.1 — Directiva como ciudadano de primera clase (add-only). Filas legacy:
    # enforcement=NULL (≡ suggest/observacional), priority=0, applies_to_json=NULL.
    enforcement = Column(String(12))          # None/"suggest" | "always"
    priority = Column(Integer, nullable=False, default=0)
    applies_to_json = Column(Text)            # targeting estructurado (JSON)
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

    def applies_to(self) -> dict:
        try:
            data = json.loads(self.applies_to_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

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
            "enforcement": self.enforcement,
            "priority": self.priority if self.priority is not None else 0,
            "applies_to": self.applies_to(),
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
# M1.1 — Targeting de directivas (puro, sin DB)
# ---------------------------------------------------------------------------

# Dimensiones válidas de `applies_to`. Contrato estricto (M2.1 rechaza otras).
APPLIES_TO_DIMENSIONS = (
    "agent_types",
    "projects",
    "work_item_types",
    "title_keywords",
    "tags",
)


def _norm_list(val) -> list[str]:
    if not isinstance(val, (list, tuple)):
        return []
    return [str(x).strip().lower() for x in val if str(x).strip()]


def directive_matches_run(
    applies_to: dict | None,
    *,
    agent_type: str | None = None,
    project: str | None = None,
    ticket_title: str | None = None,
    ticket_description: str | None = None,
    work_item_type: str | None = None,
) -> bool:
    """¿Una directiva con este `applies_to` matchea el run? AND multi-dimensión.

    - Una dimensión ausente o vacía = no restringe (matchea cualquier valor).
    - `agent_types`/`projects`/`work_item_types`: match exacto case-insensitive.
    - `title_keywords`: substring case-insensitive en title O description.
    - `tags`: NO participa del match de run (decisión M1.1; son del autor).
    Un `applies_to` totalmente vacío matchea TODO.
    """
    a = applies_to or {}
    if not isinstance(a, dict):
        return False

    agent_types = _norm_list(a.get("agent_types"))
    if agent_types and (agent_type or "").strip().lower() not in agent_types:
        return False

    projects = _norm_list(a.get("projects"))
    if projects and (project or "").strip().lower() not in projects:
        return False

    wits = _norm_list(a.get("work_item_types"))
    if wits and (work_item_type or "").strip().lower() not in wits:
        return False

    keywords = _norm_list(a.get("title_keywords"))
    if keywords:
        haystack = f"{ticket_title or ''}\n{ticket_description or ''}".lower()
        if not any(kw in haystack for kw in keywords):
            return False

    return True


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
    review_after: datetime | None = None,
    enforcement: str | None = None,
    priority: int = 0,
    applies_to_json: str | None = None,
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
            review_after=review_after,
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
            review_after=review_after,
            enforcement=enforcement,
            priority=priority or 0,
            applies_to_json=applies_to_json,
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
    review_after: datetime | None = None,
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
            if review_after is not None:
                existing.review_after = review_after
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
            review_after=review_after,
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


def update_observation(
    memory_id: str,
    *,
    title: str | None = None,
    content: str | None = None,
    enforcement: str | None = None,
    priority: int | None = None,
    applies_to_json: str | None = None,
    expires_at: datetime | None = None,
    review_after: datetime | None = None,
) -> bool:
    """M2.2 — Edita campos de una memoria por id (add-only, no destructivo).

    Solo toca los campos provistos (None = no tocar). Recalcula `normalized_hash`
    si cambió título/contenido, incrementa `revision_count` (auditoría) y
    `updated_at`. NO cambia `status` (eso es `set_status`), NO toca `topic_key`,
    NO crea fila nueva. Devuelve True si la fila existe.
    """
    with session_scope() as session:
        row = (
            session.query(StackyMemoryObservation)
            .filter(StackyMemoryObservation.memory_id == memory_id)
            .first()
        )
        if row is None:
            return False
        changed_text = False
        if title is not None:
            row.title = title
            changed_text = True
        if content is not None:
            row.content = content
            changed_text = True
        if enforcement is not None:
            row.enforcement = enforcement
        if priority is not None:
            row.priority = priority
        if applies_to_json is not None:
            row.applies_to_json = applies_to_json
        if expires_at is not None:
            row.expires_at = expires_at
        if review_after is not None:
            row.review_after = review_after
        if changed_text:
            row.normalized_hash = _normalized_hash(row.title or "", row.content or "")
        row.revision_count = (row.revision_count or 1) + 1
        row.updated_at = datetime.utcnow()
        return True


def mark_stale_for_review(*, project: str | None = None) -> int:
    """M0.3 — Marca `needs_review` las memorias `active` cuyo `review_after`
    venció. NUNCA borra ni desactiva (rule 11: solo mueve a needs_review; el
    humano decide). Devuelve cuántas marcó.
    """
    now = datetime.utcnow()
    marked = 0
    with session_scope() as session:
        q = session.query(StackyMemoryObservation).filter(
            StackyMemoryObservation.status == "active",
            StackyMemoryObservation.deleted_at.is_(None),
            StackyMemoryObservation.review_after.isnot(None),
            StackyMemoryObservation.review_after < now,
        )
        if project:
            q = q.filter(StackyMemoryObservation.project == project)
        for row in q.all():
            row.status = "needs_review"
            row.updated_at = now
            marked += 1
    return marked


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
            # M0.3 — una memoria expirada nunca entra al pool de candidatos.
            or_(
                StackyMemoryObservation.expires_at.is_(None),
                StackyMemoryObservation.expires_at > datetime.utcnow(),
            ),
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

        # I2.3 — OPT-IN: expansión de query (fold de acentos + sinónimos del
        # dominio) cuando STACKY_RETRIEVAL_EXPANSION_ENABLED=true. El corpus
        # (línea _tokenize(_doc_text(r))) NO cambia: solo el query se expande.
        # `_tokenize` global permanece idéntico (sin mutación).
        _do_expand = False
        try:
            import os as _os
            _raw = _os.getenv("STACKY_RETRIEVAL_EXPANSION_ENABLED", "false")
            _do_expand = _raw.lower() in ("1", "true", "yes")
        except Exception:  # noqa: BLE001
            pass

        if qt and _do_expand:
            from services.query_expansion import normalize_text, expand_query
            _qt_normalized = normalize_text(qt)
            _base_tokens = _tokenize(_qt_normalized)
            query_tokens = expand_query(_base_tokens)
        else:
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

        scored: list[tuple[float, float, StackyMemoryObservation]] = []
        for r, tf in doc_tfs:
            d_weighted = {t: c * idf.get(t, 1.0) for t, c in tf.items()}
            d_norm = math.sqrt(sum(v * v for v in d_weighted.values()))
            if d_norm == 0:
                continue
            common = set(q_weighted) & set(d_weighted)
            if not common:
                continue
            dot = sum(q_weighted[t] * d_weighted[t] for t in common)
            score = dot / (q_norm * d_norm)  # coseno ∈ [0,1]
            if score <= 0:
                continue
            # Ranking en 2 etapas: el coseno es la relevancia; el orden final se
            # decide por señales NORMALIZADAS 0..1 (relevancia + match de agente +
            # confianza), sin sumar indicadores crudos al coseno (plan v2 §4.3).
            agent_match = 1.0 if (agent_type and (r.source_agent_type or "") == agent_type) else 0.0
            conf = r.confidence if r.confidence is not None else 0.5
            conf = max(0.0, min(1.0, conf))
            composite = 0.75 * score + 0.15 * agent_match + 0.10 * conf
            scored.append((composite, score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _composite, score, r in scored[:k]:
            d = r.to_dict()
            d["_score"] = round(score, 4)  # se expone la relevancia (coseno), no el composite
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


def get_directives_for_run(
    *,
    project: str | None,
    agent_type: str | None = None,
    ticket_title: str | None = None,
    ticket_description: str | None = None,
    work_item_type: str | None = None,
    scopes: Iterable[str] = INJECT_SCOPES,
) -> list[dict]:
    """M1.2 — Directivas `enforcement=always` que matchean el targeting del run.

    Query RELACIONAL (sin TF-IDF, sin supresión de conflicto): una directiva
    obligatoria se inyecta SIEMPRE que el run matchee su targeting, ordenada por
    `priority` desc y luego `updated_at` desc. No compite en el pool léxico.
    """
    if not project:
        return []
    scopes = tuple(scopes)
    now = datetime.utcnow()
    with session_scope() as session:
        q = session.query(StackyMemoryObservation).filter(
            StackyMemoryObservation.status == "active",
            StackyMemoryObservation.enforcement == "always",
            StackyMemoryObservation.deleted_at.is_(None),
            or_(
                StackyMemoryObservation.expires_at.is_(None),
                StackyMemoryObservation.expires_at > now,
            ),
        )
        # scope: project-match para project-scoped; global/team viajan por scope.
        if scopes:
            q = q.filter(StackyMemoryObservation.scope.in_(scopes))
        q = q.filter(
            or_(
                StackyMemoryObservation.scope != "project",
                StackyMemoryObservation.project == project,
            )
        )
        rows = q.order_by(
            StackyMemoryObservation.priority.desc(),
            StackyMemoryObservation.updated_at.desc(),
        ).all()

        matched = [
            r for r in rows
            if directive_matches_run(
                r.applies_to(),
                agent_type=agent_type,
                project=project,
                ticket_title=ticket_title,
                ticket_description=ticket_description,
                work_item_type=work_item_type,
            )
        ]
        return [r.to_dict() for r in matched]


def _render_directives(items: list[dict]) -> str:
    """Render imperativo (espejo de _render_memory con framing de orden)."""
    lines: list[str] = ["## REGLAS OBLIGATORIAS DEL OPERADOR (cumplir SIEMPRE)"]
    for it in items:
        header = f"### {it['title']}"
        if it.get("topic_key"):
            header += f"  ({it['topic_key']})"
        lines.append(header)
        lines.append((it.get("content") or "").strip())
        lines.append("")
    return "\n".join(lines).strip()


def directive_health(project: str) -> dict:
    """M3.2 — Riesgos del set de directivas activas de un proyecto.

    - overlapping: pares de directivas cuyos applies_to coinciden en TODAS las
      dimensiones presentes en común (mismo escenario). NO juzga si el contenido
      se contradice (eso es LLM, fuera de scope) — solo señala "revisá estas".
    - budget_pressure: por agent_type, ratio de chars de directivas vs el slice
      reservado (M0.1 caps + STACKY_MEMORY_DIRECTIVE_MAX_CHARS). ratio>0.8 = flag.
    - stale: directivas con review_after o expires_at vencidos.
    """
    import os

    now = datetime.utcnow()
    with session_scope() as session:
        rows = (
            session.query(StackyMemoryObservation)
            .filter(
                StackyMemoryObservation.project == project,
                StackyMemoryObservation.enforcement == "always",
                StackyMemoryObservation.status == "active",
                StackyMemoryObservation.deleted_at.is_(None),
            )
            .all()
        )
        dirs = [
            {
                "memory_id": r.memory_id,
                "applies_to": r.applies_to(),
                "chars": len(r.title or "") + len(r.content or "") + 64,
                "review_after": r.review_after,
                "expires_at": r.expires_at,
            }
            for r in rows
        ]

    # overlapping: comparar pares con targeting que se solapa en las dimensiones
    # presentes en AMBOS (al menos una compartida y con intersección no vacía).
    overlapping: list[dict] = []
    match_dims = ("agent_types", "projects", "work_item_types")
    for i in range(len(dirs)):
        for j in range(i + 1, len(dirs)):
            a, b = dirs[i]["applies_to"], dirs[j]["applies_to"]
            shared = [d for d in match_dims if d in a and d in b]
            if not shared:
                # ambos sin dimensiones de match → ambos aplican a todo → solapan
                if not any(d in a for d in match_dims) and not any(d in b for d in match_dims):
                    overlapping.append({
                        "ids": [dirs[i]["memory_id"], dirs[j]["memory_id"]],
                        "shared_targeting": {},
                    })
                continue
            shared_targeting = {}
            ok = True
            for d in shared:
                sa = {str(x).strip().lower() for x in (a.get(d) or [])}
                sb = {str(x).strip().lower() for x in (b.get(d) or [])}
                inter = sa & sb
                if not inter:
                    ok = False
                    break
                shared_targeting[d] = sorted(inter)
            if ok:
                overlapping.append({
                    "ids": [dirs[i]["memory_id"], dirs[j]["memory_id"]],
                    "shared_targeting": shared_targeting,
                })

    # budget_pressure por agent_type referenciado (o "*" para untargeted).
    try:
        directive_cap_flag = int(os.getenv("STACKY_MEMORY_DIRECTIVE_MAX_CHARS", "4000"))
    except ValueError:
        directive_cap_flag = 4000
    buckets: dict[str, int] = {}
    for d in dirs:
        agents = d["applies_to"].get("agent_types") or ["*"]
        for ag in agents:
            buckets[str(ag).strip().lower()] = buckets.get(str(ag).strip().lower(), 0) + d["chars"]
    budget_pressure: list[dict] = []
    for ag, chars in sorted(buckets.items()):
        _maxmem, agent_max_chars = _caps_for(None if ag == "*" else ag)
        cap = min(max(agent_max_chars // 2, 0), directive_cap_flag) or agent_max_chars
        ratio = round(chars / cap, 3) if cap else 0.0
        budget_pressure.append({
            "project": project,
            "agent_type": ag,
            "directive_chars": chars,
            "cap": cap,
            "ratio": ratio,
        })

    # stale: review_after o expires_at vencidos.
    stale: list[dict] = []
    for d in dirs:
        ra, ex = d["review_after"], d["expires_at"]
        if (ra is not None and ra < now) or (ex is not None and ex < now):
            stale.append({
                "id": d["memory_id"],
                "review_after": ra.isoformat() if ra else None,
                "expires_at": ex.isoformat() if ex else None,
            })

    return {
        "project": project,
        "overlapping": overlapping,
        "budget_pressure": budget_pressure,
        "stale": stale,
    }


def get_context_for_run(
    *,
    project: str | None,
    agent_type: str | None,
    query_text: str | None,
    inject_scopes: Iterable[str] = INJECT_SCOPES,
    max_chars: int | None = None,
    ticket_title: str | None = None,
    ticket_description: str | None = None,
    work_item_type: str | None = None,
) -> dict:
    """Arma el bloque de memoria operativa para una ejecución.

    Estructura (M1.2): primero las DIRECTIVAS obligatorias (bypass scoring, slice
    de presupuesto reservado, render imperativo), luego el pool observacional
    (TF-IDF → supresión de conflicto → caps) con el presupuesto restante.

    Devuelve:
      {
        "content": str,          # texto a inyectar (vacío si no hay nada)
        "hits": int,             # candidatos observacionales activos pre-supresión
        "active_hits": int,      # observaciones inyectadas
        "suppressed_hits": int,  # observaciones ocultadas por conflicto
        "memory_ids": [str, ...] # observaciones inyectadas
        "directive_ids": [str],  # directivas inyectadas (M1.2, aditivo)
        "directive_hits": int,   # cantidad de directivas inyectadas (M1.2)
        "directives_crowded_out_observations": bool  # M1.3, opcional
      }
    """
    empty = {
        "content": "", "hits": 0, "active_hits": 0, "suppressed_hits": 0,
        "memory_ids": [], "directive_ids": [], "directive_hits": 0,
    }
    if not project:
        return empty

    import os

    max_memories, agent_max_chars = _caps_for(agent_type)
    char_cap = min(max_chars, agent_max_chars) if max_chars else agent_max_chars

    # ── M1.2 — Directivas obligatorias (bypass scoring) ───────────────────────
    directives = get_directives_for_run(
        project=project,
        agent_type=agent_type,
        ticket_title=ticket_title,
        ticket_description=ticket_description,
        work_item_type=work_item_type,
        scopes=tuple(inject_scopes),
    )

    try:
        directive_cap_flag = int(os.getenv("STACKY_MEMORY_DIRECTIVE_MAX_CHARS", "4000"))
    except ValueError:
        directive_cap_flag = 4000
    # Slice reservado: la mitad del techo o el flag, lo menor. Si el techo total
    # es menor que el slice, las directivas pueden consumir hasta todo el techo
    # (M1.3: las directivas SIEMPRE ganan al pool).
    directive_cap_chars = min(max(char_cap // 2, 0), directive_cap_flag) or char_cap

    directive_content = ""
    directive_ids: list[str] = []
    directive_used = 0
    if directives:
        rendered: list[dict] = []
        for d in directives:
            title = pii_masker.redact_irreversible(d.get("title") or "")
            body = pii_masker.redact_irreversible(d.get("content") or "")
            rendered.append({**d, "title": title, "content": body})
        directive_ids = [d["memory_id"] for d in directives]
        directive_content = _render_directives(rendered)
        # Las directivas SIEMPRE ganan: si el techo total es menor que el slice,
        # pueden usar hasta todo el techo (M1.3); si no, su slice reservado.
        cap_for_directives = min(directive_cap_chars, char_cap)
        if len(directive_content) > cap_for_directives:
            # NUNCA se dropea una directiva en silencio: se trunca con marcador.
            directive_content = directive_content[:cap_for_directives].rstrip() + "\n… [directivas truncadas por presupuesto]"
            try:
                import logging
                logging.getLogger(__name__).warning(
                    "directivas truncadas por presupuesto (project=%s agent=%s cap=%d)",
                    project, agent_type, cap_for_directives,
                )
            except Exception:  # noqa: BLE001
                pass
        directive_used = len(directive_content)

    # Presupuesto restante para el pool observacional.
    obs_cap = max(char_cap - directive_used, 0)
    crowded_out = directive_used > 0 and obs_cap == 0

    # ── Pool observacional (comportamiento histórico, sobre obs_cap) ──────────
    candidates = search(
        project=project,
        query_text=query_text,
        scopes=tuple(inject_scopes),
        agent_type=agent_type,
        statuses=INJECTABLE_STATUSES,
        k=max(max_memories * 3, 30),
    )
    # B5: no re-emitir por el USER prompt lo que los FA-* ya inyectan por el
    # SYSTEM prompt (un solo canal por conocimiento). Y excluir las directivas
    # ya inyectadas arriba (evita doble-inyección si caen en el pool léxico).
    directive_id_set = set(directive_ids)
    candidates = [
        c for c in candidates
        if (c.get("type") or "") not in _SYSTEM_PROMPT_TYPES
        and c.get("memory_id") not in directive_id_set
    ]

    selected: list[dict] = []
    suppressed: list[dict] = []
    if candidates and obs_cap > 0:
        kept, suppressed = _apply_conflict_suppression(project, candidates)
        kept = kept[:max_memories]
        running = 0
        for it in kept:
            title = pii_masker.redact_irreversible(it.get("title") or "")
            body = pii_masker.redact_irreversible(it.get("content") or "")
            cost = len(title) + len(body) + 64
            if selected and running + cost > obs_cap:
                break
            selected.append({**it, "title": title, "content": body})
            running += cost

    # ── Composición final ─────────────────────────────────────────────────────
    obs_content = _render_memory(selected) if selected else ""
    if obs_content and len(obs_content) > obs_cap:
        obs_content = obs_content[:obs_cap].rstrip() + "\n…"

    parts = [p for p in (directive_content, obs_content) if p]
    content = "\n\n".join(parts)

    if not content:
        return {
            **empty,
            "hits": len(candidates),
            "suppressed_hits": len(suppressed),
        }

    result = {
        "content": content,
        "hits": len(candidates),
        "active_hits": len(selected),
        "suppressed_hits": len(suppressed),
        "memory_ids": [it["memory_id"] for it in selected],
        "directive_ids": directive_ids,
        "directive_hits": len(directive_ids),
    }
    if crowded_out:
        result["directives_crowded_out_observations"] = True
    return result
