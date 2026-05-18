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
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import desc

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
from services.pm.pm_risk_engine import detect_risks
from services.pm.models import (
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

