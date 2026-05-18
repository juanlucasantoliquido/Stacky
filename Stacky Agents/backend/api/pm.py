"""PM Intelligence Suite — endpoints REST (Fase 1 MVP).

Endpoints:
  POST /api/pm/sync-ado          — sincroniza sprint actual y persiste snapshot
  GET  /api/pm/sprint/current    — devuelve el último snapshot del sprint activo

Gate de proyecto: solo opera si el proyecto activo tiene tracker_type=azure_devops.

Sin IA en esta fase. Solo cálculos determinísticos. Componentes IA (recommendation
engine, sentiment) están definidos como contratos en docs/11_PM_INTELLIGENCE_SUITE.md
pero NO se habilitan hasta pasar los eval fixtures (§5 del plan v2).
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import desc, func

from db import session_scope
from project_manager import get_active_project, get_project_config
from services.ado_client import AdoApiError, AdoClient, AdoConfigError
from services.pm import ado_pm_collector as collector
from services.pm.pm_kpi_engine import compute_sprint_kpis
from services.pm.pm_normalizer import (
    extract_state_transitions,
    normalize_iteration,
    normalize_work_item,
)
from services.pm.pm_comment_indexer import index_comments_bulk
from services.pm.pm_evals import run_evals
from services.pm.pm_recommendation_engine import (
    acknowledge_recommendation,
    generate_recommendations,
)
from services.pm.pm_risk_engine import detect_risks
from services.pm.pm_sentiment import analyze_sentiment_for_comments
from services.pm.models import (
    PmAiRecommendation,
    PmAiUsage,
    PmRiskItem,
    PmSprintSnapshot,
    PmWorkItemComment,
)
from services.stacky_logger import logger as stacky_logger

logger = logging.getLogger("stacky_agents.pm.api")

bp = Blueprint("pm", __name__, url_prefix="/pm")


# ── helpers ────────────────────────────────────────────────────────────────────

def _resolve_project(project_param: str | None) -> tuple[str | None, dict | None, dict | None]:
    """Resuelve proyecto + config + tracker. Si project_param viene vacío, usa el activo."""
    project_name = project_param or get_active_project()
    if not project_name:
        return None, None, None
    cfg = get_project_config(project_name) or {}
    tracker = (cfg.get("issue_tracker") or {}) if cfg else {}
    return project_name, cfg, tracker


def _ado_only_error(project: str | None) -> tuple[dict, int]:
    return {
        "ok": False,
        "error": "TRACKER_NOT_SUPPORTED",
        "message": "PM Intelligence Suite v1 solo está disponible para proyectos Azure DevOps.",
        "detail": {"project": project},
    }, 400


def _new_client(tracker: dict) -> AdoClient:
    kw: dict = {}
    if tracker.get("organization") and tracker.get("project"):
        kw = {"org": tracker["organization"], "project": tracker["project"]}
    return AdoClient(**kw)


# ── endpoints ──────────────────────────────────────────────────────────────────

@bp.post("/sync-ado")
def sync_ado():
    """Sincroniza work items + revisiones del sprint actual desde Azure DevOps.

    Body (opcional): {"project": "...", "iteration_path": "..."}
    Si no se pasa iteration_path, usa @currentIteration de ADO.
    """
    body = request.get_json(silent=True) or {}
    project_param = (body.get("project") or "").strip() or None
    iteration_path_override = (body.get("iteration_path") or "").strip() or None
    team_override = (body.get("team") or "").strip() or None

    project, cfg, tracker = _resolve_project(project_param)
    if not project:
        return jsonify({
            "ok": False,
            "error": "PROJECT_NOT_FOUND",
            "message": "No hay proyecto activo ni se especificó uno en el body.",
        }), 404

    if tracker.get("type", "azure_devops") != "azure_devops":
        err, code = _ado_only_error(project)
        return jsonify(err), code

    start = time.monotonic()
    try:
        client = _new_client(tracker)
    except AdoConfigError as e:
        return jsonify({
            "ok": False,
            "error": "ADO_CONFIG_ERROR",
            "message": str(e),
            "detail": {"project": project, "stage": "client_init"},
        }), 503

    try:
        if iteration_path_override:
            iteration_raw = {
                "id": uuid.uuid5(uuid.NAMESPACE_URL, iteration_path_override).hex,
                "name": iteration_path_override.rsplit("\\", 1)[-1],
                "path": iteration_path_override,
                "attributes": {},
            }
        else:
            iteration_raw = collector.fetch_current_iteration(client, team=team_override)
            if not iteration_raw:
                return jsonify({
                    "ok": False,
                    "error": "NO_CURRENT_ITERATION",
                    "message": "ADO no devolvió iteración activa para el team.",
                    "detail": {"project": project},
                }), 404

        iteration = normalize_iteration(iteration_raw)
        iteration_path = iteration.get("path") or iteration_path_override
        if not iteration_path:
            return jsonify({
                "ok": False,
                "error": "ITERATION_PATH_MISSING",
                "message": "No se pudo determinar iteration_path.",
            }), 400

        raw_items = collector.fetch_work_items_by_iteration(client, iteration_path)
        normalized_items = [normalize_work_item(w) for w in raw_items if w.get("id")]
        ado_ids = [int(w["ado_id"]) for w in normalized_items if w.get("ado_id")]

        revisions_by_id = collector.fetch_revisions_for_many(client, ado_ids)
        transitions_by_id = {
            ado_id: extract_state_transitions(revs)
            for ado_id, revs in revisions_by_id.items()
        }

        kpis = compute_sprint_kpis(
            sprint=iteration,
            work_items=normalized_items,
            transitions_by_ado_id=transitions_by_id,
        )

        detected = detect_risks(
            project=project,
            sprint=iteration,
            work_items=normalized_items,
            kpis=kpis,
            transitions_by_ado_id=transitions_by_id,
        )

        sprint_id_key = str(iteration.get("id") or iteration_path)

        snapshot_payload = {
            "iteration": {
                "id": iteration.get("id"),
                "name": iteration.get("name"),
                "path": iteration_path,
                "start_date": iteration["start_date"].isoformat() if iteration.get("start_date") else None,
                "end_date": iteration["end_date"].isoformat() if iteration.get("end_date") else None,
                "timeframe": iteration.get("timeframe"),
            },
            "kpis": kpis.to_dict(),
            "risks": [r.to_dict() for r in detected],
            "items_count": len(normalized_items),
            "revisions_count": sum(len(r) for r in revisions_by_id.values()),
        }

        with session_scope() as session:
            snap = PmSprintSnapshot(
                project=project,
                sprint_id=sprint_id_key,
                sprint_name=str(iteration.get("name") or iteration_path),
                start_date=iteration["start_date"].date() if iteration.get("start_date") else None,
                end_date=iteration["end_date"].date() if iteration.get("end_date") else None,
                source="ado_live",
            )
            snap.snapshot = snapshot_payload
            session.add(snap)
            session.flush()
            snapshot_id = snap.id

            risks_inserted = 0
            risks_updated = 0
            for r in detected:
                existing = (
                    session.query(PmRiskItem)
                    .filter(PmRiskItem.risk_id == r.risk_id)
                    .one_or_none()
                )
                if existing is None:
                    item = PmRiskItem(
                        project=project,
                        sprint_id=sprint_id_key,
                        risk_id=r.risk_id,
                        category=r.category,
                        severity=r.severity,
                        description=r.description,
                        rule=r.rule,
                        ai_enriched=False,
                    )
                    item.affected_items = r.affected_items
                    session.add(item)
                    risks_inserted += 1
                else:
                    existing.severity = r.severity
                    existing.description = r.description
                    existing.affected_items = r.affected_items
                    risks_updated += 1

        duration_ms = int((time.monotonic() - start) * 1000)
        stacky_logger.info(
            "pm.sync_ado",
            "pm.sprint_sync",
            duration_ms=duration_ms,
            input_data={"project": project, "iteration_path": iteration_path},
            output_data={
                "snapshot_id": snapshot_id,
                "items_count": len(normalized_items),
                "revisions_count": snapshot_payload["revisions_count"],
                "risks_inserted": risks_inserted,
                "risks_updated": risks_updated,
            },
            tags=["pm", "sprint_sync"],
        )

        return jsonify({
            "ok": True,
            "result": {
                "project": project,
                "snapshot_id": snapshot_id,
                "iteration_path": iteration_path,
                "items_synced": len(normalized_items),
                "revisions_synced": snapshot_payload["revisions_count"],
                "risks_detected": len(detected),
                "risks_inserted": risks_inserted,
                "risks_updated": risks_updated,
                "duration_ms": duration_ms,
            },
        })

    except AdoApiError as e:
        stacky_logger.warning("pm.sync_ado", "ado_unreachable", error=str(e), tags=["pm"])
        return jsonify({
            "ok": False,
            "error": "ADO_UNREACHABLE",
            "message": "No se pudo conectar con Azure DevOps.",
            "detail": {"project": project, "stage": "ado_sync", "ado_error": str(e)},
        }), 502
    except Exception as e:
        logger.exception("sync_ado unexpected error")
        stacky_logger.error("pm.sync_ado", "unexpected_error", exc=e, tags=["pm"])
        return jsonify({
            "ok": False,
            "error": "INTERNAL_ERROR",
            "message": "Error inesperado durante sync PM.",
        }), 500


@bp.get("/sprint/current")
def sprint_current():
    """Devuelve el último snapshot persistido del sprint del proyecto activo."""
    project_param = (request.args.get("project") or "").strip() or None
    project, cfg, tracker = _resolve_project(project_param)
    if not project:
        return jsonify({
            "ok": False,
            "error": "PROJECT_NOT_FOUND",
            "message": "No hay proyecto activo ni se especificó uno en query.",
        }), 404

    if tracker.get("type", "azure_devops") != "azure_devops":
        err, code = _ado_only_error(project)
        return jsonify(err), code

    with session_scope() as session:
        latest = (
            session.query(PmSprintSnapshot)
            .filter(PmSprintSnapshot.project == project)
            .order_by(desc(PmSprintSnapshot.captured_at))
            .first()
        )
        if latest is None:
            return jsonify({
                "ok": False,
                "error": "NO_SNAPSHOT",
                "message": "No hay snapshots PM para este proyecto. Ejecutá POST /api/pm/sync-ado primero.",
                "detail": {"project": project},
            }), 404

        return jsonify({
            "ok": True,
            "result": {
                "project": project,
                "snapshot": latest.to_dict(),
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "source": latest.source,
                "human_review_required": False,
                "ai_enriched": False,
            },
        })


@bp.get("/sprint/history")
def sprint_history():
    """Devuelve los últimos N snapshots del proyecto (default 10)."""
    project_param = (request.args.get("project") or "").strip() or None
    try:
        last_n = max(1, min(50, int(request.args.get("last_n", "10"))))
    except (TypeError, ValueError):
        last_n = 10

    project, cfg, tracker = _resolve_project(project_param)
    if not project:
        return jsonify({
            "ok": False,
            "error": "PROJECT_NOT_FOUND",
            "message": "No hay proyecto activo ni se especificó uno en query.",
        }), 404

    if tracker.get("type", "azure_devops") != "azure_devops":
        err, code = _ado_only_error(project)
        return jsonify(err), code

    with session_scope() as session:
        rows = (
            session.query(PmSprintSnapshot)
            .filter(PmSprintSnapshot.project == project)
            .order_by(desc(PmSprintSnapshot.captured_at))
            .limit(last_n)
            .all()
        )
        snapshots = [r.to_dict() for r in rows]

    return jsonify({
        "ok": True,
        "result": {
            "project": project,
            "count": len(snapshots),
            "snapshots": snapshots,
        },
    })


@bp.get("/risks")
def list_risks():
    """Lista riesgos detectados. Filtros opcionales: project, sprint_id, acknowledged, severity."""
    project_param = (request.args.get("project") or "").strip() or None
    sprint_id = (request.args.get("sprint_id") or "").strip() or None
    severity = (request.args.get("severity") or "").strip().upper() or None
    ack_param = (request.args.get("acknowledged") or "").strip().lower()

    project, _cfg, tracker = _resolve_project(project_param)
    if not project:
        return jsonify({
            "ok": False,
            "error": "PROJECT_NOT_FOUND",
            "message": "No hay proyecto activo ni se especificó uno en query.",
        }), 404

    if tracker.get("type", "azure_devops") != "azure_devops":
        err, code = _ado_only_error(project)
        return jsonify(err), code

    with session_scope() as session:
        q = session.query(PmRiskItem).filter(PmRiskItem.project == project)
        if sprint_id:
            q = q.filter(PmRiskItem.sprint_id == sprint_id)
        if severity in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            q = q.filter(PmRiskItem.severity == severity)
        if ack_param in {"true", "1"}:
            q = q.filter(PmRiskItem.acknowledged.is_(True))
        elif ack_param in {"false", "0"}:
            q = q.filter(PmRiskItem.acknowledged.is_(False))
        q = q.order_by(desc(PmRiskItem.detected_at))
        rows = q.limit(500).all()
        risks = [r.to_dict() for r in rows]

    return jsonify({
        "ok": True,
        "result": {
            "project": project,
            "count": len(risks),
            "risks": risks,
            "ai_enriched": False,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
    })


@bp.post("/risks/<risk_id>/acknowledge")
def acknowledge_risk(risk_id: str):
    """Marca un riesgo como reconocido por un operador humano.

    Body opcional: {"acknowledged_by": "email"} — si no viene, usa header X-User-Email.
    """
    body = request.get_json(silent=True) or {}
    actor = (
        body.get("acknowledged_by")
        or request.headers.get("X-User-Email")
        or "anonymous"
    ).strip()

    with session_scope() as session:
        risk = (
            session.query(PmRiskItem)
            .filter(PmRiskItem.risk_id == risk_id)
            .one_or_none()
        )
        if risk is None:
            return jsonify({
                "ok": False,
                "error": "RISK_NOT_FOUND",
                "message": f"No existe riesgo con risk_id={risk_id}",
            }), 404
        if risk.acknowledged:
            return jsonify({
                "ok": True,
                "result": {
                    "risk_id": risk_id,
                    "already_acknowledged": True,
                    "acknowledged_by": risk.acknowledged_by,
                    "acknowledged_at": risk.acknowledged_at.isoformat() if risk.acknowledged_at else None,
                },
            })
        risk.acknowledged = True
        risk.acknowledged_by = actor
        risk.acknowledged_at = datetime.utcnow()
        result = risk.to_dict()

    stacky_logger.info(
        "pm.risks",
        "pm.risk_acknowledged",
        user=actor,
        output_data={"risk_id": risk_id, "rule": result.get("rule")},
        tags=["pm", "risk_ack"],
    )

    return jsonify({"ok": True, "result": result})


# ── comments ──────────────────────────────────────────────────────────────────

@bp.get("/comments")
def list_comments():
    """Lista comentarios indexados de un work item.

    Query: ?ado_id=<int>&limit=<int, default 50>.
    Devuelve `text_plain` ya con HTML strip + PII mask aplicados.
    """
    try:
        ado_id = int(request.args.get("ado_id", "0"))
    except (TypeError, ValueError):
        ado_id = 0
    if ado_id <= 0:
        return jsonify({
            "ok": False,
            "error": "INVALID_ADO_ID",
            "message": "Parametro ado_id es obligatorio y debe ser entero positivo.",
        }), 400
    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except (TypeError, ValueError):
        limit = 50

    with session_scope() as session:
        rows = (
            session.query(PmWorkItemComment)
            .filter(PmWorkItemComment.ado_id == ado_id)
            .order_by(desc(PmWorkItemComment.comment_date), desc(PmWorkItemComment.id))
            .limit(limit)
            .all()
        )
        comments = [r.to_dict() for r in rows]

    return jsonify({
        "ok": True,
        "result": {
            "ado_id": ado_id,
            "count": len(comments),
            "comments": comments,
            "pii_masked": True,
            "ai_analyzed": False,
        },
    })


@bp.post("/comments/index")
def index_comments():
    """Dispara indexación de comentarios para una lista de work items.

    Body: {"project": "...", "ado_ids": [int, ...], "top_per_item": 50}
    """
    body = request.get_json(silent=True) or {}
    project_param = (body.get("project") or "").strip() or None
    ado_ids_raw = body.get("ado_ids") or []
    if not isinstance(ado_ids_raw, list) or not ado_ids_raw:
        return jsonify({
            "ok": False,
            "error": "ADO_IDS_REQUIRED",
            "message": "Body debe incluir ado_ids: [int, ...] no vacío.",
        }), 400
    try:
        ado_ids = [int(x) for x in ado_ids_raw]
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "INVALID_ADO_IDS",
            "message": "Todos los ado_ids deben ser enteros.",
        }), 400
    try:
        top_per_item = max(1, min(200, int(body.get("top_per_item", 50))))
    except (TypeError, ValueError):
        top_per_item = 50

    project, _cfg, tracker = _resolve_project(project_param)
    if not project:
        return jsonify({
            "ok": False,
            "error": "PROJECT_NOT_FOUND",
            "message": "No hay proyecto activo ni se especificó uno en el body.",
        }), 404
    if tracker.get("type", "azure_devops") != "azure_devops":
        err, code = _ado_only_error(project)
        return jsonify(err), code

    start = time.monotonic()
    try:
        client = _new_client(tracker)
    except AdoConfigError as e:
        return jsonify({
            "ok": False,
            "error": "ADO_CONFIG_ERROR",
            "message": str(e),
            "detail": {"project": project, "stage": "client_init"},
        }), 503

    totals = index_comments_bulk(
        client=client,
        project=project,
        ado_ids=ado_ids,
        top_per_item=top_per_item,
    )

    duration_ms = int((time.monotonic() - start) * 1000)
    stacky_logger.info(
        "pm.comments",
        "pm.comments_indexed",
        duration_ms=duration_ms,
        input_data={"project": project, "ado_ids_count": len(ado_ids)},
        output_data=totals,
        tags=["pm", "comments_index"],
    )

    return jsonify({
        "ok": True,
        "result": {
            "project": project,
            "requested_ado_ids": len(ado_ids),
            "inserted": totals["inserted"],
            "skipped_duplicates": totals["skipped_duplicates"],
            "total_fetched": totals["total_fetched"],
            "errors": totals.get("errors", []),
            "duration_ms": duration_ms,
        },
    })


# ── AI usage tracking (Fase 2) ────────────────────────────────────────────────

@bp.get("/ai/usage")
def ai_usage():
    """Agrega consumo de tokens y costo USD de las llamadas LLM PM.

    Query params:
      project: filtra por proyecto (opcional)
      since_hours: ventana hacia atrás (default 24, max 168)
      agent_kind: sentiment | recommendation (opcional)
    """
    project_param = (request.args.get("project") or "").strip() or None
    agent_filter = (request.args.get("agent_kind") or "").strip().lower() or None
    try:
        since_hours = max(1, min(168, int(request.args.get("since_hours", "24"))))
    except (TypeError, ValueError):
        since_hours = 24

    cutoff = datetime.utcnow() - timedelta(hours=since_hours)

    with session_scope() as session:
        q = session.query(PmAiUsage).filter(PmAiUsage.timestamp >= cutoff)
        if project_param:
            q = q.filter(PmAiUsage.project == project_param)
        if agent_filter in {"sentiment", "recommendation"}:
            q = q.filter(PmAiUsage.agent_kind == agent_filter)

        rows = q.all()

        total_calls = len(rows)
        success_calls = sum(1 for r in rows if r.success)
        tokens_in_total = sum(r.tokens_in for r in rows)
        tokens_out_total = sum(r.tokens_out for r in rows)
        cost_usd_total = round(sum(r.cost_usd for r in rows), 6)
        latency_ms_avg = (
            int(sum(r.latency_ms for r in rows) / total_calls) if total_calls else 0
        )

        by_model: dict[str, dict] = {}
        by_agent: dict[str, dict] = {}
        for r in rows:
            for bucket, key in ((by_model, r.model), (by_agent, r.agent_kind)):
                slot = bucket.setdefault(key, {
                    "calls": 0, "tokens_in": 0, "tokens_out": 0,
                    "cost_usd": 0.0, "success": 0,
                })
                slot["calls"] += 1
                slot["tokens_in"] += r.tokens_in
                slot["tokens_out"] += r.tokens_out
                slot["cost_usd"] += r.cost_usd
                if r.success:
                    slot["success"] += 1
        for bucket in (by_model, by_agent):
            for slot in bucket.values():
                slot["cost_usd"] = round(slot["cost_usd"], 6)

        recent = [r.to_dict() for r in sorted(
            rows, key=lambda x: x.timestamp, reverse=True
        )[:20]]

    return jsonify({
        "ok": True,
        "result": {
            "project": project_param,
            "since_hours": since_hours,
            "window_start": cutoff.isoformat() + "Z",
            "totals": {
                "calls": total_calls,
                "success": success_calls,
                "success_rate_pct": round(100.0 * success_calls / total_calls, 2) if total_calls else 0.0,
                "tokens_in": tokens_in_total,
                "tokens_out": tokens_out_total,
                "tokens_total": tokens_in_total + tokens_out_total,
                "cost_usd": cost_usd_total,
                "latency_ms_avg": latency_ms_avg,
            },
            "by_model": by_model,
            "by_agent": by_agent,
            "recent_calls": recent,
            "advisory_only": True,
        },
    })


# ── evals (Fase 2 gate) ───────────────────────────────────────────────────────

_VALID_EVAL_COMPONENTS = {"comment_sentiment", "recommendation_engine"}


@bp.post("/evals/run")
def run_evals_endpoint():
    """Ejecuta los eval fixtures de un componente IA y devuelve el reporte.

    Body: {"component": "comment_sentiment"|"recommendation_engine", "model": optional}
    """
    body = request.get_json(silent=True) or {}
    component = (body.get("component") or "").strip()
    if component not in _VALID_EVAL_COMPONENTS:
        return jsonify({
            "ok": False,
            "error": "INVALID_COMPONENT",
            "message": f"component debe ser uno de: {sorted(_VALID_EVAL_COMPONENTS)}",
        }), 400
    model = (body.get("model") or "claude-haiku-4-5").strip()

    start = time.monotonic()
    try:
        report = run_evals(component=component, model=model)
    except Exception as e:  # noqa: BLE001
        logger.exception("evals/run falló")
        return jsonify({
            "ok": False,
            "error": "EVAL_RUN_FAILED",
            "message": str(e),
        }), 500
    duration_ms = int((time.monotonic() - start) * 1000)

    stacky_logger.info(
        "pm.evals",
        "pm.evals_run",
        duration_ms=duration_ms,
        input_data={"component": component, "model": model},
        output_data={
            "gate_passed": report.gate_passed,
            "passed": report.passed,
            "total": report.total,
            "cost_usd": round(report.cost_usd_total, 6),
        },
        tags=["pm", "evals"],
    )

    return jsonify({
        "ok": True,
        "result": {
            **report.to_dict(),
            "duration_ms": duration_ms,
        },
    })


@bp.get("/evals/components")
def list_eval_components():
    """Devuelve la lista de componentes IA con eval fixtures definidos."""
    from services.pm.pm_evals import load_fixtures
    out = []
    for comp in sorted(_VALID_EVAL_COMPONENTS):
        fixtures = load_fixtures(comp)
        out.append({
            "component": comp,
            "fixtures_count": len(fixtures),
            "fixture_ids": [f.get("fixture_id") for f in fixtures],
        })
    return jsonify({"ok": True, "result": {"components": out}})


# ── sentiment analyzer (Fase 2 advisory) ──────────────────────────────────────

@bp.post("/sentiment/analyze")
def sentiment_analyze():
    """Analiza sentimientos de comentarios indexados.

    Body: {
      "project": optional,
      "sprint_name": optional,
      "comment_ids": [int, ...] REQUERIDO,
      "model": optional (default claude-haiku-4-5),
      "force_unsafe": false,
      "skip_gate_check": false
    }

    Bloqueado por eval gate salvo force_unsafe=true.
    """
    body = request.get_json(silent=True) or {}
    project_param = (body.get("project") or "").strip() or None
    sprint_name = (body.get("sprint_name") or "unknown").strip()
    raw_ids = body.get("comment_ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({
            "ok": False,
            "error": "COMMENT_IDS_REQUIRED",
            "message": "Body debe incluir comment_ids: [int, ...] no vacío.",
        }), 400
    try:
        comment_ids = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "INVALID_COMMENT_IDS",
            "message": "Todos los comment_ids deben ser enteros.",
        }), 400

    model = (body.get("model") or "claude-haiku-4-5").strip()
    force_unsafe = bool(body.get("force_unsafe", False))
    skip_gate = bool(body.get("skip_gate_check", False))

    project, _cfg, tracker = _resolve_project(project_param)
    if not project:
        return jsonify({
            "ok": False,
            "error": "PROJECT_NOT_FOUND",
            "message": "No hay proyecto activo ni se especificó uno en el body.",
        }), 404
    if tracker.get("type", "azure_devops") != "azure_devops":
        err, code = _ado_only_error(project)
        return jsonify(err), code

    start = time.monotonic()
    result = analyze_sentiment_for_comments(
        project=project,
        sprint_name=sprint_name,
        comment_ids=comment_ids,
        model=model,
        force_unsafe=force_unsafe,
        skip_gate_check=skip_gate,
    )
    duration_ms = int((time.monotonic() - start) * 1000)

    if not result.gate_passed and not force_unsafe:
        return jsonify({
            "ok": False,
            "error": "EVAL_GATE_NOT_PASSED",
            "message": "El eval gate del componente comment_sentiment no pasó. "
                       "Ejecutá POST /api/pm/evals/run primero, o forzá con force_unsafe=true.",
            "result": {**result.to_dict(), "duration_ms": duration_ms},
        }), 412  # 412 Precondition Failed

    stacky_logger.info(
        "pm.sentiment",
        "pm.sentiment_analyzed",
        duration_ms=duration_ms,
        input_data={"project": project, "comment_ids_count": len(comment_ids), "model": model},
        output_data=result.to_dict(),
        tags=["pm", "sentiment"],
    )

    return jsonify({
        "ok": True,
        "result": {**result.to_dict(), "duration_ms": duration_ms},
    })


# ── recommendation engine (Fase 2 advisory) ───────────────────────────────────

@bp.post("/recommendations/generate")
def generate_recs_endpoint():
    """Genera recomendaciones IA para el sprint dado (advisory, no publica).

    Body: {
      "project": optional,
      "model": optional (default claude-sonnet-4-6),
      "force_unsafe": false,
      "skip_gate_check": false,
      "history": optional [{name, velocity, completion_rate_pct}, ...]
    }
    """
    body = request.get_json(silent=True) or {}
    project_param = (body.get("project") or "").strip() or None
    model = (body.get("model") or "claude-sonnet-4-6").strip()
    force_unsafe = bool(body.get("force_unsafe", False))
    skip_gate = bool(body.get("skip_gate_check", False))
    history = body.get("history") or []
    if not isinstance(history, list):
        return jsonify({
            "ok": False,
            "error": "INVALID_HISTORY",
            "message": "history debe ser lista de {name, velocity, completion_rate_pct}.",
        }), 400

    project, _cfg, tracker = _resolve_project(project_param)
    if not project:
        return jsonify({
            "ok": False,
            "error": "PROJECT_NOT_FOUND",
            "message": "No hay proyecto activo ni se especificó uno.",
        }), 404
    if tracker.get("type", "azure_devops") != "azure_devops":
        err, code = _ado_only_error(project)
        return jsonify(err), code

    start = time.monotonic()
    result = generate_recommendations(
        project=project,
        history=history,
        model=model,
        force_unsafe=force_unsafe,
        skip_gate_check=skip_gate,
    )
    duration_ms = int((time.monotonic() - start) * 1000)

    if not result.gate_passed and not force_unsafe:
        return jsonify({
            "ok": False,
            "error": "EVAL_GATE_NOT_PASSED",
            "message": "El eval gate del componente recommendation_engine no pasó. "
                       "Ejecutá POST /api/pm/evals/run primero, o forzá con force_unsafe=true.",
            "result": {**result.to_dict(), "duration_ms": duration_ms},
        }), 412

    stacky_logger.info(
        "pm.recommendations",
        "pm.recommendations_generated",
        duration_ms=duration_ms,
        input_data={"project": project, "model": model},
        output_data=result.to_dict(),
        tags=["pm", "recommendations"],
    )

    return jsonify({
        "ok": True,
        "result": {**result.to_dict(), "duration_ms": duration_ms},
    })


@bp.get("/recommendations")
def list_recommendations():
    """Lista recomendaciones IA persistidas. Filtros: project, sprint_id, acknowledged, priority."""
    project_param = (request.args.get("project") or "").strip() or None
    sprint_id = (request.args.get("sprint_id") or "").strip() or None
    priority = (request.args.get("priority") or "").strip().upper() or None
    ack_param = (request.args.get("acknowledged") or "").strip().lower()

    project, _cfg, tracker = _resolve_project(project_param)
    if not project:
        return jsonify({
            "ok": False,
            "error": "PROJECT_NOT_FOUND",
            "message": "No hay proyecto activo ni se especificó uno.",
        }), 404
    if tracker.get("type", "azure_devops") != "azure_devops":
        err, code = _ado_only_error(project)
        return jsonify(err), code

    with session_scope() as session:
        q = session.query(PmAiRecommendation).filter(PmAiRecommendation.project == project)
        if sprint_id:
            q = q.filter(PmAiRecommendation.sprint_id == sprint_id)
        if priority in {"P0", "P1", "P2"}:
            q = q.filter(PmAiRecommendation.priority == priority)
        if ack_param in {"true", "1"}:
            q = q.filter(PmAiRecommendation.acknowledged.is_(True))
        elif ack_param in {"false", "0"}:
            q = q.filter(PmAiRecommendation.acknowledged.is_(False))
        q = q.order_by(
            PmAiRecommendation.priority,
            desc(PmAiRecommendation.generated_at),
        )
        rows = q.limit(200).all()
        recs = [r.to_dict() for r in rows]

    return jsonify({
        "ok": True,
        "result": {
            "project": project,
            "count": len(recs),
            "recommendations": recs,
            "advisory_only": True,
            "publishable": False,
        },
    })


@bp.post("/recommendations/<rec_id>/acknowledge")
def acknowledge_rec(rec_id: str):
    """Marca una recomendación IA como reconocida por un humano."""
    body = request.get_json(silent=True) or {}
    actor = (
        body.get("acknowledged_by")
        or request.headers.get("X-User-Email")
        or "anonymous"
    ).strip()

    updated = acknowledge_recommendation(rec_id, actor=actor)
    if updated is None:
        return jsonify({
            "ok": False,
            "error": "RECOMMENDATION_NOT_FOUND",
            "message": f"No existe recomendación con rec_id={rec_id}",
        }), 404

    stacky_logger.info(
        "pm.recommendations",
        "pm.recommendation_acknowledged",
        user=actor,
        output_data={"rec_id": rec_id, "category": updated.get("category")},
        tags=["pm", "rec_ack"],
    )

    return jsonify({"ok": True, "result": updated})
