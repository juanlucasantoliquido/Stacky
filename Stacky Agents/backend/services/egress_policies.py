"""
FA-41 — Data egress controls.

Policy declarativa: qué proyecto puede mandar qué clase de dato a qué LLM.
Antes de invocar al LLM, `check()` verifica si el contexto contiene clases
de datos prohibidas para el modelo elegido. Si bloquea, devuelve razón.

Tabla `egress_policies`:
  id, project, data_class, allowed_llms (CSV), action (allow|block|warn)

Clases de datos detectadas (lista pre-definida, extensible):
  - "pii"          → DNI/CUIT/email/teléfono detectados (FA-37)
  - "financial"    → CBU/CARD detectados
  - "production"   → keywords ['producción', 'PROD', 'data real']
  - "regulatory"   → keywords ['SOX', 'BCRA', 'compliance']

Uso desde agent_runner: si check devuelve action=block → exec falla con razón.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from db import Base, session_scope


class EgressPolicy(Base):
    __tablename__ = "egress_policies"

    id = Column(Integer, primary_key=True)
    project = Column(String(80))   # None = global
    data_class = Column(String(40), nullable=False)  # pii | financial | production | regulatory
    allowed_llms = Column(String(400))   # CSV; vacío = ninguno permitido
    action = Column(String(20), default="block")  # block | warn | allow
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(200))

    __table_args__ = (Index("ix_egress_project_class", "project", "data_class"),)

    def allowed(self) -> set[str]:
        if not self.allowed_llms:
            return set()
        return {m.strip() for m in self.allowed_llms.split(",") if m.strip()}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "data_class": self.data_class,
            "allowed_llms": list(self.allowed()),
            "action": self.action,
            "active": self.active,
        }


# ─────────────────────────────────────────────────────────────
# Detección de clases de datos en texto
# ─────────────────────────────────────────────────────────────

_DETECTORS: dict[str, list[re.Pattern[str]]] = {
    "pii": [
        re.compile(r"\b\d{7,8}\b"),                          # DNI
        re.compile(r"\b\d{2}-\d{8}-\d\b"),                   # CUIT
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # email
    ],
    "financial": [
        re.compile(r"\b\d{22}\b"),                           # CBU
        re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b"),          # tarjeta
    ],
    "production": [
        re.compile(r"\b(producci[oó]n|PROD|data\s+real|prod-db)\b", re.IGNORECASE),
    ],
    "regulatory": [
        re.compile(r"\b(SOX|BCRA|GDPR|HIPAA|PCI[-\s]DSS|compliance)\b", re.IGNORECASE),
    ],
}


def detect_classes(text: str) -> set[str]:
    if not text:
        return set()
    found: set[str] = set()
    for cls, patterns in _DETECTORS.items():
        for p in patterns:
            if p.search(text):
                found.add(cls)
                break
    return found


@dataclass
class EgressDecision:
    allowed: bool
    blocked_classes: list[str]
    warning_classes: list[str]
    detected_classes: list[str]
    reason: str

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "blocked_classes": self.blocked_classes,
            "warning_classes": self.warning_classes,
            "detected_classes": self.detected_classes,
            "reason": self.reason,
        }


def check(*, project: str | None, model: str, context_text: str) -> EgressDecision:
    """Verifica si se puede mandar `context_text` al `model` para `project`.
    Devuelve `EgressDecision` con allowed=True/False y motivos."""
    detected = detect_classes(context_text)
    if not detected:
        return EgressDecision(allowed=True, blocked_classes=[],
                              warning_classes=[], detected_classes=[],
                              reason="no sensitive data classes detected")

    blocked: list[str] = []
    warns: list[str] = []
    with session_scope() as session:
        from sqlalchemy import or_
        rows = (
            session.query(EgressPolicy)
            .filter(EgressPolicy.active.is_(True))
            .filter(EgressPolicy.data_class.in_(list(detected)))
            .filter(or_(EgressPolicy.project == project,
                        EgressPolicy.project.is_(None)))
            .all()
        )
        for r in rows:
            allowed_set = r.allowed()
            if model not in allowed_set:
                if r.action == "block":
                    blocked.append(r.data_class)
                elif r.action == "warn":
                    warns.append(r.data_class)

    if blocked:
        return EgressDecision(
            allowed=False,
            blocked_classes=blocked,
            warning_classes=warns,
            detected_classes=list(detected),
            reason=f"egress blocked: data class(es) {blocked} not allowed to model {model} for project {project or 'global'}",
        )
    return EgressDecision(
        allowed=True,
        blocked_classes=[],
        warning_classes=warns,
        detected_classes=list(detected),
        reason=f"egress allowed (warnings: {warns})" if warns else "egress allowed",
    )


# CRUD
def create(*, data_class: str, allowed_llms: list[str], action: str = "block",
           project: str | None = None, created_by: str = "dev@local") -> int:
    with session_scope() as session:
        row = EgressPolicy(
            project=project, data_class=data_class,
            allowed_llms=",".join(allowed_llms), action=action,
            created_by=created_by,
        )
        session.add(row); session.flush()
        return row.id


def list_all(project: str | None = None) -> list[dict]:
    with session_scope() as session:
        q = session.query(EgressPolicy).filter(EgressPolicy.active.is_(True))
        if project:
            q = q.filter(EgressPolicy.project == project)
        return [r.to_dict() for r in q.all()]


def deactivate(pid: int) -> bool:
    with session_scope() as session:
        r = session.get(EgressPolicy, pid)
        if not r:
            return False
        r.active = False
        return True
