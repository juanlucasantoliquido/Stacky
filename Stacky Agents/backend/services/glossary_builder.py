"""
FA-15 — Project glossary auto-build.

Escanea outputs aprobados, extrae términos candidatos (bold, code, ALLCAPS)
y los propone al operador para confirmación. Una vez aprobados, el glosario
permanente (tabla `glossary_entries`) enriquece FA-09 (auto-injection).

Pipeline:
1. `scan_approved(...)` → lista de candidatos con frecuencia y fuente
2. Operador revisa: aprueba / rechaza vía /api/glossary/candidates
3. `promote(candidate_id)` → mueve a `glossary_entries` (activo)
4. FA-09 (`services/glossary.py`) incorpora los entries de esta tabla
   en el bloque [auto] a través de `build_glossary_block_enriched()`
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text

from db import Base, session_scope
from models import AgentExecution


# ─────────────────────────────────────────────────────────────
# Modelos
# ─────────────────────────────────────────────────────────────

class GlossaryEntry(Base):
    __tablename__ = "glossary_entries"

    id = Column(Integer, primary_key=True)
    project = Column(String(80))
    term = Column(String(200), nullable=False)
    definition = Column(Text, nullable=False)
    auto_generated = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(200))

    __table_args__ = (Index("ix_glossary_project_term", "project", "term"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "term": self.term,
            "definition": self.definition,
            "auto_generated": self.auto_generated,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }


class GlossaryCandidate(Base):
    __tablename__ = "glossary_candidates"

    id = Column(Integer, primary_key=True)
    project = Column(String(80))
    term = Column(String(200), nullable=False)
    occurrences = Column(Integer, default=1)
    source_exec_ids_json = Column(Text)   # JSON list[int]
    context_sample = Column(Text)          # fragmento donde apareció
    status = Column(String(20), default="pending")  # pending | approved | rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    promoted_entry_id = Column(Integer, ForeignKey("glossary_entries.id"))

    __table_args__ = (Index("ix_candidates_project_status", "project", "status"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "term": self.term,
            "occurrences": self.occurrences,
            "source_exec_ids": json.loads(self.source_exec_ids_json or "[]"),
            "context_sample": self.context_sample,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "promoted_entry_id": self.promoted_entry_id,
        }


# ─────────────────────────────────────────────────────────────
# Extracción de candidatos
# ─────────────────────────────────────────────────────────────

# Patrones a extraer
_BOLD = re.compile(r"\*\*([A-Z][A-Za-z0-9_.\-]{2,40})\*\*")
_CODE_INLINE = re.compile(r"`([A-Z][A-Za-z0-9_.:\-]{2,60})`")
_ALLCAPS = re.compile(r"\b([A-Z]{3,20})\b")
_KNOWN_NOISE = {
    "HTML", "URL", "API", "SQL", "JSON", "XML", "ADO", "N/A", "OK", "EL",
    "LA", "LOS", "LAS", "UNA", "DEL", "POR", "QUE", "CON", "SIN",
    "MAS", "PASS", "FAIL", "TU", "RF", "QA",
}

@dataclass
class _Raw:
    term: str
    exec_id: int
    snippet: str


def _extract_from(text: str, exec_id: int) -> list[_Raw]:
    raws: list[_Raw] = []
    for rx in (_BOLD, _CODE_INLINE, _ALLCAPS):
        for m in rx.finditer(text):
            term = m.group(1).strip()
            if term in _KNOWN_NOISE or len(term) < 3:
                continue
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            snippet = "…" + text[start:end].replace("\n", " ") + "…"
            raws.append(_Raw(term=term, exec_id=exec_id, snippet=snippet))
    return raws


def scan_approved(
    project: str | None = None,
    days: int = 30,
    min_occurrences: int = 2,
) -> int:
    """
    Escanea outputs aprobados recientes, extrae candidatos y los persiste
    en `glossary_candidates` (status=pending). Devuelve cantidad de nuevos.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    with session_scope() as session:
        execs = (
            session.query(AgentExecution)
            .filter(AgentExecution.verdict == "approved")
            .filter(AgentExecution.started_at >= cutoff)
            .filter(AgentExecution.output.isnot(None))
            .all()
        )

        # Excluir los terms ya conocidos (en GlossaryEntry)
        existing_entries = {
            e.term.lower()
            for e in session.query(GlossaryEntry).filter_by(active=True).all()
        }
        existing_candidates = {
            c.term.lower()
            for c in session.query(GlossaryCandidate)
            .filter(GlossaryCandidate.status.in_(["pending", "approved"]))
            .all()
        }
        skip = existing_entries | existing_candidates
        # También saltear el glossary inline de FA-09
        from services.glossary import GLOSSARY
        skip |= {t.lower() for t in GLOSSARY}

        raw_all: list[_Raw] = []
        for e in execs:
            raw_all.extend(_extract_from(e.output or "", e.id))

        # Agrupar por term
        by_term: dict[str, list[_Raw]] = {}
        for r in raw_all:
            if r.term.lower() in skip:
                continue
            by_term.setdefault(r.term, []).append(r)

        new_count = 0
        for term, raws in by_term.items():
            if len(raws) < min_occurrences:
                continue
            exec_ids = list({r.exec_id for r in raws})[:10]
            sample = raws[0].snippet
            session.add(GlossaryCandidate(
                project=project,
                term=term,
                occurrences=len(raws),
                source_exec_ids_json=json.dumps(exec_ids),
                context_sample=sample,
                status="pending",
            ))
            new_count += 1
    return new_count


# ─────────────────────────────────────────────────────────────
# CRUD candidatos
# ─────────────────────────────────────────────────────────────

def list_candidates(project: str | None = None, status: str | None = "pending") -> list[dict]:
    with session_scope() as session:
        q = session.query(GlossaryCandidate)
        if project:
            q = q.filter(GlossaryCandidate.project == project)
        if status:
            q = q.filter(GlossaryCandidate.status == status)
        return [c.to_dict() for c in q.order_by(GlossaryCandidate.occurrences.desc()).all()]


def promote(candidate_id: int, definition: str, created_by: str = "dev@local") -> int:
    """Aprueba un candidato y lo promueve a GlossaryEntry activo."""
    with session_scope() as session:
        cand = session.get(GlossaryCandidate, candidate_id)
        if cand is None:
            raise ValueError(f"candidate {candidate_id} not found")
        entry = GlossaryEntry(
            project=cand.project,
            term=cand.term,
            definition=definition,
            auto_generated=True,
            active=True,
            created_by=created_by,
        )
        session.add(entry)
        session.flush()
        cand.status = "approved"
        cand.promoted_entry_id = entry.id
        return entry.id


def reject(candidate_id: int) -> None:
    with session_scope() as session:
        cand = session.get(GlossaryCandidate, candidate_id)
        if cand:
            cand.status = "rejected"


def list_entries(project: str | None = None, active_only: bool = True) -> list[dict]:
    with session_scope() as session:
        q = session.query(GlossaryEntry)
        if project:
            q = q.filter(GlossaryEntry.project == project)
        if active_only:
            q = q.filter(GlossaryEntry.active.is_(True))
        return [e.to_dict() for e in q.order_by(GlossaryEntry.term).all()]


# ─────────────────────────────────────────────────────────────
# Integración con FA-09: bloque enriquecido con entries de la tabla
# ─────────────────────────────────────────────────────────────

def build_glossary_block_enriched(
    texts: list[str],
    project: str | None = None,
    max_terms: int = 12,
) -> dict | None:
    """Extiende FA-09: agrega terms de la tabla GlossaryEntry al glosario inline."""
    from services.glossary import detect_terms, GLOSSARY

    # Terms inline (FA-09)
    detected = detect_terms(texts)[:max_terms]

    # Terms de la tabla para este proyecto
    with session_scope() as session:
        q = session.query(GlossaryEntry).filter_by(active=True)
        if project:
            from sqlalchemy import or_
            q = q.filter(
                or_(GlossaryEntry.project == project, GlossaryEntry.project.is_(None))
            )
        db_entries = q.all()

    unified: dict[str, str] = {d.term: d.definition for d in detected}
    for e in db_entries:
        if e.term not in unified:
            unified[e.term] = e.definition

    if not unified:
        return None
    body = "\n".join(f"- **{t}**: {d}" for t, d in list(unified.items())[:max_terms])
    return {
        "id": "glossary-auto",
        "kind": "auto",
        "title": f"Glosario detectado ({len(unified)} término{'s' if len(unified) != 1 else ''})",
        "content": body,
        "source": {"type": "glossary", "terms": list(unified.keys())},
    }
