"""
FA-13 — Historical decisions database.

Decisiones técnicas y de negocio quedan vivas y consultables. Para cada Run,
si hay una decisión taggeada con palabras clave del contexto, se inyecta como
bloque informativo en el system prompt:

> "decidimos NO usar X en 2025-Q3 porque Y"

Tabla `decisions`:
- summary (qué se decidió)
- reasoning (por qué)
- tags (lista de keywords para matching simple)
- supersedes_id (FK opcional a decisión anterior)
- made_at, made_by, project, active

API en `/api/decisions`. Buscador básico por overlap de tags.
Cuando integremos embeddings (FA-01), reemplazamos el matching de tags
por similitud semántica del texto del contexto.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, or_

from db import Base, session_scope


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True)
    project = Column(String(80))
    summary = Column(String(500), nullable=False)
    reasoning = Column(Text, nullable=False)
    tags = Column(Text)  # CSV de tags lower
    supersedes_id = Column(Integer, ForeignKey("decisions.id"))
    made_by = Column(String(200))
    made_at = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)

    __table_args__ = (Index("ix_decisions_project_active", "project", "active"),)

    def tag_list(self) -> list[str]:
        if not self.tags:
            return []
        return [t.strip().lower() for t in self.tags.split(",") if t.strip()]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "summary": self.summary,
            "reasoning": self.reasoning,
            "tags": self.tag_list(),
            "supersedes_id": self.supersedes_id,
            "made_by": self.made_by,
            "made_at": self.made_at.isoformat() if self.made_at else None,
            "active": self.active,
        }


@dataclass
class _Loaded:
    summary: str
    reasoning: str
    made_at: str | None


def _tokens(text: str) -> set[str]:
    import re

    return {t.lower() for t in re.findall(r"[a-záéíóúñ0-9]{4,}", text or "", flags=re.IGNORECASE)}


def relevant(*, project: str | None, context_text: str, limit: int = 4) -> list[_Loaded]:
    """Busca decisiones cuyo overlap de tags con el contexto sea ≥ 1."""
    if not context_text:
        return []
    needle = _tokens(context_text)
    if not needle:
        return []

    with session_scope() as session:
        q = session.query(Decision).filter(Decision.active.is_(True))
        if project:
            q = q.filter(or_(Decision.project == project, Decision.project.is_(None)))
        else:
            q = q.filter(Decision.project.is_(None))
        rows = q.order_by(Decision.made_at.desc()).limit(200).all()

        scored: list[tuple[int, Decision]] = []
        for r in rows:
            tags = set(r.tag_list())
            if not tags:
                continue
            overlap = len(tags & needle)
            if overlap >= 1:
                scored.append((overlap, r))
        scored.sort(key=lambda kv: kv[0], reverse=True)
        return [
            _Loaded(
                summary=r.summary,
                reasoning=r.reasoning,
                made_at=r.made_at.isoformat() if r.made_at else None,
            )
            for _, r in scored[:limit]
        ]


def build_prefix(items: list[_Loaded]) -> str:
    if not items:
        return ""
    body_lines: list[str] = []
    for i, it in enumerate(items, 1):
        line = f"{i}. **{it.summary}**\n   → {it.reasoning}"
        if it.made_at:
            line += f"\n   _decidido el {it.made_at[:10]}_"
        body_lines.append(line)
    return (
        "## Decisiones previas relevantes\n"
        "Estas decisiones fueron tomadas y siguen vigentes. Respetá sus implicancias "
        "al producir tu output (no las contradigas sin justificación explícita).\n\n"
        + "\n\n".join(body_lines)
        + "\n"
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create(
    *,
    summary: str,
    reasoning: str,
    tags: list[str] | None = None,
    project: str | None = None,
    supersedes_id: int | None = None,
    made_by: str = "dev@local",
) -> int:
    with session_scope() as session:
        if supersedes_id:
            old = session.get(Decision, supersedes_id)
            if old is not None:
                old.active = False
        row = Decision(
            project=project,
            summary=summary,
            reasoning=reasoning,
            tags=",".join((t.strip().lower() for t in (tags or []) if t.strip())),
            supersedes_id=supersedes_id,
            made_by=made_by,
            active=True,
        )
        session.add(row)
        session.flush()
        return row.id


def list_all(active_only: bool = True) -> list[dict]:
    with session_scope() as session:
        q = session.query(Decision)
        if active_only:
            q = q.filter(Decision.active.is_(True))
        rows = q.order_by(Decision.made_at.desc()).all()
        return [r.to_dict() for r in rows]


def deactivate(decision_id: int) -> bool:
    with session_scope() as session:
        row = session.get(Decision, decision_id)
        if row is None:
            return False
        row.active = False
        return True
