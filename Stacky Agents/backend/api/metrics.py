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
from models import AgentExecution, SystemLog, Ticket

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


def _execution_costs(execution: AgentExecution) -> tuple[float, float, bool]:
    md = _parse_context(execution.metadata_json)
    reported = 0.0
    estimated = 0.0
    has_estimated = False

    telemetry = md.get("claude_telemetry") if isinstance(md.get("claude_telemetry"), dict) else {}
    value = telemetry.get("total_cost_usd") if isinstance(telemetry, dict) else None
    if value is not None:
        try:
            reported = float(value)
        except (TypeError, ValueError):
            reported = 0.0

    est_val = md.get("cost_estimated")
    if est_val is not None:
        try:
            estimated = float(est_val)
            has_estimated = estimated > 0
        except (TypeError, ValueError):
            estimated = 0.0

    return reported, estimated, has_estimated


@bp.get("/ticket-costs")
def ticket_costs():
    raw_ids = (request.args.get("ticket_ids") or "").strip()
    if not raw_ids:
        return jsonify({"ok": False, "error": "ticket_ids_required"}), 400

    try:
        ticket_ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_ticket_ids"}), 400
    if not ticket_ids:
        return jsonify({"ok": False, "error": "ticket_ids_required"}), 400

    with session_scope() as session:
        rows = (
            session.query(AgentExecution, Ticket)
            .join(Ticket, Ticket.id == AgentExecution.ticket_id)
            .filter(AgentExecution.ticket_id.in_(ticket_ids))
            .all()
        )

    by_ticket: dict[int, dict] = {}
    for exec_row, ticket in rows:
        reported, estimated, has_estimated = _execution_costs(exec_row)
        total = reported + estimated
        if total <= 0:
            continue
        rec = by_ticket.setdefault(
            exec_row.ticket_id,
            {
                "ticket_id": exec_row.ticket_id,
                "ado_id": ticket.ado_id,
                "project": ticket.stacky_project_name or ticket.project,
                "reported_usd": 0.0,
                "estimated_usd": 0.0,
                "total_usd": 0.0,
                "estimated": False,
            },
        )
        rec["reported_usd"] += reported
        rec["estimated_usd"] += estimated
        rec["total_usd"] += total
        rec["estimated"] = bool(rec["estimated"] or has_estimated)

    items = sorted(by_ticket.values(), key=lambda x: x["ticket_id"])
    for item in items:
        item["reported_usd"] = round(float(item["reported_usd"]), 6)
        item["estimated_usd"] = round(float(item["estimated_usd"]), 6)
        item["total_usd"] = round(float(item["total_usd"]), 6)

    return jsonify({"ok": True, "items": items})


@bp.get("/project-costs")
def project_costs():
    months = request.args.get("months", default=3, type=int)
    months = max(1, min(months, 24))
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    # Ventana desde el primer día del mes (months-1) hacia atrás.
    window_start = month_start - timedelta(days=31 * (months - 1))

    with session_scope() as session:
        rows = (
            session.query(AgentExecution, Ticket)
            .join(Ticket, Ticket.id == AgentExecution.ticket_id)
            .filter(AgentExecution.started_at >= window_start)
            .all()
        )

    agg: dict[tuple[str, str], dict] = {}
    for exec_row, ticket in rows:
        reported, estimated, has_estimated = _execution_costs(exec_row)
        total = reported + estimated
        if total <= 0:
            continue
        month_key = exec_row.started_at.strftime("%Y-%m") if exec_row.started_at else now.strftime("%Y-%m")
        project = ticket.stacky_project_name or ticket.project or "UNKNOWN"
        key = (month_key, project)
        rec = agg.setdefault(
            key,
            {
                "month": month_key,
                "project": project,
                "reported_usd": 0.0,
                "estimated_usd": 0.0,
                "total_usd": 0.0,
                "estimated": False,
            },
        )
        rec["reported_usd"] += reported
        rec["estimated_usd"] += estimated
        rec["total_usd"] += total
        rec["estimated"] = bool(rec["estimated"] or has_estimated)

    series = sorted(agg.values(), key=lambda x: (x["month"], x["project"]))
    for row in series:
        row["reported_usd"] = round(float(row["reported_usd"]), 6)
        row["estimated_usd"] = round(float(row["estimated_usd"]), 6)
        row["total_usd"] = round(float(row["total_usd"]), 6)

    return jsonify({"ok": True, "months": months, "series": series})


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
                AgentExecution.status.in_(["preparing", "running", "queued"]),
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


# ── F3.3: Score de salud del arnés ───────────────────────────────────────────

@bp.get("/harness-health")
def harness_health():
    """Salud del arnés CLI (F3.3 / H8). Agrega datos ya persistidos por Fases 1-2.

    GET /api/metrics/harness-health?days=14

    Sin acciones nuevas para el operador: una vista de
    completed-sin-intervención, tasa de autocorrección (F1.3), costo real por
    ticket (F1.2), contract score por agente (F1.1) y distribución de modelos (F3.2).

    H8 — KPIs de valor agregado (top-level + by_runtime):
      - autocorrection_saves: runs donde autocorrect fue invocado Y completó.
      - memory_hit_rate: fracción de runs con memoria colaborativa inyectada.
      - runaway_stops: runs terminados por el runaway guard (needs_review).
    """
    from services import harness_health as hh

    try:
        days = int(request.args.get("days", 14))
    except (ValueError, TypeError):
        days = 14
    days = max(1, min(days, 365))

    health = hh.compute_health(window_days=days)
    return jsonify({
        "ok": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        **health.to_dict(),
    })


# ── Feature C: Comparador de Agentes ─────────────────────────────────────────

@bp.get("/agent-comparison")
def agent_comparison():
    """Compara el rendimiento de agentes por filename en un periodo dado.

    GET /api/metrics/agent-comparison?days=30&agent_type=developer

    Agrega por agent_filename (desde metadata_json) y calcula:
      - total_runs, approved_count, discarded_count, error_count
      - approval_rate, avg_duration_ms, p95_duration_ms
      - tickets_completed

    agent_filename puede ser "unknown" para ejecuciones sin metadata.
    Se muestra badge de advertencia si total_runs < 10 (baja significancia estadistica).
    """
    from models import AgentExecution
    from sqlalchemy import func

    try:
        days = int(request.args.get("days", 30))
    except (ValueError, TypeError):
        days = 30
    agent_type_filter = request.args.get("agent_type") or None

    since_dt = datetime.utcnow() - timedelta(days=days)

    with session_scope() as session:
        q = session.query(AgentExecution).filter(
            AgentExecution.started_at >= since_dt,
            AgentExecution.status.in_(["completed", "error", "cancelled", "discarded"]),
        )
        if agent_type_filter:
            q = q.filter(AgentExecution.agent_type == agent_type_filter)

        executions = q.all()

    # Agrupar por agent_filename desde metadata_json
    grouped: dict[str, dict] = {}
    for ex in executions:
        md = _parse_context(ex.metadata_json)
        filename = md.get("agent_filename") or md.get("vscode_agent_filename") or "unknown"
        agent_type = ex.agent_type or "unknown"

        key = filename
        if key not in grouped:
            grouped[key] = {
                "filename": filename,
                "agent_type": agent_type,
                "total_runs": 0,
                "approved_count": 0,
                "discarded_count": 0,
                "error_count": 0,
                "cancelled_count": 0,
                "tickets_completed": set(),
                "duration_ms_values": [],
            }

        grouped[key]["total_runs"] += 1

        verdict = (ex.verdict or "").lower()
        status = (ex.status or "").lower()

        if verdict == "approved":
            grouped[key]["approved_count"] += 1
        elif verdict == "discarded" or status == "discarded":
            grouped[key]["discarded_count"] += 1
        elif status == "error":
            grouped[key]["error_count"] += 1
        elif status == "cancelled":
            grouped[key]["cancelled_count"] += 1

        # Contar tickets completados (ejecuciones que derivaron en status completado)
        if status == "completed":
            grouped[key]["tickets_completed"].add(ex.ticket_id)

        dur = ex.duration_ms()
        if dur is not None:
            grouped[key]["duration_ms_values"].append(dur)

    # Calcular metricas finales
    agents_result = []
    for key, g in grouped.items():
        total = g["total_runs"]
        durations = sorted(g["duration_ms_values"])
        avg_dur = round(sum(durations) / len(durations), 0) if durations else None

        # Estimacion p95 (percentil 95)
        if len(durations) >= 5:
            idx = int(len(durations) * 0.95)
            p95_dur = durations[min(idx, len(durations) - 1)]
        else:
            p95_dur = max(durations) if durations else None

        approval_rate = round(g["approved_count"] / total, 4) if total > 0 else 0.0

        agents_result.append({
            "filename": g["filename"],
            "agent_type": g["agent_type"],
            "total_runs": total,
            "approved_count": g["approved_count"],
            "discarded_count": g["discarded_count"],
            "error_count": g["error_count"],
            "cancelled_count": g["cancelled_count"],
            "approval_rate": approval_rate,
            "avg_duration_ms": avg_dur,
            "p95_duration_ms": p95_dur,
            "tickets_completed": len(g["tickets_completed"]),
            # Advertencia de baja significancia estadistica
            "low_sample_warning": total < 10,
        })

    # Ordenar por approval_rate descendente
    agents_result.sort(key=lambda a: a["approval_rate"], reverse=True)

    # Marcar el mejor
    if agents_result:
        agents_result[0]["is_best"] = True
        for a in agents_result[1:]:
            a["is_best"] = False

    return jsonify({
        "ok": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "period_days": days,
        "agent_type": agent_type_filter,
        "agents": agents_result,
        "total_executions": sum(a["total_runs"] for a in agents_result),
    })


# ── I3.3 — Asesor de caps de contexto ────────────────────────────────────────

@bp.get("/caps-advisor")
def caps_advisor():
    """Sugiere caps de memoria por agente basándose en telemetría (I3.3).

    GET /api/metrics/caps-advisor?project=X&days=30

    SOLO lectura. NUNCA escribe. El operador aplica las sugerencias
    editando STACKY_MEMORY_CAPS_JSON.

    Response:
      {"enabled": false}  — si el flag está OFF
      {"ok": true, "project": "X", "suggestions": {agent_type: {...}}}  — si ON
    """
    from config import config as _cfg

    if not getattr(_cfg, "STACKY_CAPS_ADVISOR_ENABLED", False):
        return jsonify({"enabled": False}), 200

    project = (request.args.get("project") or "").strip()
    if not project:
        return jsonify({"ok": False, "error": "project_required"}), 400

    try:
        days = int(request.args.get("days", 30))
    except (ValueError, TypeError):
        days = 30
    days = max(1, min(days, 365))

    try:
        from services.context_caps_advisor import suggest_caps
        suggestions = suggest_caps(project=project, days=days)
    except Exception as _e:
        logger.warning("caps_advisor: error en suggest_caps: %s", _e)
        return jsonify({"ok": False, "error": "internal_error"}), 500

    return jsonify({
        "ok": True,
        "enabled": True,
        "project": project,
        "days": days,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "suggestions": suggestions,
    })
