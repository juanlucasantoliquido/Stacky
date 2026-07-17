"""Plan 133 F1 — Refresh just-in-time del snapshot local del ticket antes del run.

Re-sincroniza work_item_type/ado_state/título/descripción del ticket desde el
tracker (solo Azure DevOps en v1) al inicio de POST /api/agents/run, para que
el preflight de negocio (F2) y la inyección de contexto (F4) decidan sobre
datos frescos en vez de un snapshot local potencialmente stale.

Fail-open ante red (§3.3 del plan): cualquier error de red/tracker degrada a
{"refreshed": False, "reason": "tracker_error: <detalle>"}, nunca levanta.
"""
from __future__ import annotations

import logging

from db import session_scope
from models import Ticket

logger = logging.getLogger("stacky.services.run_ticket_refresh")


def refresh_ticket_snapshot(ticket_id: int | None) -> dict:
    """Re-sincroniza el work item del ticket desde el tracker (ADO).

    Retorna {"refreshed": bool, "reason": str}. NUNCA levanta excepción.
    Con flag OFF, ticket inexistente/None, ado_id ausente/<=0 (sentinels
    -1..-8 incluidos), o tracker no-ADO: no-op con el "reason" apropiado.
    """
    from config import config

    if not getattr(config, "STACKY_RUN_TICKET_REFRESH_ENABLED", False):
        return {"refreshed": False, "reason": "flag_off"}

    if not ticket_id:
        return {"refreshed": False, "reason": "no_ado_id"}

    with session_scope() as session:
        ticket = session.query(Ticket).filter_by(id=ticket_id).first()
        if ticket is None:
            return {"refreshed": False, "reason": "no_ado_id"}
        ado_id = ticket.ado_id
        if not ado_id or ado_id <= 0:
            return {"refreshed": False, "reason": "no_ado_id"}
        tracker_type = ticket.tracker_type or "azure_devops"
        if tracker_type != "azure_devops":
            return {"refreshed": False, "reason": "non_ado_tracker"}
        stacky_project_name = ticket.stacky_project_name
        tracker_project = ticket.project

    try:
        from services.project_context import build_ado_client
        from services import ado_read_cache
        from services.ado_sync import upsert_single_work_item

        client = build_ado_client(
            project_name=stacky_project_name, tracker_project=tracker_project
        )
        ttl = int(getattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 0) or 0)
        ado_read_cache.get_or_fetch(
            ("run_refresh", ado_id),
            lambda: upsert_single_work_item(client, ado_id),
            ttl_sec=ttl,
        )
        return {"refreshed": True, "reason": "ok"}
    except Exception as exc:  # noqa: BLE001 — fail-open ante red (§3.3)
        logger.warning(
            "refresh_ticket_snapshot(ticket=%s, ado_id=%s) falló (fail-open): %s",
            ticket_id, ado_id, exc,
        )
        return {"refreshed": False, "reason": f"tracker_error: {exc}"}
