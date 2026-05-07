"""
services/mantis_sync.py — Sincroniza issues de Mantis BT con la BD local.

Interfaz equivalente a jira_sync.sync_tickets() / ado_sync.sync_tickets()
para que api/tickets.py pueda usarlos indistintamente.
"""

from __future__ import annotations

import logging
from datetime import datetime

from db import session_scope
from models import AgentExecution, Ticket
from services.mantis_client import (
    MantisClient,
    MantisSOAPClient,
    AnyMantisClient,
    get_mantis_client,
    MantisApiError,
    MantisConfigError,
    _PRIORITY_MAP,
)

logger = logging.getLogger("stacky_agents.mantis_sync")


def _project_key(client) -> str:
    """Clave del proyecto en la BD: 'mantis-{project_id}'."""
    return f"mantis-{client.project_id}"


def sync_tickets(
    client=None,
    tracker_config: dict | None = None,
) -> dict:
    """
    Sincroniza issues de Mantis con la BD local.

    Si se provee tracker_config, construye el cliente adecuado (REST o SOAP)
    a partir de esa config usando get_mantis_client().
    Si se provee client directamente, se usa ese.

    Retorna dict con las mismas claves que ado_sync / jira_sync:
      { project, fetched, created, updated, removed, synced_at }
    """
    if client is None:
        if tracker_config is None:
            raise MantisConfigError("Se requiere un MantisClient o tracker_config.")
        client = get_mantis_client(
            url        = tracker_config.get("url", ""),
            project_id = tracker_config.get("project_id", ""),
            protocol   = tracker_config.get("protocol", "rest"),
            auth_file  = tracker_config.get("auth_file", "auth/mantis_auth.json"),
            verify_ssl = tracker_config.get("verify_ssl", True),
        )

    issues = client.fetch_open_issues()
    now    = datetime.utcnow()
    project_key = _project_key(client)

    fetched_ids: set[int] = set()
    created = 0
    updated = 0

    with session_scope() as session:
        for issue in issues:
            issue_id_raw = issue.get("id")
            if issue_id_raw is None:
                continue
            try:
                issue_id = int(issue_id_raw)
            except (TypeError, ValueError):
                continue

            fetched_ids.add(issue_id)

            summary     = (issue.get("summary") or f"Mantis-{issue_id}").strip()
            description = (issue.get("description") or "").strip()

            status    = issue.get("status") or {}
            state     = status.get("label") or status.get("name") or ""

            priority_obj = issue.get("priority") or {}
            priority_id  = priority_obj.get("id", 30) if isinstance(priority_obj, dict) else 30
            priority     = _PRIORITY_MAP.get(int(priority_id))

            issue_url = client.issue_url(issue_id)

            existing = session.query(Ticket).filter_by(ado_id=issue_id).first()
            if existing is None:
                session.add(Ticket(
                    ado_id        = issue_id,
                    project       = project_key,
                    title         = summary,
                    description   = description,
                    ado_state     = state,
                    ado_url       = issue_url,
                    priority      = priority,
                    last_synced_at = now,
                ))
                created += 1
            else:
                existing.project       = project_key
                existing.title         = summary or existing.title
                existing.description   = description or existing.description
                existing.ado_state     = state or existing.ado_state
                existing.ado_url       = issue_url
                existing.priority      = priority if priority is not None else existing.priority
                existing.last_synced_at = now
                updated += 1

        removed = _purge_orphans(session, project_key, fetched_ids)

    return {
        "project":   project_key,
        "fetched":   len(fetched_ids),
        "created":   created,
        "updated":   updated,
        "removed":   removed,
        "synced_at": now.isoformat(),
    }


def _purge_orphans(session, project_key: str, fetched_ids: set[int]) -> int:
    locals_ = session.query(Ticket).filter(Ticket.project == project_key).all()
    removed = 0
    for t in locals_:
        if t.ado_id in fetched_ids:
            continue
        has_exec = (
            session.query(AgentExecution.id)
            .filter(AgentExecution.ticket_id == t.id)
            .first() is not None
        )
        if has_exec:
            continue
        session.delete(t)
        removed += 1
    return removed


__all__ = [
    "sync_tickets",
    "MantisApiError",
    "MantisConfigError",
]
