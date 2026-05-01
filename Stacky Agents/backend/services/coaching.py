"""
FA-43 — Operator coaching.

Analiza el historial reciente de un operador y sugiere tips concretos para
mejorar su tasa de aprobación primera-pasada. Compara su patrón con el patrón
de los outputs aprobados de otros operadores.

Tips actuales (heurísticos):
- Si tasa de re-runs > 30%: "tus outputs requieren re-run con frecuencia"
- Si tasa de discarded > 25%: "muchos descartes — probá agent forking"
- Si nunca usa few-shot: "activá few-shot, sube 15% la aprobación"
- Si nunca incluye block X que los aprobados sí: "agregá bloque X"
- Si su confidence promedio < 70: "outputs con baja confianza, revisá contexto"

Endpoint: GET /api/coaching/tips?user=...
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from db import session_scope
from models import AgentExecution


@dataclass
class CoachingTip:
    severity: str  # "info" | "warning" | "high"
    title: str
    detail: str
    metric: str  # ej "discard_rate=0.32"

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "metric": self.metric,
        }


def _conf_from_metadata(metadata_json: str | None) -> int | None:
    if not metadata_json:
        return None
    try:
        md = json.loads(metadata_json)
        return md.get("confidence", {}).get("overall")
    except Exception:
        return None


def tips_for(user_email: str, *, lookback_days: int = 30, min_sample: int = 5) -> list[CoachingTip]:
    """Devuelve tips ordenados por severidad descendente."""
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    tips: list[CoachingTip] = []

    with session_scope() as session:
        execs = (
            session.query(AgentExecution)
            .filter(AgentExecution.started_by == user_email)
            .filter(AgentExecution.started_at >= cutoff)
            .all()
        )
        if len(execs) < min_sample:
            return [CoachingTip(
                severity="info",
                title=f"Aún sin datos suficientes ({len(execs)} runs en {lookback_days}d)",
                detail=f"Después de {min_sample}+ runs voy a mostrarte tips personalizados.",
                metric=f"sample={len(execs)}",
            )]

        total = len(execs)
        approved = sum(1 for e in execs if e.verdict == "approved")
        discarded = sum(1 for e in execs if e.verdict == "discarded")
        errored = sum(1 for e in execs if e.status == "error")

        # Tasa de re-runs aproximada: misma combinación (ticket, agent_type) > 1
        seen: Counter = Counter()
        for e in execs:
            seen[(e.ticket_id, e.agent_type)] += 1
        rerun_combos = sum(1 for v in seen.values() if v > 1)
        rerun_rate = rerun_combos / max(1, len(seen))

        approval_rate = approved / total
        discard_rate = discarded / total
        error_rate = errored / total

        # Confidence promedio
        confs = [_conf_from_metadata(e.metadata_json) for e in execs]
        confs = [c for c in confs if c is not None]
        avg_conf = sum(confs) / len(confs) if confs else None

        if approval_rate >= 0.85:
            tips.append(CoachingTip(
                severity="info",
                title="Tu tasa de aprobación primera-pasada es excelente",
                detail=f"{approval_rate:.0%} aprobados. Considerá guardar tus outputs como template del equipo.",
                metric=f"approval_rate={approval_rate:.2f}",
            ))
        elif approval_rate < 0.50:
            tips.append(CoachingTip(
                severity="high",
                title="Aprobación baja — revisá tu pipeline",
                detail=f"Solo {approval_rate:.0%} de tus runs son aprobados. Probá: (a) usar Agent Packs guiados, (b) activar few-shot, (c) revisar el bloque de contexto antes de Run.",
                metric=f"approval_rate={approval_rate:.2f}",
            ))

        if discard_rate > 0.25:
            tips.append(CoachingTip(
                severity="warning",
                title="Muchos outputs descartados",
                detail=f"{discard_rate:.0%} de tus runs terminan descartados. Probá Cost preview (FA-33) y forkear el system prompt (FA-50) para ajustar antes de gastar tokens.",
                metric=f"discard_rate={discard_rate:.2f}",
            ))

        if rerun_rate > 0.30:
            tips.append(CoachingTip(
                severity="warning",
                title="Repetís muchos runs sobre los mismos tickets",
                detail=f"{rerun_rate:.0%} de tus combos (ticket, agent) corrieron > 1 vez. Mirá las execs similares aprobadas (FA-45) antes de re-correr.",
                metric=f"rerun_rate={rerun_rate:.2f}",
            ))

        if error_rate > 0.10:
            tips.append(CoachingTip(
                severity="high",
                title="Tasa de errores alta",
                detail=f"{error_rate:.0%} de tus runs fallaron. Revisá los logs detallados; puede ser contexto malformado o exceso de tokens.",
                metric=f"error_rate={error_rate:.2f}",
            ))

        if avg_conf is not None and avg_conf < 70:
            tips.append(CoachingTip(
                severity="warning",
                title="Confidence promedio baja",
                detail=f"Promedio {avg_conf:.0f}/100. Outputs con muchas hedge phrases. Considerá agregar más contexto técnico (Git context, BD live, decisiones).",
                metric=f"avg_confidence={avg_conf:.0f}",
            ))

        if not tips:
            tips.append(CoachingTip(
                severity="info",
                title="Sin issues detectados — buen patrón",
                detail=f"Tasa de aprobación {approval_rate:.0%}. Seguí así.",
                metric=f"approval_rate={approval_rate:.2f}",
            ))

    severity_order = {"high": 0, "warning": 1, "info": 2}
    tips.sort(key=lambda t: severity_order.get(t.severity, 3))
    return tips
