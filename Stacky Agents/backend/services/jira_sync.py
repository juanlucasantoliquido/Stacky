"""
services/jira_sync.py — Sincroniza issues de Jira con la BD local.

Interfaz equivalente a ado_sync.sync_tickets() para que api/tickets.py
pueda usarlos indistintamente según el tracker del proyecto activo.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from db import session_scope
from models import AgentExecution, Ticket
from services.jira_client import JiraClient, JiraApiError, JiraConfigError, strip_jira_wiki_markup

logger = logging.getLogger("stacky_agents.jira_sync")


def _extract_description(fields: dict[str, Any], api_version: str) -> str:
    raw = fields.get("description") or ""
    if not raw:
        return ""
    if isinstance(raw, dict):
        # Atlassian Document Format (v3 Cloud)
        from services.jira_client import _adf_to_text
        return _adf_to_text(raw).strip()
    if isinstance(raw, str):
        if api_version == "3":
            return raw.strip()
        # v2 Server / DC — puede tener wiki markup
        return strip_jira_wiki_markup(raw)
    return str(raw).strip()


def _extract_priority(fields: dict[str, Any]) -> int | None:
    prio = fields.get("priority") or {}
    name = (prio.get("name") or "").lower() if isinstance(prio, dict) else ""
    mapping = {"blocker": 1, "critical": 1, "highest": 1, "high": 2, "medium": 3,
               "low": 4, "lowest": 5, "trivial": 5}
    return mapping.get(name)


def sync_tickets(client: JiraClient | None = None, tracker_config: dict | None = None) -> dict:
    """
    Sincroniza issues de Jira con la BD local.

    Si se provee tracker_config, se construye un JiraClient a partir de esa config.
    Si se provee client directamente, se usa ese.

    Retorna dict con las mismas claves que ado_sync.sync_tickets():
      { project, fetched, created, updated, removed, synced_at }
    """
    if client is None:
        if tracker_config is None:
            raise JiraConfigError("Se requiere un JiraClient o tracker_config.")
        client = JiraClient(
            url         = tracker_config.get("url", ""),
            project_key = tracker_config.get("project_key", ""),
            api_version = str(tracker_config.get("api_version", "3")),
            jql         = tracker_config.get("jql", ""),
            auth_file   = tracker_config.get("auth_file", "auth/jira_auth.json"),
            verify_ssl  = tracker_config.get("verify_ssl", True),
        )

    issues = client.fetch_open_issues()
    now    = datetime.utcnow()
    fetched_ids: set[int] = set()
    created  = 0
    updated  = 0

    with session_scope() as session:
        for issue in issues:
            fields    = issue.get("fields") or {}
            issue_key = issue.get("key", "")

            raw_id = issue.get("id")
            if raw_id is None:
                continue
            try:
                jira_id = int(raw_id)
            except (TypeError, ValueError):
                continue

            fetched_ids.add(jira_id)

            title       = (fields.get("summary") or f"JIRA-{jira_id}").strip()
            description = _extract_description(fields, client.api_version)
            priority    = _extract_priority(fields)
            status_obj  = fields.get("status") or {}
            state       = (
                status_obj.get("name")
                or status_obj.get("statusCategory", {}).get("name")
                or ""
            )
            issue_url   = client.issue_url(issue_key)

            existing = session.query(Ticket).filter_by(ado_id=jira_id).first()
            if existing is None:
                session.add(Ticket(
                    ado_id       = jira_id,
                    project      = client.project_key,
                    title        = title,
                    description  = description,
                    ado_state    = state,
                    ado_url      = issue_url,
                    priority     = priority,
                    last_synced_at = now,
                ))
                created += 1
            else:
                existing.project       = client.project_key
                existing.title         = title or existing.title
                existing.description   = description or existing.description
                existing.ado_state     = state or existing.ado_state
                existing.ado_url       = issue_url
                existing.priority      = priority if priority is not None else existing.priority
                existing.last_synced_at = now
                updated += 1

        removed = _purge_orphans(session, client.project_key, fetched_ids)

    return {
        "project":    client.project_key,
        "fetched":    len(fetched_ids),
        "created":    created,
        "updated":    updated,
        "removed":    removed,
        "synced_at":  now.isoformat(),
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
    "JiraApiError",
    "JiraConfigError",
]
