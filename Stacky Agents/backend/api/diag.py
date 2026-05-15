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
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify

from db import session_scope
from models import AgentExecution, Ticket
from services.heartbeat_monitor import (
    HEARTBEAT_TIMEOUT_MINUTES,
    STARTUP_GRACE_SECONDS,
    is_execution_heartbeat_stale,
)
from services.manifest_watcher import MANIFEST_FILENAME, default_runs_dir
from services.ticket_status import TicketStatusEvent

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
            "heartbeat_timeout_minutes": HEARTBEAT_TIMEOUT_MINUTES,
            "startup_grace_seconds": STARTUP_GRACE_SECONDS,
        },
    })


# ── Helpers ──────────────────────────────────────────────────────────────────


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
