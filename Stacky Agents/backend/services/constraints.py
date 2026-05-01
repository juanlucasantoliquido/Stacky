"""
FA-08 — Customer/project constraints injection.

Reglas declarativas que se inyectan al system prompt cuando el contexto
las activa. Más específicas que los anti-patrones (FA-11): definen
OBLIGACIONES del cliente, no solo errores a evitar.

Ejemplos:
- "Si el módulo es Cobranzas: toda modificación requiere entrada de auditoría"
- "Si es tipo Batch: no usar queries sin índice"
- "Regulatorio: no almacenar datos de tarjeta en logs"

Tabla `project_constraints`:
  project, trigger_keywords (CSV), constraint_text, agent_types (CSV), priority

Injection: si algún keyword del trigger está en context_text → inject.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from db import Base, session_scope


class ProjectConstraint(Base):
    __tablename__ = "project_constraints"

    id = Column(Integer, primary_key=True)
    project = Column(String(80))
    trigger_keywords = Column(Text, nullable=False)  # CSV lower
    constraint_text = Column(Text, nullable=False)
    agent_types = Column(String(200))  # CSV o "*"
    priority = Column(Integer, default=5)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(200))

    __table_args__ = (Index("ix_constraints_project_active", "project", "active"),)

    def keywords(self) -> list[str]:
        return [k.strip().lower() for k in (self.trigger_keywords or "").split(",") if k.strip()]

    def agent_list(self) -> list[str]:
        if not self.agent_types or self.agent_types == "*":
            return []  # empty = all
        return [a.strip() for a in self.agent_types.split(",") if a.strip()]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "trigger_keywords": self.keywords(),
            "constraint_text": self.constraint_text,
            "agent_types": self.agent_list(),
            "priority": self.priority,
            "active": self.active,
        }


@dataclass
class _Loaded:
    constraint_text: str
    priority: int


_TOKEN_RE = re.compile(r"[a-záéíóúñ0-9]{3,}", re.IGNORECASE)


def relevant(
    *,
    agent_type: str,
    project: str | None,
    context_text: str,
    limit: int = 6,
) -> list[_Loaded]:
    context_tokens = {t.lower() for t in _TOKEN_RE.findall(context_text or "")}
    with session_scope() as session:
        q = session.query(ProjectConstraint).filter(ProjectConstraint.active.is_(True))
        if project:
            from sqlalchemy import or_
            q = q.filter(
                or_(ProjectConstraint.project == project, ProjectConstraint.project.is_(None))
            )
        rows = q.order_by(ProjectConstraint.priority.asc()).all()

        matched: list[_Loaded] = []
        for r in rows:
            agents = r.agent_list()
            if agents and agent_type not in agents:
                continue
            kws = set(r.keywords())
            if not kws:
                continue
            if kws & context_tokens:
                matched.append(_Loaded(constraint_text=r.constraint_text, priority=r.priority))
        matched.sort(key=lambda x: x.priority)
        return matched[:limit]


def build_prefix(items: list[_Loaded]) -> str:
    if not items:
        return ""
    body = "\n".join(f"- {it.constraint_text}" for it in items)
    return (
        "## Restricciones obligatorias del proyecto / cliente\n"
        "Las siguientes restricciones aplican al contexto de este Run. "
        "Son OBLIGACIONES — si no podés cumplirlas, declaralo explícitamente.\n\n"
        f"{body}\n"
    )


# CRUD
def create(*, project: str | None, trigger_keywords: list[str], constraint_text: str,
           agent_types: list[str] | None = None, priority: int = 5,
           created_by: str = "dev@local") -> int:
    with session_scope() as session:
        row = ProjectConstraint(
            project=project,
            trigger_keywords=",".join(k.lower() for k in trigger_keywords),
            constraint_text=constraint_text,
            agent_types=",".join(agent_types) if agent_types else "*",
            priority=priority,
            created_by=created_by,
        )
        session.add(row)
        session.flush()
        return row.id


def list_all(project: str | None = None, active_only: bool = True) -> list[dict]:
    with session_scope() as session:
        q = session.query(ProjectConstraint)
        if project:
            q = q.filter(ProjectConstraint.project == project)
        if active_only:
            q = q.filter(ProjectConstraint.active.is_(True))
        return [r.to_dict() for r in q.order_by(ProjectConstraint.priority).all()]


def deactivate(cid: int) -> bool:
    with session_scope() as session:
        r = session.get(ProjectConstraint, cid)
        if not r:
            return False
        r.active = False
        return True
