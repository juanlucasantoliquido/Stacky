"""Diagnóstico forense de ejecuciones — Fase 4 del plan de remediación.

GET /api/diag/execution/<id>
  Retorna un snapshot estructurado del estado completo de una ejecución
  combinando: row de DB, ticket asociado, MANIFEST.json y heartbeat.json en
  disco, historia de transiciones de stacky_status y una diagnosis
  recomendada.

Útil para responder rápido "¿por qué este run sigue en running?" sin tener
que poll'ear varios endpoints.
"""
from __future__ import annotations

import json
import logging
import io
import os
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from sqlalchemy import select
from sqlalchemy.orm import joinedload

import config as _config
from db import session_scope
from models import AgentExecution, Ticket
from services.heartbeat_monitor import (
    HEARTBEAT_TIMEOUT_MINUTES,
    STARTUP_GRACE_SECONDS,
    is_execution_heartbeat_stale,
)
from services.manifest_watcher import MANIFEST_FILENAME, default_runs_dir
from services.ticket_status import EXECUTION_TIMEOUT_MINUTES, PRE_RUN_TIMEOUT_SECONDS, TicketStatusEvent
from services.app_version import get_app_version

logger = logging.getLogger("stacky.api.diag")

bp = Blueprint("diag", __name__, url_prefix="/diag")


@bp.get("/execution/<int:execution_id>")
def diagnose_execution(execution_id: int):
    """Snapshot diagnóstico completo de una ejecución."""
    with session_scope() as session:
        exec_row = session.get(AgentExecution, execution_id)
        if exec_row is None:
            return jsonify({"ok": False, "error": "execution_not_found", "execution_id": execution_id}), 404

        ticket_row = (
            session.get(Ticket, exec_row.ticket_id) if exec_row.ticket_id else None
        )

        execution_payload = {
            "id": exec_row.id,
            "ticket_id": exec_row.ticket_id,
            "agent_type": exec_row.agent_type,
            "status": exec_row.status,
            "started_by": exec_row.started_by,
            "started_at": _iso(exec_row.started_at),
            "completed_at": _iso(exec_row.completed_at),
            "error_message": exec_row.error_message,
            "completion_source": getattr(exec_row, "completion_source", None),
        }
        ticket_payload = (
            {
                "id": ticket_row.id,
                "ado_id": ticket_row.ado_id,
                "project": ticket_row.project,
                "title": ticket_row.title,
                "ado_state": ticket_row.ado_state,
                "stacky_status": getattr(ticket_row, "stacky_status", None),
                "work_item_type": ticket_row.work_item_type,
            }
            if ticket_row
            else None
        )

        history_rows = (
            session.query(TicketStatusEvent)
            .filter(TicketStatusEvent.execution_id == execution_id)
            .order_by(TicketStatusEvent.changed_at.asc())
            .all()
        )
        recovery_history = [
            {
                "old_status": ev.old_status,
                "new_status": ev.new_status,
                "changed_by": ev.changed_by,
                "changed_at": _iso(ev.changed_at),
                "reason": ev.reason,
            }
            for ev in history_rows
        ]

        started_at_dt = exec_row.started_at
        status_in_db = exec_row.status

    manifest_payload = _read_manifest(execution_id)
    is_stale, hb_status = is_execution_heartbeat_stale(
        execution_id, started_at=started_at_dt
    )
    heartbeat_payload = hb_status.to_dict()

    diagnosis, recommended_action = _diagnose(
        status_in_db=status_in_db,
        manifest=manifest_payload,
        heartbeat_stale=is_stale,
        heartbeat=hb_status,
    )

    return jsonify({
        "ok": True,
        "execution": execution_payload,
        "ticket": ticket_payload,
        "manifest": manifest_payload,
        "heartbeat": heartbeat_payload,
        "recovery_history": recovery_history,
        "diagnosis": diagnosis,
        "recommended_action": recommended_action,
        "thresholds": {
            "pre_run_timeout_seconds": PRE_RUN_TIMEOUT_SECONDS,
            "heartbeat_timeout_minutes": HEARTBEAT_TIMEOUT_MINUTES,
            "startup_grace_seconds": STARTUP_GRACE_SECONDS,
        },
    })


@bp.post("/output-watcher/scan-now")
def output_watcher_scan_now():
    """Dispara una pasada manual del output_watcher.

    Útil para cerrar runs huérfanos inmediatamente sin esperar el polling
    interval. También sirve para troubleshooting: si un comment.html está en
    disco pero el run sigue running, hacer scan-now y leer el `round` del
    response.
    """
    from services.output_watcher import AdoOutputWatcher, get_output_watcher

    # Si el singleton no está arrancado (caso watcher disabled vía env),
    # creamos uno ad-hoc para esta pasada — la usabilidad lo justifica.
    watcher = get_output_watcher()
    ad_hoc = False
    if watcher is None:
        watcher = AdoOutputWatcher()
        ad_hoc = True

    round_result = watcher.scan_once()

    return jsonify({
        "ok": True,
        "ad_hoc_watcher": ad_hoc,
        "round": round_result,
        "stats_total": watcher.stats.as_dict(),
    })


@bp.get("/output-watcher/stats")
def output_watcher_stats():
    """Stats acumuladas del output_watcher (solo lectura)."""
    from services.output_watcher import get_output_watcher

    watcher = get_output_watcher()
    if watcher is None:
        return jsonify({
            "ok": True,
            "running": False,
            "stats": None,
        })
    return jsonify({
        "ok": True,
        "running": watcher._thread is not None and watcher._thread.is_alive(),
        "stats": watcher.stats.as_dict(),
        "config": {
            "outputs_dir": str(watcher.outputs_dir),
            "poll_interval": watcher.poll_interval,
            "stable_delay_b": watcher.stable_delay_b,
            "stable_delay_a": watcher.stable_delay_a,
        },
    })


@bp.get("/metrics")
def metrics():
    """Métricas operacionales del lifecycle de ejecuciones.

    Devuelve JSON con:
      - executions_by_status: counter por status.
      - duration_ms: p50 / p95 / p99 de runs completados (ventana últimas 200).
      - recoveries: counter por kind (heartbeat_timeout, execution_timeout,
        execution_ended, no_execution, manifest_orphan_detected).
      - currently_running: cantidad de runs en status=running.
      - oldest_running_age_seconds: edad de la ejecución running más vieja.
      - thresholds: umbrales activos (timeouts, intervals).
    """
    from sqlalchemy import func

    with session_scope() as session:
        status_rows = (
            session.query(AgentExecution.status, func.count(AgentExecution.id))
            .group_by(AgentExecution.status)
            .all()
        )
        executions_by_status = {s: int(n) for s, n in status_rows}

        # Duraciones de los últimos 200 runs completados
        completed_rows = (
            session.query(AgentExecution.started_at, AgentExecution.completed_at)
            .filter(
                AgentExecution.status == "completed",
                AgentExecution.completed_at.isnot(None),
            )
            .order_by(AgentExecution.id.desc())
            .limit(200)
            .all()
        )
        durations_ms = sorted(
            int((c - s).total_seconds() * 1000)
            for s, c in completed_rows
            if s is not None and c is not None
        )

        # Recovery counters desde TicketStatusEvent: parsea el 'reason' o
        # cuenta por changed_by prefix `system:reaper` / `system:recovery`.
        recovery_rows = (
            session.query(TicketStatusEvent.reason, TicketStatusEvent.changed_by)
            .filter(
                (TicketStatusEvent.changed_by.like("system:reaper%"))
                | (TicketStatusEvent.changed_by.like("system:recovery%"))
            )
            .all()
        )
        recoveries: dict[str, int] = {}
        for reason, _changed_by in recovery_rows:
            kind = _classify_recovery_reason(reason)
            recoveries[kind] = recoveries.get(kind, 0) + 1

        currently_running = executions_by_status.get("running", 0) + executions_by_status.get("preparing", 0)
        oldest_age: float | None = None

        # Alerta (Fase P5): ejecuciones running más viejas que el umbral. Sirve
        # de señal temprana de runs huérfanos (el banner de la UI la consume)
        # antes de que el reaper las cierre por timeout duro.
        alert_minutes = int(os.getenv("STACKY_RUNNING_ALERT_MINUTES", "30"))
        alert_cutoff = datetime.utcnow() - timedelta(minutes=alert_minutes)
        stale_suspects: list[dict] = []
        if currently_running:
            running_rows = (
                session.query(AgentExecution)
                .filter(AgentExecution.status.in_(["preparing", "running"]))
                .order_by(AgentExecution.started_at.asc())
                .all()
            )
            if running_rows and running_rows[0].started_at:
                oldest_age = (datetime.utcnow() - running_rows[0].started_at).total_seconds()
            for r in running_rows:
                if r.started_at and r.started_at < alert_cutoff:
                    stale_suspects.append({
                        "execution_id": r.id,
                        "ticket_id": r.ticket_id,
                        "agent_type": r.agent_type,
                        "age_seconds": int((datetime.utcnow() - r.started_at).total_seconds()),
                    })

    return jsonify({
        "ok": True,
        "executions_by_status": executions_by_status,
        "duration_ms": _percentiles(durations_ms),
        "recoveries": recoveries,
        "currently_running": currently_running,
        "oldest_running_age_seconds": oldest_age,
        "running_over_threshold_count": len(stale_suspects),
        "running_over_threshold": stale_suspects,
        "thresholds": {
            "execution_timeout_minutes": EXECUTION_TIMEOUT_MINUTES,
            "pre_run_timeout_seconds": PRE_RUN_TIMEOUT_SECONDS,
            "heartbeat_timeout_minutes": HEARTBEAT_TIMEOUT_MINUTES,
            "startup_grace_seconds": STARTUP_GRACE_SECONDS,
            "running_alert_minutes": alert_minutes,
        },
    })


@bp.get("/health")
def health():
    """Health de configuración del deploy (preflight, Fase P2).

    Responde las preguntas que importan para diagnosticar runs huérfanos del
    flujo open-chat de un vistazo:
      - repo_root / outputs_dir resueltos + existencia (causa raíz C1).
      - active_project (si no hay → el watcher congelado no resuelve repo_root).
      - ado_pat_present (causa raíz C2: sin PAT no se crean Tasks).
      - estado de los watchers (output / manifest) y flags relevantes.

    Solo lectura: no muta nada. Pensado para troubleshooting y monitoreo.
    """
    from runtime_paths import repo_root as _repo_root
    from services.agent_html_output import outputs_dir as _outputs_dir

    try:
        repo_root_path = _repo_root()
    except Exception as exc:  # noqa: BLE001
        repo_root_path = None
        repo_root_err = str(exc)
    else:
        repo_root_err = None

    try:
        outputs_path = _outputs_dir()
        outputs_exists = outputs_path.exists()
    except Exception as exc:  # noqa: BLE001
        outputs_path = None
        outputs_exists = False
        repo_root_err = repo_root_err or str(exc)

    try:
        from project_manager import get_active_project
        active_project = get_active_project()
    except Exception:
        active_project = None

    try:
        from services.ado_client import ado_pat_present
        pat_present = ado_pat_present()
    except Exception:
        pat_present = False

    auto_create_tasks = (
        os.getenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true").lower() != "false"
    )

    # Estado de watchers (sin arrancar nada ad-hoc).
    from services.output_watcher import get_output_watcher
    ow = get_output_watcher()
    output_watcher_info = {
        "running": bool(ow and ow._thread and ow._thread.is_alive()),
        "watching_dir": str(ow.outputs_dir) if ow else None,
    }

    # Señales de salud "dura": condiciones que romperían el cierre automático.
    warnings: list[str] = []
    if outputs_path is None or not outputs_exists:
        warnings.append(
            "outputs_dir no existe — el output_watcher no encontrará artifacts "
            "(¿proyecto activo? ¿STACKY_REPO_ROOT?)"
        )
    if active_project is None:
        warnings.append("sin proyecto activo — repo_root puede no resolver en deploy congelado")
    if auto_create_tasks and not pat_present:
        warnings.append("auto-create de Tasks habilitado pero ADO PAT ausente → las Tasks no se crearán")

    return jsonify({
        "ok": True,
        "healthy": not warnings,
        "version": get_app_version(),
        "repo_root": str(repo_root_path) if repo_root_path else None,
        "repo_root_error": repo_root_err,
        "outputs_dir": str(outputs_path) if outputs_path else None,
        "outputs_dir_exists": outputs_exists,
        "active_project": active_project,
        "ado_pat_present": pat_present,
        "auto_create_tasks_enabled": auto_create_tasks,
        "local_llm_enabled": bool(getattr(_config.config, "LOCAL_LLM_ENABLED", False)),  # Plan 106
        "watchers": {"output_watcher": output_watcher_info},
        "warnings": warnings,
    })


@bp.get("/local")
def local_diagnostics():
    """Diagnóstico operativo local de la instalación del operador."""
    from services.local_diagnostics import run_local_diagnostics

    return jsonify(run_local_diagnostics())


@bp.get("/git/pull-check")
def git_pull_check():
    """Diagnostico report-only de frescura Git del workspace.

    Query params:
      project: nombre Stacky del proyecto (opcional; default activo)
      workspace_root: override explicito para troubleshooting
      fetch=true: ejecuta git fetch --prune con prompts deshabilitados
    """
    from services.pre_run_git import run_pull_check
    from services.project_context import resolve_project_context

    project_name = (request.args.get("project") or "").strip() or None
    workspace_root = (request.args.get("workspace_root") or "").strip() or None
    fetch = (request.args.get("fetch") or "").strip().lower() in {"1", "true", "yes", "on"}

    ctx = resolve_project_context(project_name=project_name) if not workspace_root else None
    if workspace_root is None and ctx is not None:
        workspace_root = ctx.workspace_root

    result = run_pull_check(
        workspace_root,
        enabled=False,
        required=False,
        fetch=fetch,
    )
    payload = result.to_dict()
    payload["project"] = ctx.stacky_project_name if ctx else project_name
    payload["report_only"] = True
    return jsonify(payload)


@bp.post("/backup/run")
def run_db_backup():
    """Fuerza una verificación/backup semanal de la DB local."""
    from services.db_backup import ensure_weekly_backup

    return jsonify(ensure_weekly_backup())


@bp.get("/logs/export")
def export_local_logs():
    """Exporta los últimos 3 días de logs locales rotativos como ZIP."""
    from services.local_file_logging import build_logs_zip, export_filename

    payload = build_logs_zip(days=3)
    return send_file(
        io.BytesIO(payload),
        mimetype="application/zip",
        as_attachment=True,
        download_name=export_filename(),
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _percentiles(samples: list[int]) -> dict[str, int | None]:
    """Calcula p50/p95/p99 sobre una lista YA ordenada. None si vacía."""
    if not samples:
        return {"count": 0, "p50": None, "p95": None, "p99": None, "max": None}
    n = len(samples)

    def at(p: float) -> int:
        idx = min(n - 1, max(0, int(p * (n - 1))))
        return samples[idx]

    return {
        "count": n,
        "p50": at(0.50),
        "p95": at(0.95),
        "p99": at(0.99),
        "max": samples[-1],
    }


def _classify_recovery_reason(reason: str | None) -> str:
    """Mapea el texto libre del reason a una categoría enumerada."""
    if not reason:
        return "unknown"
    r = reason.lower()
    if "heartbeat" in r:
        return "heartbeat_timeout"
    if "timed out" in r or "timeout" in r:
        return "execution_timeout"
    if "last execution was already terminal" in r:
        return "execution_ended"
    if "no executions found" in r:
        return "no_execution"
    return "other"


def _read_manifest(execution_id: int) -> dict | None:
    path = default_runs_dir() / str(execution_id) / MANIFEST_FILENAME
    if not path.is_file():
        return {"exists": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("diag: manifest inválido en %s: %s", path, exc)
        return {"exists": True, "valid": False, "error": str(exc)}
    if not isinstance(data, dict):
        return {"exists": True, "valid": False, "error": "payload no es dict"}
    return {
        "exists": True,
        "valid": True,
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "signals": data.get("signals") or {},
        "exit_code": data.get("exit_code"),
        "written_at": data.get("written_at"),
        "error_message": data.get("error_message"),
    }


def _diagnose(
    *,
    status_in_db: str,
    manifest: dict | None,
    heartbeat_stale: bool,
    heartbeat,
) -> tuple[str, str | None]:
    """Decide la categoría de la situación + acción sugerida.

    Categorías:
      - terminal_clean: execution en estado terminal coherente con MANIFEST.
      - terminal_no_manifest: terminal en DB pero no hay MANIFEST (no es
        crítico, sólo para forense).
      - alive: corriendo con heartbeat reciente.
      - starting: corriendo, sin heartbeat, dentro del período de gracia.
      - manifest_orphan: MANIFEST terminal pero DB aún en running (el watcher
        debería cerrarla; si persiste, hay bug en watcher).
      - heartbeat_stale_no_manifest: corriendo, heartbeat viejo, sin MANIFEST
        (probable proceso muerto silenciosamente).
      - no_heartbeat_after_grace: corriendo, no escribió heartbeat tras grace
        (runtime no soporta heartbeat o murió en el arranque).
      - unknown: cualquier otro caso.
    """
    manifest_terminal = (
        manifest is not None
        and manifest.get("exists") is True
        and manifest.get("valid") is True
        and manifest.get("status") in {"completed", "error", "cancelled"}
    )

    if status_in_db in {"completed", "error", "cancelled", "approved"}:
        if manifest_terminal:
            return "terminal_clean", None
        return "terminal_no_manifest", None

    if status_in_db == "preparing":
        return "preparing", None

    if status_in_db in {"running", "queued"}:
        if manifest_terminal:
            return (
                "manifest_orphan",
                "Trigger POST /api/tickets/recover-stale-status — el manifest watcher debería haberlo cerrado.",
            )
        if heartbeat.exists and not heartbeat_stale:
            return "alive", None
        if not heartbeat.exists and not heartbeat_stale:
            return "starting", None
        if heartbeat.exists and heartbeat_stale:
            return (
                "heartbeat_stale_no_manifest",
                "Trigger POST /api/tickets/recover-stale-status — proceso colgado, dejará de aparecer corriendo.",
            )
        # not exists + stale => grace period elapsed
        return (
            "no_heartbeat_after_grace",
            "Trigger POST /api/tickets/recover-stale-status — el runtime nunca emitió heartbeat tras la gracia.",
        )

    return "unknown", None


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


# ── Plan 46 — Panel de Salud Operativa (triage solo-lectura) ──────────────────

def _recent_executions(session, limit: int) -> list:
    """C4: joinedload evita N+1 al leer ex.ticket.stacky_project_name en el loop."""
    stmt = (
        select(AgentExecution)
        .options(joinedload(AgentExecution.ticket))
        .order_by(AgentExecution.started_at.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


@bp.get("/operational-health")
def operational_health():
    """Plan 46 — Triage solo-lectura de runs recientes. No muta nada.

    GET /api/diag/operational-health[?limit=&cost_usd=&zombie_minutes=&needs_review_stale_days=]
    Gated por STACKY_OPERATIONAL_HEALTH_ENABLED (default true). OFF → 404.
    """
    if os.getenv("STACKY_OPERATIONAL_HEALTH_ENABLED", "true").lower() == "false":
        return jsonify({"ok": False, "error": "disabled"}), 404

    from services.operational_health import aggregate_operational_health

    # C2 — parse defensivo de limit (no romper con ?limit=abc).
    try:
        limit = int(request.args.get("limit", 200))
    except (TypeError, ValueError):
        limit = 200
    limit = max(1, min(limit, 500))

    # Umbrales: zombie default = timeout real del sistema (single source of truth);
    # los overrides del operador (query params) siguen ganando.
    thresholds: dict = {"zombie_minutes": EXECUTION_TIMEOUT_MINUTES}
    for k in ("cost_usd", "zombie_minutes", "needs_review_stale_days"):
        v = request.args.get(k)
        if v is not None:
            try:
                thresholds[k] = float(v) if k == "cost_usd" else int(float(v))
            except (TypeError, ValueError):
                pass

    rows = []
    with session_scope() as session:
        for ex in _recent_executions(session, limit):
            d = ex.to_dict(include_output=False)
            d["project"] = ex.ticket.stacky_project_name if ex.ticket else None
            rows.append(d)

    result = aggregate_operational_health(
        rows, now_iso=datetime.utcnow().isoformat(), thresholds=thresholds or None
    )
    result["ok"] = True
    return jsonify(result)


@bp.get("/code-integrity")
def code_integrity_route():
    """Plan 130 — gate determinista de sintaxis + imports (read-only, sin IA)."""
    if not bool(getattr(_config.config, "STACKY_CODE_INTEGRITY_ENABLED", False)):
        return jsonify({"ok": False, "error": "code_integrity_disabled",
                        "message": "El verificador de integridad está deshabilitado (STACKY_CODE_INTEGRITY_ENABLED)."}), 404
    from services import code_integrity as ci  # import lazy (patrón Plan 109)
    try:
        return jsonify(ci.run_checks())
    except Exception as exc:
        return jsonify({"ok": False, "error": type(exc).__name__}), 200
