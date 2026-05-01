"""
FA-11 — Anti-pattern registry + injection.

Errores que el equipo cometió antes y NO quiere repetir.
Inyectados al system prompt como "evitá X porque Y".

Tabla `anti_patterns`:
- agent_type   (None = aplica a todos)
- project      (None = aplica a todos)
- pattern      (lo que NO hay que hacer)
- reason       (por qué; ej: "ADO-1100 explotó en prod por esto")
- example      (opcional, ejemplo concreto)
- created_at, created_by, active

Operador puede agregar uno desde un output descartado ("guardar este motivo
como anti-patrón").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, or_

from db import Base, session_scope


class AntiPattern(Base):
    __tablename__ = "anti_patterns"

    id = Column(Integer, primary_key=True)
    agent_type = Column(String(20))   # None = todos
    project = Column(String(80))      # None = todos
    pattern = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    example = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(200))
    active = Column(Boolean, default=True)

    __table_args__ = (Index("ix_antipatterns_agent_project_active", "agent_type", "project", "active"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "project": self.project,
            "pattern": self.pattern,
            "reason": self.reason,
            "example": self.example,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "active": self.active,
        }


@dataclass
class _Loaded:
    pattern: str
    reason: str
    example: str | None


def relevant(*, agent_type: str, project: str | None = None, limit: int = 8) -> list[_Loaded]:
    """Devuelve anti-patterns activos relevantes para el agente y proyecto."""
    with session_scope() as session:
        q = session.query(AntiPattern).filter(AntiPattern.active.is_(True))
        # agent_type matches: igual o null
        q = q.filter(or_(AntiPattern.agent_type == agent_type, AntiPattern.agent_type.is_(None)))
        if project:
            q = q.filter(or_(AntiPattern.project == project, AntiPattern.project.is_(None)))
        else:
            q = q.filter(AntiPattern.project.is_(None))
        rows = q.order_by(AntiPattern.created_at.desc()).limit(limit).all()
        return [_Loaded(pattern=r.pattern, reason=r.reason, example=r.example) for r in rows]


def build_prefix(items: list[_Loaded]) -> str:
    if not items:
        return ""
    body_lines: list[str] = []
    for i, it in enumerate(items, 1):
        line = f"{i}. **Evitá**: {it.pattern}\n   **Por qué**: {it.reason}"
        if it.example:
            line += f"\n   **Ejemplo**: {it.example}"
        body_lines.append(line)
    return (
        "## Anti-patrones a evitar (registro de errores pasados)\n"
        "Estas son cosas que el equipo cometió antes y se acordó NO repetir. "
        "Tomá esto como restricciones duras al producir tu output.\n\n"
        + "\n\n".join(body_lines)
        + "\n"
    )


# ---------------------------------------------------------------------------
# CRUD usado por API
# ---------------------------------------------------------------------------

def create(
    *,
    pattern: str,
    reason: str,
    agent_type: str | None = None,
    project: str | None = None,
    example: str | None = None,
    created_by: str = "dev@local",
) -> int:
    with session_scope() as session:
        row = AntiPattern(
            agent_type=agent_type,
            project=project,
            pattern=pattern,
            reason=reason,
            example=example,
            created_by=created_by,
            active=True,
        )
        session.add(row)
        session.flush()
        return row.id


def list_all(active_only: bool = True) -> list[dict]:
    with session_scope() as session:
        q = session.query(AntiPattern)
        if active_only:
            q = q.filter(AntiPattern.active.is_(True))
        rows = q.order_by(AntiPattern.created_at.desc()).all()
        return [r.to_dict() for r in rows]


def deactivate(ap_id: int) -> bool:
    with session_scope() as session:
        row = session.get(AntiPattern, ap_id)
        if row is None:
            return False
        row.active = False
        return True
