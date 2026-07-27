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
from services.app_version import get_app_version, get_source_commit, get_built_at, get_repo_head, get_build_drift

logger = logging.getLogger("stacky.api.diag")

bp = Blueprint("diag", __name__, url_prefix="/diag")


def build_diagnosis_snapshot(execution_id: int) -> dict | None:
    """Snapshot forense completo de una ejecución (dict listo para jsonify).
    None si la ejecución no existe. Reusada por el Plan 127 (error-analysis)."""
    with session_scope() as session:
        exec_row = session.get(AgentExecution, execution_id)
        if exec_row is None:
            return None

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

    return {
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
    }


@bp.get("/execution/<int:execution_id>")
def diagnose_execution(execution_id: int):
    """Snapshot diagnóstico completo de una ejecución."""
    snapshot = build_diagnosis_snapshot(execution_id)
    if snapshot is None:
        return jsonify({"ok": False, "error": "execution_not_found", "execution_id": execution_id}), 404
    return jsonify(snapshot)


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


def _quarantine_age_days(first_seen: str | None) -> int:
    """Plan 256 F3 — dias enteros desde `first_seen`. Es el campo que hace
    visible un artefacto atascado hace 11 dias; sin el, la tarjeta muestra una
    lista sin urgencia. Tolerante: si la marca de tiempo no se puede leer,
    devuelve 0 en vez de romper el diagnostico."""
    if not first_seen:
        return 0
    texto = str(first_seen).strip().replace("Z", "+00:00")
    try:
        cuando = datetime.fromisoformat(texto)
    except ValueError:
        return 0
    from datetime import timezone as _tz
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=_tz.utc)
    delta = datetime.now(_tz.utc) - cuando
    return max(int(delta.total_seconds() // 86400), 0)


# Accion del interlock de confirmacion del descarte (plan 256 F4). Namespaced
# para que un identificador emitido para otra accion no sirva aca.
_DISCARD_ACTION = "intake_quarantine_discard"


class _PathOutsideOutputs(ValueError):
    """El `path` que mando el cliente no cae bajo el outputs_dir del watcher."""


def _assert_under_outputs(raw_path: str) -> Path:
    """Plan 256 F4 — 400 si el path no cae bajo el outputs_dir del watcher vivo.

    Se usa la property de la INSTANCIA viva (`outputs_dir`), no `_outputs_dir()`
    a secas: la property respeta `_outputs_dir_override`, que es lo que usan los
    tests y un proyecto con override. `resolve()` colapsa `..`, symlinks y 8.3;
    `os.path.normcase` cubre el case-insensitive de Windows; el `+ os.sep` evita
    que `C:\\outputs-evil` pase como hijo de `C:\\outputs`.
    """
    from services.output_watcher import AdoOutputWatcher, get_output_watcher

    watcher = get_output_watcher() or AdoOutputWatcher()
    base = watcher.outputs_dir.resolve()
    candidato = Path(raw_path or "").resolve()
    base_n = os.path.normcase(str(base))
    cand_n = os.path.normcase(str(candidato))
    if cand_n != base_n and not cand_n.startswith(base_n + os.sep):
        raise _PathOutsideOutputs("path fuera de outputs_dir")
    return candidato


def _quarantine_surface_enabled() -> bool:
    return bool(getattr(_config.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", True))


@bp.get("/intake-quarantine")
def intake_quarantine():
    """Plan 149 F7 — Snapshot read-only GLOBAL de la cuarentena de intake.

    Complementa el board Desatascador (epic-scoped) con una vista total, incluidos
    archivos cuya Epic no resuelve. Read-only, sin efectos. Gobernado por el mismo
    kill-switch que la superficie del board (F4), sin flag nueva.

    Plan 256 F3 — ADITIVO: `path`/`reason`/`mtime_ns` se conservan con el mismo
    nombre y tipo (hay consumidores) y se agregan la causa tipada, la antiguedad
    en dias, las ocurrencias y si el artefacto se puede reintentar. Los
    descartados por el operador NO se listan salvo `?include_discarded=1`.
    """
    if not _quarantine_surface_enabled():
        return jsonify({"enabled": False, "items": []})
    from services.output_watcher import quarantine_snapshot

    incluir_descartados = (request.args.get("include_discarded") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    items = []
    for path, entry in quarantine_snapshot().items():
        descartado = bool(entry.get("discarded"))
        if descartado and not incluir_descartados:
            continue
        items.append({
            # ── contrato del plan 149, intacto ──
            "path": path,
            "reason": entry.get("reason", ""),
            "mtime_ns": entry.get("mtime_ns"),
            # ── plan 256 F3, aditivo ──
            "file_name": Path(path).name,
            "cause_code": entry.get("cause_code") or "UNKNOWN",
            "first_seen": entry.get("first_seen"),
            "age_days": _quarantine_age_days(entry.get("first_seen")),
            "occurrences": int(entry.get("occurrences") or 1),
            "has_original_backup": bool(entry.get("has_original_backup")),
            "discarded": descartado,
            "retryable": bool(entry.get("retryable", True)),
        })
    items.sort(key=lambda i: (-i["age_days"], i["path"]))
    return jsonify({
        "enabled": True,
        "count": len(items),
        "items": items,
        "discard_enabled": bool(
            getattr(_config.config, "STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED", False)
        ),
    })


@bp.post("/intake-quarantine/retry")
def intake_quarantine_reintento():
    """Plan 256 F4 — saca UN artefacto de la cuarentena para que el proximo scan
    lo reintente. NO DESTRUCTIVO: no toca el archivo, no crea nada, no publica.

    REUSA `clear_quarantine` (plan 149 F5), que ya deriva la clave exactamente
    igual que `_quarantine_pending_once` y documenta el gotcha de Windows. A
    proposito NO se creo un helper gemelo para reintentar.

    Idempotente: reintentar algo que no estaba en cuarentena devuelve ok=True.
    OJO: reintenta la VALIDACION, no corrige el artefacto — si la causa era la
    carpeta o el archivo vacio, va a volver a fallar hasta que el operador lo
    corrija (la razon dice exactamente que hacer).
    """
    if not _quarantine_surface_enabled():
        return jsonify({"ok": False, "error": "quarantine_surface_disabled"}), 404

    body = request.get_json(silent=True) or {}
    try:
        pt_file = _assert_under_outputs(str(body.get("path") or ""))
    except _PathOutsideOutputs as exc:
        return jsonify({"ok": False, "error": "path_outside_outputs", "detail": str(exc)}), 400

    from services.output_watcher import clear_quarantine

    estaba = bool(clear_quarantine(pt_file))
    logger.info("intake-quarantine: reintento pedido por el operador para %s (estaba=%s)",
                pt_file, estaba)
    return jsonify({"ok": True, "path": str(pt_file), "was_quarantined": estaba})


@bp.post("/intake-quarantine/discard")
def intake_quarantine_discard():
    """Plan 256 F4 — marca un artefacto como descartado por el operador.

    NO borra ni modifica el artefacto: el trabajo del agente queda intacto en
    disco y el marcador va al sidecar `<artefacto>.quarantine.json`. Aun asi
    exige confirmacion explicita, porque el marcador no se revierte desde la UI.

    Interlock de dos pasos (reusa `services/confirm_token.py` del plan 253, no
    se reimplementa): sin identificador valido responde 409 y devuelve uno nuevo
    para que la UI pueda mostrar el aviso y confirmar. NO ES SEGURIDAD — Stacky
    es mono-operador sin login; es un anti-clic-accidental.
    """
    if not getattr(_config.config, "STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED", False):
        return jsonify({"ok": False, "error": "discard_disabled"}), 404

    body = request.get_json(silent=True) or {}
    try:
        pt_file = _assert_under_outputs(str(body.get("path") or ""))
    except _PathOutsideOutputs as exc:
        return jsonify({"ok": False, "error": "path_outside_outputs", "detail": str(exc)}), 400

    from services.confirm_token import ConfirmTokenError, consume_token, issue_token

    token = str(body.get("confirm_token") or "")
    try:
        payload = consume_token(_DISCARD_ACTION, token)
    except ConfirmTokenError as exc:
        return jsonify({
            "ok": False,
            "error": "confirmation_required",
            "detail": str(exc),
            "confirm_token": issue_token(_DISCARD_ACTION, {"path": str(pt_file)}),
            "confirm_ttl_s": 120,
            "message": (
                "El artefacto queda intacto en disco. Solo se marca como descartado "
                "y el vigilante deja de reintentarlo."
            ),
        }), 409

    if str(payload.get("path") or "") != str(pt_file):
        return jsonify({
            "ok": False,
            "error": "confirmation_stale",
            "detail": "la confirmacion era para otro artefacto",
        }), 409

    from services.output_watcher import quarantine_discard

    operador = (request.headers.get("X-Current-User") or "operador").strip() or "operador"
    resultado = quarantine_discard(pt_file, operator=operador)
    if not resultado.get("ok"):
        return jsonify(resultado), 409
    return jsonify(resultado)


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

    # ── Plan 253 F7 — estado REAL de la concurrencia de la base de runtime ───
    # El operador no tenía forma de saber si el fix está VIVO en su máquina.
    # Solo lectura: no muta nada y no tiene costo ocioso.
    from db import lock_stats, sqlite_concurrency_state, startup_writes_state
    from services.db_backup import sqlite_db_path
    from services.maintenance import maintenance_state

    _db_path = sqlite_db_path()
    _conc = sqlite_concurrency_state()
    _wal_file = _db_path.with_name(_db_path.name + "-wal") if _db_path else None
    try:
        from app import _CREATE_APP_COUNT as _create_app_count
    except Exception:  # noqa: BLE001
        _create_app_count = None
    db_runtime = {
        "sqlite_file": str(_db_path) if _db_path else None,
        "db_size_bytes": _db_path.stat().st_size if _db_path and _db_path.exists() else None,
        "wal_size_bytes": _wal_file.stat().st_size if _wal_file and _wal_file.exists() else 0,
        "journal_mode_effective": _conc["journal_mode_effective"],
        "wal_status": _conc["wal_status"],          # ok | in_memory | rejected | disabled | not_sqlite
        "busy_timeout_ms": _conc["busy_timeout_ms"],
        "synchronous": _conc["synchronous"],
        "startup_writes": startup_writes_state(),   # {"armed": bool, "done": bool}
        "lock_stats": lock_stats(),                 # {"retried","recovered","exhausted"}
        "maintenance": maintenance_state(),
        "create_app_count": _create_app_count,
    }

    # Señales de salud "dura": condiciones que romperían el cierre automático.
    warnings: list[str] = []

    if db_runtime["wal_status"] == "rejected":
        warnings.append(
            "la base no pudo pasar a lectura/escritura simultánea en este disco "
            f"(quedó en '{db_runtime['journal_mode_effective']}'): puede haber "
            "errores de bloqueo bajo carga"
        )
    if (db_runtime["lock_stats"] or {}).get("exhausted", 0) > 0:
        warnings.append(
            f"{db_runtime['lock_stats']['exhausted']} operaciones se perdieron por "
            "bloqueo de la base pese a los reintentos"
        )
    if db_runtime["sqlite_file"] is None and str(_config.config.DATABASE_URL).startswith("sqlite"):
        warnings.append(
            "la base figura como archivo pero no se pudo resolver su ruta: "
            "la copia de respaldo semanal no se está haciendo"
        )
    if outputs_path is None or not outputs_exists:
        warnings.append(
            "outputs_dir no existe — el output_watcher no encontrará artifacts "
            "(¿proyecto activo? ¿STACKY_REPO_ROOT?)"
        )
    if active_project is None:
        warnings.append("sin proyecto activo — repo_root puede no resolver en deploy congelado")
    if auto_create_tasks and not pat_present:
        warnings.append("auto-create de Tasks habilitado pero ADO PAT ausente → las Tasks no se crearán")

    # Estado explícito de watchers (D8): activos SOLO si hay proyecto activo y
    # el outputs_dir resuelto existe (o sea, repo_root no es el sentinel).
    from runtime_paths import _UNRESOLVED_REPO_ROOT
    repo_root_unresolved = (repo_root_path is not None
                            and Path(repo_root_path) == _UNRESOLVED_REPO_ROOT)
    if active_project is None:
        watchers_active = False
        watchers_inactive_reason = "sin_proyecto_activo"
    elif repo_root_unresolved:
        watchers_active = False
        watchers_inactive_reason = "repo_root_no_resoluble"
    elif not outputs_exists:
        watchers_active = False
        watchers_inactive_reason = "outputs_dir_inexistente"
    else:
        watchers_active = True
        watchers_inactive_reason = None

    return jsonify({
        "ok": True,
        "healthy": not warnings,
        "version": get_app_version(),
        "source_commit": get_source_commit(),   # Plan 163 F1 — identidad de build
        "built_at": get_built_at(),              # Plan 163 F1
        "repo_head": get_repo_head(),            # Plan 163 F1 — solo dev (None en deploy)
        "build_drift": get_build_drift(),        # Plan 163 F1 — solo dev
        "repo_root": str(repo_root_path) if repo_root_path else None,
        "repo_root_error": repo_root_err,
        "outputs_dir": str(outputs_path) if outputs_path else None,
        "outputs_dir_exists": outputs_exists,
        "active_project": active_project,
        "ado_pat_present": pat_present,
        "auto_create_tasks_enabled": auto_create_tasks,
        "watchers_active": watchers_active,
        "watchers_inactive_reason": watchers_inactive_reason,
        "local_llm_enabled": bool(getattr(_config.config, "LOCAL_LLM_ENABLED", False)),  # Plan 106
        "shell_v2_enabled": bool(getattr(_config.config, "STACKY_UI_SHELL_V2_ENABLED", False)),  # Plan 139
        "ui_shortcuts_enabled": bool(getattr(_config.config, "STACKY_UI_SHORTCUTS_ENABLED", False)),  # Plan 172
        "model_picker_in_board_enabled": bool(getattr(_config.config, "STACKY_MODEL_PICKER_IN_BOARD_ENABLED", False)),  # Plan 212
        "ui_saved_views_enabled": bool(getattr(_config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", False)),  # Plan 173
        "ui_virtualization_enabled": bool(getattr(_config.config, "STACKY_UI_VIRTUALIZATION_ENABLED", False)),  # Plan 174
        "ui_prefetch_enabled": bool(getattr(_config.config, "STACKY_UI_PREFETCH_ENABLED", False)),  # Plan 174
        "ui_instant_nav_enabled": bool(getattr(_config.config, "STACKY_UI_INSTANT_NAV_ENABLED", False)),  # Plan 174
        "ui_peek_enabled": bool(getattr(_config.config, "STACKY_UI_PEEK_ENABLED", False)),  # Plan 175
        "ui_context_menu_enabled": bool(getattr(_config.config, "STACKY_UI_CONTEXT_MENU_ENABLED", False)),  # Plan 175
        "watchers": {"output_watcher": output_watcher_info},
        "db_runtime": db_runtime,   # Plan 253 F7 — concurrencia de la base, consultable
        "warnings": warnings,
    })


# ── Plan 253 F6 — compactacion asistida de la base (HITL, destructiva) ───────


@bp.get("/db/stats")
def db_stats_route():
    """Diagnostico read-only de la base de runtime + identificador de confirmacion.

    El identificador (TTL 120 s, un solo uso) transporta el conteo EXACTO que se
    le muestra al operador: no es seguridad, es un interlock anti-clic-accidental.
    """
    from services.db_maintenance import db_stats, issue_compact_token

    stats = db_stats()
    if not _config.config.STACKY_DB_COMPACT_ENABLED:
        return jsonify({**stats, "compact_enabled": False, "confirm_token": None})
    if not stats.get("available"):
        return jsonify({**stats, "compact_enabled": True, "confirm_token": None}), 409
    return jsonify({
        **stats,
        "compact_enabled": True,
        "confirm_token": issue_compact_token(stats),
        "confirm_ttl_s": 120,
    })


@bp.post("/db/compact")
def db_compact_route():
    """Compacta la base. DESTRUCTIVO e IRREVERSIBLE: exige confirmacion explicita.

    Respalda antes (reusando la convencion de nombre existente), hace
    wal_checkpoint(TRUNCATE) y recien despues el VACUUM. Sin identificador
    valido, o con el conteo cambiado, responde 409 y no toca nada.
    """
    from services.db_maintenance import CompactError, compact_db

    body = request.get_json(silent=True) or {}
    token = str(body.get("confirm_token") or "")
    purge_retroactive = bool(body.get("purge_retroactive", True))
    try:
        return jsonify(compact_db(token=token, purge_retroactive=purge_retroactive))
    except CompactError as exc:
        return jsonify({"ok": False, "error": exc.reason, "detail": str(exc)}), 409


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


@bp.get("/logs/noise")
def logs_noise_route():
    """Plan 257 F3 — las firmas de log mas repetidas, desde MEMORIA.

    Sale de `get_throttle_filter().snapshot()`, que ya tiene los contadores en
    memoria: cero costo extra, no se re-parsea ningun archivo de disco. Y
    `snapshot()` es READ-ONLY: la UI mira el rastro, nunca lo borra (el unico
    que resetea es el flush determinista de F1-ter).

    Con la flag apagada o sin filtro instalado devuelve 200 con
    `enabled: false` — no 404, no 500: un panel de diagnostico no debe romperse
    porque una flag este apagada.
    """
    from services.local_file_logging import get_throttle_filter

    ventana = float(getattr(_config.config, "STACKY_LOG_THROTTLE_WINDOW_S", 60.0))
    flush_s = int(getattr(_config.config, "STACKY_LOG_THROTTLE_FLUSH_S", 300))
    habilitada = bool(getattr(_config.config, "STACKY_LOG_THROTTLE_ENABLED", True))
    # `card_enabled` es EJE APARTE de `enabled`: apagar la tarjeta no debe
    # apagar la consulta (el operador puede querer el dato sin la tarjeta), y
    # apagar el agrupado no debe devolver 404. La tarjeta es su unico consumidor.
    tarjeta = bool(getattr(_config.config, "STACKY_UI_LOG_NOISE_CARD_ENABLED", True))
    flt = get_throttle_filter()

    if not habilitada or flt is None:
        return jsonify({
            "enabled": False,
            "card_enabled": tarjeta,
            "window_s": ventana,
            "flush_interval_s": flush_s,
            "signatures": [],
        }), 200

    try:
        firmas = flt.snapshot()
    except Exception:  # noqa: BLE001 — un diagnostico jamas rompe el panel
        logger.debug("logs/noise fallo", exc_info=True)
        firmas = []

    return jsonify({
        "enabled": True,
        "card_enabled": tarjeta,
        "window_s": flt.window_s,
        "flush_interval_s": flush_s,
        "signatures": firmas,
    }), 200


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


@bp.get("/run-reconciliation")
def run_reconciliation_route():
    """Plan 254 F5 — el falso ROJO, medido. READ-ONLY absoluto.

    Compara, para cada run terminado, el estado del ticket contra la evidencia
    objetiva del run y LISTA las discrepancias. No cambia ningún estado, no
    reintenta y no corre en un loop: es un GET bajo demanda. El operador decide
    qué hacer con cada línea.

    `red_with_delivered_work` es literalmente el contador del falso rojo.
    """
    if not bool(getattr(_config.config, "STACKY_RUN_RECONCILIATION_ENABLED", True)):
        return jsonify({
            "ok": False,
            "error": "run_reconciliation_disabled",
            "message": "La reconciliación de corridas está deshabilitada (STACKY_RUN_RECONCILIATION_ENABLED).",
        }), 404
    from services import run_reconciliation as rr  # import lazy (patrón Plan 109)

    limit = request.args.get("limit", default=200, type=int) or 200
    try:
        result = rr.summarize(rr.scan_recent(limit=limit))
    except Exception as exc:  # noqa: BLE001 — un diagnóstico jamás rompe el panel
        logger.debug("run-reconciliation falló", exc_info=True)
        return jsonify({
            "ok": False, "error": type(exc).__name__,
            "total": 0, "by_kind": {k: 0 for k in rr.DISCREPANCY_KINDS}, "items": [],
        }), 200
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


@bp.get("/silent-failures")
def silent_failures_route():
    """Plan 255 F1 — cuántos fallos se tragó cada `except`, en esta ventana.

    READ-ONLY y sin costo ocioso: es un GET a pedido sobre un dict en memoria.
    La respuesta DECLARA su ventana porque el contador vive en RAM y el backend
    reinicia varias veces por día: `count == 0` no prueba que un sitio sea
    inerte, solo que no se disparó desde el último arranque.
    """
    if not bool(getattr(_config.config, "STACKY_SILENT_FAILURE_COUNTER_ENABLED", True)):
        return jsonify({
            "ok": False,
            "error": "silent_failure_counter_disabled",
            "message": "El contador de fallos silenciados está deshabilitado "
                       "(STACKY_SILENT_FAILURE_COUNTER_ENABLED).",
        }), 404
    from services import silent_failure_counter as sfc  # import lazy (patrón Plan 109)

    limit = request.args.get("top", default=10, type=int) or 10
    try:
        reporte = sfc.swallowed_report(top=limit)
    except Exception as exc:  # noqa: BLE001 — un diagnóstico jamás rompe el panel
        logger.debug("silent-failures falló", exc_info=True)
        return jsonify({"ok": False, "error": type(exc).__name__,
                        "window": None, "rows": []}), 200
    reporte["ok"] = True
    return jsonify(reporte)


@bp.get("/dormant-canaries")
def dormant_canaries_route():
    """Plan 255 F6 — mecanismos caros que dejaron de dar señal de ÉXITO.

    Lo inverso a una huella de regresión: alarma cuando un patrón BUENO deja de
    aparecer. AVISA, NUNCA ARREGLA: no reintenta, no re-habilita y no toca
    config. Lee bajo demanda un tail acotado del log local (sin loop, sin red,
    sin modelo), así que la flag puede estar default ON sin quemar nada.
    """
    if not bool(getattr(_config.config, "STACKY_DORMANT_CANARY_ENABLED", True)):
        return jsonify({
            "ok": False,
            "error": "dormant_canary_disabled",
            "message": "El canario de mecanismos dormidos está deshabilitado "
                       "(STACKY_DORMANT_CANARY_ENABLED).",
        }), 404
    from services import dormant_canary as dc  # import lazy (patrón Plan 109)

    try:
        filas = dc.check_canaries()
    except Exception as exc:  # noqa: BLE001 — un diagnóstico jamás rompe el panel
        logger.debug("dormant-canaries falló", exc_info=True)
        return jsonify({"ok": False, "error": type(exc).__name__, "canaries": []}), 200
    return jsonify({"ok": True, "canaries": filas})


# ---------------------------------------------------------------------------
# Plan 258 F3/F4 — Salud de ledgers: procedencia, huerfanos y limpieza asistida
# ---------------------------------------------------------------------------
# Los ledgers JSONL deberian darle al operador visibilidad de lo que la UI no
# muestra. Medido antes de este plan: `ci_runs.jsonl` tenia 8 de 8 lineas de
# fixture de test y `env_applies.jsonl` 10 de 10 escritas por pytest. No eran
# una fuente de verdad: eran archivos mezclados.
#
# READ-ONLY salvo el POST, que es la UNICA pieza destructiva del plan y esta
# detras de flag OFF por default, `dry_run` explicito, confirmacion y copia.

_LEDGER_CONFIRM_TTL_S = 120


@bp.get("/ledgers/health")
def ledgers_health():
    """Plan 258 F3 — desglose por procedencia de cada archivo de registro.

    Por ledger: total de lineas y cuantas son de produccion, de test o de
    procedencia desconocida. Para `ci_runs`, ademas, las corridas REALES que
    nunca reportaron desenlace.

    `unknown` NO es `prod`: una linea historica sin marca no se puede afirmar
    como real, y este plan no inventa datos. Tampoco se oculta.
    """
    from services import ledger_writer as lw  # import lazy (patron Plan 109)

    purga_on = bool(getattr(_config.config, "STACKY_LEDGER_PURGE_ENABLED", False))
    filas: list[dict] = []
    borrables_total = 0
    for nombre in lw.LEDGER_NAMES:
        try:
            desglose = lw.env_breakdown(nombre)
        except Exception:  # noqa: BLE001 — un diagnostico jamas rompe el panel
            logger.debug("ledgers/health: fallo el desglose de %s", nombre, exc_info=True)
            desglose = {"total": 0, "prod": 0, "test": 0, "unknown": 0}

        purgable = lw.purgeable(nombre)
        borrables = desglose.get("test", 0) if purgable else 0
        borrables_total += borrables

        token = None
        if purga_on and borrables > 0:
            # El identificador transporta el conteo EXACTO que se le muestra al
            # operador: no puede confirmar una cifra distinta de la que vio.
            from services.confirm_token import issue_token
            token = issue_token(lw.PURGE_ACTION,
                                {"ledger": nombre, "deletable": borrables},
                                ttl_s=_LEDGER_CONFIRM_TTL_S)

        filas.append({
            "name": nombre,
            "total": desglose.get("total", 0),
            "prod": desglose.get("prod", 0),
            "test": desglose.get("test", 0),
            "unknown": desglose.get("unknown", 0),
            "purgeable": purgable,
            "deletable": borrables,
            "confirm_token": token,
        })

    try:
        from services.ci_run_ledger import orphan_ci_runs
        huerfanos = orphan_ci_runs()
    except Exception:  # noqa: BLE001
        logger.debug("ledgers/health: fallo el reporte de huerfanos", exc_info=True)
        huerfanos = []

    return jsonify({
        "ok": True,
        "ledgers": filas,
        "orphans": huerfanos,
        "orphans_enabled": bool(getattr(
            _config.config, "STACKY_LEDGER_ORPHAN_REPORT_ENABLED", True)),
        "deletable_total": borrables_total,
        "purge_enabled": purga_on,
        "confirm_ttl_s": _LEDGER_CONFIRM_TTL_S,
    })


@bp.post("/ledgers/purge-test-lines")
def ledgers_purge_test_lines():
    """Plan 258 F4 — borra las lineas de fixture de un archivo de registro.

    LA UNICA PIEZA DESTRUCTIVA DEL PLAN, y por eso lleva cuatro candados en
    serie: (1) la perilla nace APAGADA; (2) el cuerpo debe traer `dry_run`
    EXPLICITO en false — ausente, de otro tipo o cuerpo vacio significan
    `dry_run=true`, asi que un pedido mal formado NUNCA borra; (3) hace falta la
    confirmacion emitida por `GET /ledgers/health`, que ademas transporta el
    conteo exacto que se mostro; (4) se guarda una copia antes y, si la copia
    falla, se aborta.

    NUNCA toca lineas `prod` ni `unknown`: solo lo probadamente de test.
    NO ES SEGURIDAD — Stacky es mono-operador sin login; es un anti-clic-accidental.
    """
    from services import ledger_writer as lw  # import lazy (patron Plan 109)

    if not bool(getattr(_config.config, "STACKY_LEDGER_PURGE_ENABLED", False)):
        return jsonify({"ok": False, "error": "ledger_purge_disabled",
                        "message": "La limpieza de archivos de registro esta "
                                   "deshabilitada (STACKY_LEDGER_PURGE_ENABLED)."}), 404

    body = request.get_json(silent=True) or {}
    nombre = str(body.get("ledger") or "")
    if nombre not in lw.LEDGER_NAMES:
        return jsonify({"ok": False, "error": "ledger_desconocido",
                        "detail": f"{nombre!r} no esta en el inventario"}), 400

    # C14 — en el endpoint MANDA el cuerpo. Solo un `false` booleano explicito
    # habilita el borrado; cualquier otra cosa cae en dry-run.
    crudo = body.get("dry_run", True)
    dry_run = True if not isinstance(crudo, bool) else crudo

    from services.confirm_token import ConfirmTokenError, issue_token

    try:
        resultado = lw.purge_test_lines(nombre, confirm_token=str(body.get("confirm_token") or ""),
                                        dry_run=dry_run)
    except ConfirmTokenError as exc:
        borrables = lw.deletable_count(nombre)
        return jsonify({
            "ok": False,
            "error": "confirmation_required",
            "detail": str(exc),
            "ledger": nombre,
            "deletable": borrables,
            "confirm_token": issue_token(lw.PURGE_ACTION,
                                         {"ledger": nombre, "deletable": borrables},
                                         ttl_s=_LEDGER_CONFIRM_TTL_S),
            "confirm_ttl_s": _LEDGER_CONFIRM_TTL_S,
            "message": (f"Se eliminaran {borrables} lineas de fixture de {nombre}.jsonl. "
                        "Las de produccion y las de procedencia desconocida NO se tocan. "
                        "Se guarda una copia antes."),
        }), 409

    if not resultado.get("ok"):
        return jsonify(resultado), 409
    return jsonify(resultado)
