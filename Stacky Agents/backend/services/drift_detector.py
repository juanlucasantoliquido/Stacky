"""
FA-16 — Drift detection sobre outputs de agentes.

Compara métricas de calidad (contract_score, confidence) de los últimos 7d
contra los 7d anteriores. Si la degradación supera un umbral, genera una alerta.

Señales monitoreadas por agente:
- avg_contract_score   (de contract_result.score)
- avg_confidence       (de metadata.confidence.overall)
- approval_rate        (verdict=approved / total completed)
- error_rate           (status=error / total)

Alertas:
- Tabla `drift_alerts` (agent_type, metric, prev, curr, delta, detected_at, acknowledged)
- Se limpian automáticamente las alertas > 30 días
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String

from db import Base, session_scope
from models import AgentExecution


class DriftAlert(Base):
    __tablename__ = "drift_alerts"

    id = Column(Integer, primary_key=True)
    agent_type = Column(String(20), nullable=False)
    metric = Column(String(40), nullable=False)
    prev_value = Column(Float)
    curr_value = Column(Float)
    delta = Column(Float)
    severity = Column(String(10), default="warning")  # warning | critical
    detected_at = Column(DateTime, default=datetime.utcnow)
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(String(200))

    __table_args__ = (Index("ix_drift_agent_metric_det", "agent_type", "detected_at"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "metric": self.metric,
            "prev_value": round(self.prev_value or 0, 2),
            "curr_value": round(self.curr_value or 0, 2),
            "delta": round(self.delta or 0, 2),
            "severity": self.severity,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "acknowledged": self.acknowledged,
        }


@dataclass
class _Window:
    avg_contract_score: float | None
    avg_confidence: float | None
    approval_rate: float | None
    error_rate: float | None
    sample_size: int


def _parse_score(row: AgentExecution) -> float | None:
    if not row.contract_result_json:
        return None
    try:
        return float(json.loads(row.contract_result_json).get("score", None) or 0)
    except Exception:
        return None


def _parse_confidence(row: AgentExecution) -> float | None:
    if not row.metadata_json:
        return None
    try:
        return float(json.loads(row.metadata_json).get("confidence", {}).get("overall", None) or 0)
    except Exception:
        return None


def _compute_window(rows: list[AgentExecution]) -> _Window:
    if not rows:
        return _Window(None, None, None, None, 0)
    total = len(rows)
    scores = [s for r in rows if (s := _parse_score(r)) is not None]
    confs = [c for r in rows if (c := _parse_confidence(r)) is not None]
    approved = sum(1 for r in rows if r.verdict == "approved")
    errored = sum(1 for r in rows if r.status == "error")
    return _Window(
        avg_contract_score=sum(scores) / len(scores) if scores else None,
        avg_confidence=sum(confs) / len(confs) if confs else None,
        approval_rate=approved / total,
        error_rate=errored / total,
        sample_size=total,
    )


THRESHOLDS = {
    "avg_contract_score": {"warning": -8.0, "critical": -15.0},
    "avg_confidence":     {"warning": -8.0, "critical": -15.0},
    "approval_rate":      {"warning": -0.10, "critical": -0.20},
    "error_rate":         {"warning": +0.08, "critical": +0.15},
}


def run_detection(*, window_days: int = 7, min_sample: int = 5) -> list[dict]:
    """
    Compara ventana actual vs ventana anterior para cada agente.
    Persiste alertas nuevas. Devuelve lista de alertas generadas.
    """
    now = datetime.utcnow()
    curr_start = now - timedelta(days=window_days)
    prev_start = curr_start - timedelta(days=window_days)

    alerts_generated: list[dict] = []
    agent_types = ["business", "functional", "technical", "developer", "qa"]

    with session_scope() as session:
        # Limpiar alertas viejas
        session.query(DriftAlert).filter(
            DriftAlert.detected_at < now - timedelta(days=30)
        ).delete(synchronize_session=False)

        for agent_type in agent_types:
            curr_rows = (
                session.query(AgentExecution)
                .filter(AgentExecution.agent_type == agent_type)
                .filter(AgentExecution.started_at >= curr_start)
                .all()
            )
            prev_rows = (
                session.query(AgentExecution)
                .filter(AgentExecution.agent_type == agent_type)
                .filter(AgentExecution.started_at >= prev_start)
                .filter(AgentExecution.started_at < curr_start)
                .all()
            )
            if len(curr_rows) < min_sample or len(prev_rows) < min_sample:
                continue

            curr_w = _compute_window(curr_rows)
            prev_w = _compute_window(prev_rows)

            def _check(metric: str, prev_val, curr_val):
                if prev_val is None or curr_val is None:
                    return
                delta = curr_val - prev_val
                thresh = THRESHOLDS.get(metric, {})
                sev = None
                # error_rate sube = malo; otros bajan = malo
                if metric == "error_rate":
                    if delta >= thresh.get("critical", 999):
                        sev = "critical"
                    elif delta >= thresh.get("warning", 999):
                        sev = "warning"
                else:
                    if delta <= thresh.get("critical", -999):
                        sev = "critical"
                    elif delta <= thresh.get("warning", -999):
                        sev = "warning"
                if sev:
                    alert = DriftAlert(
                        agent_type=agent_type,
                        metric=metric,
                        prev_value=prev_val,
                        curr_value=curr_val,
                        delta=delta,
                        severity=sev,
                    )
                    session.add(alert)
                    session.flush()
                    alerts_generated.append(alert.to_dict())

            _check("avg_contract_score", prev_w.avg_contract_score, curr_w.avg_contract_score)
            _check("avg_confidence",     prev_w.avg_confidence,     curr_w.avg_confidence)
            _check("approval_rate",      prev_w.approval_rate,      curr_w.approval_rate)
            _check("error_rate",         prev_w.error_rate,         curr_w.error_rate)

    return alerts_generated


def list_alerts(*, only_unacknowledged: bool = False) -> list[dict]:
    with session_scope() as session:
        q = session.query(DriftAlert).order_by(DriftAlert.detected_at.desc()).limit(100)
        if only_unacknowledged:
            q = q.filter(DriftAlert.acknowledged.is_(False))
        return [a.to_dict() for a in q.all()]


def acknowledge(alert_id: int, user: str) -> bool:
    with session_scope() as session:
        a = session.get(DriftAlert, alert_id)
        if a is None:
            return False
        a.acknowledged = True
        a.acknowledged_at = datetime.utcnow()
        a.acknowledged_by = user
        return True
