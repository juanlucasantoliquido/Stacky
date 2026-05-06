"""
Pipeline Status Inference — para cada ticket, determina qué etapas del
ciclo de vida ya fueron ejecutadas, combinando dos fuentes:

  1. Ejecuciones locales de Stacky (AgentExecution en BD).
  2. Comentarios del work item en ADO (inferencia por patrones de texto).

Etapas del pipeline:
  business   → brief de negocio convertido en RF-XXX
  functional → análisis funcional + plan de pruebas
  technical  → análisis técnico de 5 secciones
  developer  → implementación de código
  qa         → QA / UAT con veredicto

Para cada etapa se devuelve:
  done       : bool
  source     : "stacky_exec" | "ado_comment" | None
  confidence : 0.0 – 1.0  (1.0 = ejecución Stacky completada y aprobada)
  evidence   : str | None  (label descriptivo para el UI)
  last_at    : ISO date | None
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import desc

from db import session_scope
from models import AgentExecution

# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

PIPELINE_STAGES = ["business", "functional", "technical", "developer", "qa"]

# Patrones sobre texto HTML de comentarios ADO (case-insensitive)
_COMMENT_PATTERNS: dict[str, list[str]] = {
    "business": [
        r"RF-\d{3}",
        r"requerimiento funcional",
        r"epic.*bloques",
    ],
    "functional": [
        r"an[aá]lisis funcional",
        r"analisis-funcional\.md",
        r"plan-de-pruebas\.md",
        r"CUBRE sin modificaci[oó]n",
        r"GAP",
        r"🔍.*funcional",
    ],
    "technical": [
        r"🔬\s*AN[AÁ]LISIS T[EÉ]CNICO",
        r"ANÁLISIS TÉCNICO\s*—\s*ADO-",
        r"an[aá]lisis t[eé]cnico",
        r"alcance de cambios",
        r"plan de pruebas t[eé]cnico",
    ],
    "developer": [
        r"🚀\s*IMPLEMENTACI[ÓO]N COMPLETADA",
        r"IMPLEMENTACI[ÓO]N COMPLETADA",
        r"archivos modificados",
        r"commits realizados",
    ],
    "qa": [
        r"TESTER_COMPLETADO",
        r"veredicto.*PASS",
        r"veredicto.*FAIL",
        r"escenarios ejecutados",
        r"QA.*completado",
        r"UAT.*completado",
    ],
}

# Confianza base cuando se detecta por comentario ADO (sin saber si fue aprobado)
_COMMENT_BASE_CONFIDENCE = 0.65


@dataclass
class StageStatus:
    stage: str
    done: bool = False
    source: str | None = None        # "stacky_exec" | "ado_comment" | None
    confidence: float = 0.0
    evidence: str | None = None
    last_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "done": self.done,
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
            "last_at": self.last_at,
        }


@dataclass
class PipelineStatus:
    ticket_id: int
    stages: dict[str, StageStatus] = field(default_factory=dict)
    next_suggested: str | None = None
    overall_progress: float = 0.0   # fracción [0,1] de etapas completadas

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "overall_progress": round(self.overall_progress, 2),
            "next_suggested": self.next_suggested,
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
        }


# ---------------------------------------------------------------------------
# Lógica de inferencia
# ---------------------------------------------------------------------------

def _stages_from_executions(ticket_id: int) -> dict[str, StageStatus]:
    """Consulta AgentExecution local y construye StageStatus por tipo."""
    result: dict[str, StageStatus] = {}
    with session_scope() as session:
        rows = (
            session.query(AgentExecution)
            .filter(AgentExecution.ticket_id == ticket_id)
            .filter(AgentExecution.status == "completed")
            .order_by(desc(AgentExecution.started_at))
            .all()
        )
        # Tomar la ejecución completada más reciente por tipo de agente
        seen: set[str] = set()
        for row in rows:
            t = row.agent_type
            if t in seen:
                continue
            seen.add(t)

            verdict = (row.verdict or "").lower()
            if verdict == "approved":
                confidence = 1.0
            elif verdict in ("", "pending", None):
                confidence = 0.85   # completado pero sin veredicto explícito
            else:
                confidence = 0.50   # rejected / con observaciones

            last_at = row.completed_at or row.started_at
            result[t] = StageStatus(
                stage=t,
                done=True,
                source="stacky_exec",
                confidence=confidence,
                evidence=f"Stacky exec #{row.id} — {verdict or 'sin veredicto'}",
                last_at=last_at.isoformat() if last_at else None,
            )
    return result


def _stages_from_comments(comments: list[dict]) -> dict[str, StageStatus]:
    """Escanea los comentarios ADO y detecta etapas por patrones de texto."""
    result: dict[str, StageStatus] = {}
    for stage, patterns in _COMMENT_PATTERNS.items():
        for comment in comments:
            text = comment.get("text", "")
            hit_count = sum(
                1 for p in patterns if re.search(p, text, re.IGNORECASE)
            )
            if hit_count > 0:
                # Más hits = más confianza, cap a 0.90
                confidence = min(_COMMENT_BASE_CONFIDENCE + hit_count * 0.05, 0.90)
                date = comment.get("date", "")
                author = comment.get("author", "?")
                result[stage] = StageStatus(
                    stage=stage,
                    done=True,
                    source="ado_comment",
                    confidence=confidence,
                    evidence=f"Comentario ADO — {author} ({date})",
                    last_at=date or None,
                )
                break  # con el primer comentario que matchea alcanza
    return result


def _suggest_next(stages: dict[str, StageStatus]) -> str | None:
    """Devuelve la primera etapa del pipeline que aún no está completada."""
    for stage in PIPELINE_STAGES:
        s = stages.get(stage)
        if s is None or not s.done:
            return stage
    return None  # todo completo


# ---------------------------------------------------------------------------
# Punto de entrada público
# ---------------------------------------------------------------------------

def get_pipeline_status(
    ticket_id: int,
    ado_comments: list[dict] | None = None,
) -> PipelineStatus:
    """
    Calcula el PipelineStatus de un ticket.

    Si se proveen `ado_comments` (obtenidos previamente con AdoClient.fetch_comments),
    también se infiere desde los comentarios de ADO. Stacky exec tiene prioridad
    sobre la inferencia por comentario.

    Args:
        ticket_id:    ID interno de Stacky (PK en tabla tickets).
        ado_comments: Lista de dicts {author, date, text} del work item.
                      Si es None, solo se usa la BD local (más rápido).
    """
    # Inicializar todas las etapas como no completadas
    stages: dict[str, StageStatus] = {
        s: StageStatus(stage=s) for s in PIPELINE_STAGES
    }

    # Fuente 1: inferencia desde comentarios ADO (menor prioridad)
    if ado_comments:
        comment_stages = _stages_from_comments(ado_comments)
        for stage, status in comment_stages.items():
            stages[stage] = status

    # Fuente 2: ejecuciones Stacky (mayor prioridad, sobreescribe comentario)
    exec_stages = _stages_from_executions(ticket_id)
    for stage, status in exec_stages.items():
        stages[stage] = status

    done_count = sum(1 for s in stages.values() if s.done)
    overall_progress = done_count / len(PIPELINE_STAGES)
    next_suggested = _suggest_next(stages)

    return PipelineStatus(
        ticket_id=ticket_id,
        stages=stages,
        next_suggested=next_suggested,
        overall_progress=overall_progress,
    )


def get_pipeline_summary(ticket_id: int) -> dict:
    """
    Versión ligera (solo BD local, sin llamada a ADO) para incluir
    en el listado de tickets sin generar N+1 requests a ADO.

    Devuelve dict compacto:
      {
        "done_stages": ["functional", "technical"],
        "next_suggested": "developer",
        "overall_progress": 0.4,
      }
    """
    status = get_pipeline_status(ticket_id, ado_comments=None)
    done = [s for s, v in status.stages.items() if v.done]
    return {
        "done_stages": done,
        "next_suggested": status.next_suggested,
        "overall_progress": status.overall_progress,
    }
