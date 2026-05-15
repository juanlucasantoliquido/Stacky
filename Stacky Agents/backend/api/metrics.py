"""
metrics.py — Endpoint interno de métricas del AgentCompletionGateway (P5).

GET /api/metrics/agent-completion

Devuelve métricas acumuladas desde los system_logs de tipo 'metric.completion_gateway'
y 'metric.shadow_discrepancy'. Formato JSON compatible con dashboards internos.

Los counters se computan live desde system_logs para evitar estado en memoria
y garantizar corrección después de reinicios. En producción de alta escala
se debería cachear con TTL de 60s.

Endpoint solo para uso interno (dashboard, operadores). No expuesto públicamente.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, text

from db import session_scope
from models import SystemLog

logger = logging.getLogger("stacky.metrics")

bp = Blueprint("metrics", __name__, url_prefix="/metrics")


def _parse_tags(tags_json: str | None) -> list[str]:
    if not tags_json:
        return []
    try:
        return json.loads(tags_json)
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_context(ctx_json: str | None) -> dict:
    if not ctx_json:
        return {}
    try:
        return json.loads(ctx_json)
    except (json.JSONDecodeError, TypeError):
        return {}


@bp.get("/agent-completion")
def agent_completion_metrics():
    """Devuelve métricas acumuladas del AgentCompletionGateway.

    Query params:
      since_hours: número de horas hacia atrás (default: 168 = 7 días)

    Response JSON:
      {
        "ok": true,
        "generated_at": "ISO8601",
        "window_hours": 168,
        "counters": {
          "stacky_agent_completion_total": {
            "<result>:<agent_type>:<mode>": count,
            ...
          },
          "stacky_agent_completion_duration_seconds": {
            "avg_ms": float,
            "p95_estimate": null
          },
          "stacky_publish_idempotent_replay_total": int,
          "stacky_execution_orphans_detected_total": int,
          "stacky_shadow_discrepancy_total": {
            "<kind>": count,
            ...
          }
        },
        "mode_breakdown": { "on": N, "shadow": N, "off": N },
        "result_breakdown": { "success": N, "would_succeed": N, ... },
        "last_events": [ ... ]
      }
    """
    try:
        since_hours = int(request.args.get("since_hours", 168))
    except (ValueError, TypeError):
        since_hours = 168

    since_dt = datetime.utcnow() - timedelta(hours=since_hours)

    with session_scope() as session:
        # Obtener todos los logs de métricas del gateway
        gateway_metric_logs = (
            session.query(SystemLog)
            .filter(
                SystemLog.action.in_([
                    "metric.completion_gateway",
                    "metric.shadow_discrepancy",
                ]),
                SystemLog.timestamp >= since_dt,
            )
            .order_by(SystemLog.timestamp.desc())
            .limit(5000)  # cap de seguridad
            .all()
        )

        # Leer todos los contextos
        completion_total: dict[str, int] = {}
        duration_ms_values: list[float] = []
        idempotent_replay_total = 0
        shadow_discrepancy: dict[str, int] = {}
        mode_breakdown: dict[str, int] = {}
        result_breakdown: dict[str, int] = {}

        for log_row in gateway_metric_logs:
            ctx = _parse_context(log_row.context_json)
            metric = ctx.get("metric", "")

            if metric == "stacky_agent_completion_total":
                result = ctx.get("result", "unknown")
                agent_type = ctx.get("agent_type", "unknown")
                mode = ctx.get("mode", "unknown")
                key = f"{result}:{agent_type}:{mode}"
                completion_total[key] = completion_total.get(key, 0) + 1

                # Acumular duración
                dur = ctx.get("duration_ms")
                if dur is not None:
                    try:
                        duration_ms_values.append(float(dur))
                    except (ValueError, TypeError):
                        pass

                # Breakdown por modo
                mode_breakdown[mode] = mode_breakdown.get(mode, 0) + 1

                # Breakdown por resultado
                result_breakdown[result] = result_breakdown.get(result, 0) + 1

                # Idempotent replay
                if result == "idempotent_replay":
                    idempotent_replay_total += 1

            elif metric == "stacky_shadow_discrepancy_total":
                kind = ctx.get("kind", "unknown")
                shadow_discrepancy[kind] = shadow_discrepancy.get(kind, 0) + 1

        # Calcular estadísticas de duración
        avg_duration_ms = None
        if duration_ms_values:
            avg_duration_ms = round(sum(duration_ms_values) / len(duration_ms_values), 2)

        # Detectar orphans: executions 'running' más viejas que 120 min
        from models import AgentExecution  # local import
        timeout_cutoff = datetime.utcnow() - timedelta(minutes=120)
        orphans_count = (
            session.query(func.count(AgentExecution.id))
            .filter(
                AgentExecution.status.in_(["running", "queued"]),
                AgentExecution.started_at < timeout_cutoff,
            )
            .scalar()
        ) or 0

        # Últimos 10 eventos de completion para visualización
        last_events_rows = (
            session.query(SystemLog)
            .filter(
                SystemLog.action.in_([
                    "on.completion",
                    "on.idempotent_replay",
                    "shadow.invocation",
                    "on.error.ticket_not_found",
                    "on.error.no_active_execution",
                    "on.error.html_invalid",
                ]),
                SystemLog.timestamp >= since_dt,
            )
            .order_by(SystemLog.timestamp.desc())
            .limit(10)
            .all()
        )
        last_events = [
            {
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "action": row.action,
                "ticket_id": row.ticket_id,
                "execution_id": row.execution_id,
                "agent_type": _parse_context(row.context_json).get("agent_type"),
                "mode": _parse_context(row.context_json).get("mode"),
                "correlation_id": _parse_context(row.context_json).get("correlation_id"),
            }
            for row in last_events_rows
        ]

    total_invocations = sum(completion_total.values())

    return jsonify({
        "ok": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "window_hours": since_hours,
        "total_invocations": total_invocations,
        "counters": {
            "stacky_agent_completion_total": completion_total,
            "stacky_agent_completion_duration_seconds": {
                "avg_ms": avg_duration_ms,
                "p95_estimate": None,  # requeriría almacenamiento de percentil
                "sample_count": len(duration_ms_values),
            },
            "stacky_publish_idempotent_replay_total": idempotent_replay_total,
            "stacky_execution_orphans_detected_total": orphans_count,
            "stacky_shadow_discrepancy_total": shadow_discrepancy,
        },
        "mode_breakdown": mode_breakdown,
        "result_breakdown": result_breakdown,
        "last_events": last_events,
    })
