"""
FA-51 — Macros declarativas.

Permite que el operador (o el equipo) defina workflows custom como YAML/JSON,
ejecutables por nombre. Esto va más allá de los Packs predefinidos (07_AGENT_PACKS):
los packs son recetas inmutables; las macros son DSL del usuario.

Schema de macro (JSON):
{
  "id": "hotfix-cobranza",
  "name": "Hotfix Cobranza",
  "description": "Para hotfixes urgentes en módulo cobranza",
  "steps": [
    {"agent": "technical", "mode": "bug", "auto_continue": false,
     "model": "claude-opus-4-7", "abort_on_error": true},
    {"agent": "developer", "auto_continue": true, "branch_on_verdict": {
        "approved": "next",
        "discarded": "abandon",
        "any": "next"
    }},
    {"agent": "qa", "mode": "regression", "auto_continue": false}
  ],
  "options": {"stop_on_first_error": true}
}

Tabla `macros`:
  id, slug, name, description, definition_json, project, owner, created_at

API: CRUD + /run (que delega a packs runner adaptado).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from db import Base, session_scope


class Macro(Base):
    __tablename__ = "macros"

    id = Column(Integer, primary_key=True)
    slug = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    definition_json = Column(Text, nullable=False)
    project = Column(String(80))
    owner = Column(String(200))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_macros_slug_project", "slug", "project", unique=True),)

    def definition(self) -> dict:
        try:
            return json.loads(self.definition_json or "{}")
        except Exception:
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "definition": self.definition(),
            "project": self.project,
            "owner": self.owner,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class MacroValidationError:
    field: str
    message: str

    def to_dict(self) -> dict:
        return {"field": self.field, "message": self.message}


def validate(definition: dict) -> list[MacroValidationError]:
    """Valida que la definition tenga shape correcto."""
    errors: list[MacroValidationError] = []
    if not isinstance(definition, dict):
        errors.append(MacroValidationError("$", "definition must be a dict"))
        return errors
    steps = definition.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append(MacroValidationError("steps", "must be a non-empty list"))
        return errors
    valid_agents = {"business", "functional", "technical", "developer", "qa"}
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(MacroValidationError(f"steps[{i}]", "must be a dict"))
            continue
        a = step.get("agent")
        if a not in valid_agents:
            errors.append(MacroValidationError(
                f"steps[{i}].agent", f"must be one of {sorted(valid_agents)}"))
    return errors


def create(*, slug: str, name: str, definition: dict, description: str = "",
           project: str | None = None, owner: str = "dev@local") -> int:
    errs = validate(definition)
    if errs:
        raise ValueError(f"invalid macro: {[e.to_dict() for e in errs]}")
    with session_scope() as session:
        existing = session.query(Macro).filter_by(slug=slug, project=project).first()
        if existing:
            existing.name = name
            existing.description = description
            existing.definition_json = json.dumps(definition)
            existing.owner = owner
            existing.active = True
            session.flush()
            return existing.id
        row = Macro(
            slug=slug, name=name, description=description,
            definition_json=json.dumps(definition),
            project=project, owner=owner, active=True,
        )
        session.add(row); session.flush()
        return row.id


def list_all(project: str | None = None) -> list[dict]:
    with session_scope() as session:
        q = session.query(Macro).filter(Macro.active.is_(True))
        if project:
            from sqlalchemy import or_
            q = q.filter(or_(Macro.project == project, Macro.project.is_(None)))
        return [m.to_dict() for m in q.order_by(Macro.created_at.desc()).all()]


def get(macro_id: int) -> dict | None:
    with session_scope() as session:
        m = session.get(Macro, macro_id)
        return m.to_dict() if m else None


def deactivate(macro_id: int) -> bool:
    with session_scope() as session:
        m = session.get(Macro, macro_id)
        if not m:
            return False
        m.active = False
        return True


def run(macro_id: int, ticket_id: int, user: str,
        initial_context: list[dict] | None = None) -> dict:
    """
    Ejecuta los pasos del macro. Cada paso lanza un Run del agente correspondiente.
    Devuelve la lista de exec_ids con su status.
    """
    import agent_runner

    macro_dict = get(macro_id)
    if not macro_dict:
        raise ValueError(f"macro {macro_id} not found")

    definition = macro_dict["definition"]
    steps = definition.get("steps", [])
    options = definition.get("options", {})
    stop_on_error = options.get("stop_on_first_error", True)

    exec_ids: list[int] = []
    initial_context = initial_context or []

    for i, step in enumerate(steps):
        eid = agent_runner.run_agent(
            agent_type=step["agent"],
            ticket_id=ticket_id,
            context_blocks=initial_context,
            user=user,
            model_override=step.get("model"),
            use_few_shot=step.get("use_few_shot", True),
            use_anti_patterns=step.get("use_anti_patterns", True),
        )
        exec_ids.append(eid)
        # Solo encadena el primer paso de forma sincrónica;
        # el resto se ejecuta cuando el operador haga "Approve & Continue"
        if not step.get("auto_continue"):
            break

    return {
        "macro_id": macro_id,
        "execution_ids": exec_ids,
        "next_step_index": len(exec_ids),
        "total_steps": len(steps),
    }
