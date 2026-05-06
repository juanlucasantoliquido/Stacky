"""
Sincroniza work items reales de Azure DevOps con la BD local.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Iterable

from db import session_scope
from models import AgentExecution, ExecutionLog, PackRun, Ticket
from services.ado_client import AdoClient, AdoApiError, AdoConfigError

logger = logging.getLogger("stacky_agents.ado_sync")


class _HtmlStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = _HtmlStripper()
    try:
        parser.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    text = "".join(parser.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def sync_tickets(client: AdoClient | None = None) -> dict:
    """Pulls work items from ADO and upserts into the local DB.

    - Tickets cuyo ado_id no esté en la respuesta y no tengan ejecuciones se eliminan.
    - Tickets con ejecuciones nunca se borran (puede que estén cerrados en ADO).
    """
    client = client or AdoClient()
    items = client.fetch_open_work_items()
    now = datetime.utcnow()
    fetched_ids: set[int] = set()
    created = 0
    updated = 0

    with session_scope() as session:
        for wi in items:
            fields = wi.get("fields") or {}
            ado_id = wi.get("id")
            if ado_id is None:
                continue
            ado_id = int(ado_id)
            fetched_ids.add(ado_id)

            description = _html_to_text(str(fields.get("System.Description") or ""))
            priority = fields.get("Microsoft.VSTS.Common.Priority")
            try:
                priority_int = int(priority) if priority is not None else None
            except (TypeError, ValueError):
                priority_int = None
            work_item_type = str(fields.get("System.WorkItemType") or "")
            parent_ado_id_raw = fields.get("System.Parent")
            try:
                parent_ado_id = int(parent_ado_id_raw) if parent_ado_id_raw else None
            except (TypeError, ValueError):
                parent_ado_id = None

            existing = session.query(Ticket).filter_by(ado_id=ado_id).first()
            if existing is None:
                session.add(
                    Ticket(
                        ado_id=ado_id,
                        project=client.project,
                        title=str(fields.get("System.Title") or f"WI-{ado_id}"),
                        description=description,
                        ado_state=str(fields.get("System.State") or ""),
                        ado_url=client.work_item_url(ado_id),
                        priority=priority_int,
                        work_item_type=work_item_type or None,
                        parent_ado_id=parent_ado_id,
                        last_synced_at=now,
                    )
                )
                created += 1
            else:
                existing.project = client.project
                existing.title = str(fields.get("System.Title") or existing.title)
                existing.description = description or existing.description
                existing.ado_state = str(fields.get("System.State") or existing.ado_state)
                existing.ado_url = client.work_item_url(ado_id)
                existing.priority = priority_int if priority_int is not None else existing.priority
                existing.work_item_type = work_item_type or existing.work_item_type
                existing.parent_ado_id = parent_ado_id if parent_ado_id is not None else existing.parent_ado_id
                existing.last_synced_at = now
                updated += 1

        removed = _purge_orphans(session, client.project, fetched_ids)

    return {
        "project": client.project,
        "fetched": len(fetched_ids),
        "created": created,
        "updated": updated,
        "removed": removed,
        "synced_at": now.isoformat(),
    }


def _purge_orphans(session, project: str, fetched_ids: Iterable[int]) -> int:
    fetched = set(fetched_ids)
    locals_ = (
        session.query(Ticket)
        .filter(Ticket.project == project)
        .all()
    )
    removed = 0
    for t in locals_:
        if t.ado_id in fetched:
            continue
        # El ticket ya no existe en ADO → borrar local.
        # Hay que eliminar los registros dependientes primero para evitar
        # violaciones de FK (AgentExecution.ticket_id es NOT NULL).
        exec_ids = [
            row[0] for row in
            session.query(AgentExecution.id)
            .filter(AgentExecution.ticket_id == t.id)
            .all()
        ]
        if exec_ids:
            # ExecutionLog tiene FK a agent_executions con ON DELETE CASCADE,
            # pero SQLite puede no tenerlo activo — lo eliminamos explícitamente.
            session.query(ExecutionLog).filter(
                ExecutionLog.execution_id.in_(exec_ids)
            ).delete(synchronize_session=False)
            session.query(AgentExecution).filter(
                AgentExecution.ticket_id == t.id
            ).delete(synchronize_session=False)
        session.query(PackRun).filter(
            PackRun.ticket_id == t.id
        ).delete(synchronize_session=False)
        session.delete(t)
        removed += 1
    return removed


def purge_non_project_tickets(keep_project: str) -> int:
    """Borra tickets locales de proyectos distintos al configurado y sin ejecuciones.

    Sirve para limpiar restos del seed mock (__sandbox__) sin tocar tickets reales.
    """
    removed = 0
    with session_scope() as session:
        rows = session.query(Ticket).filter(Ticket.project != keep_project).all()
        for t in rows:
            has_exec = (
                session.query(AgentExecution.id)
                .filter(AgentExecution.ticket_id == t.id)
                .first()
                is not None
            )
            if has_exec:
                continue
            session.delete(t)
            removed += 1
    return removed


def get_last_sync_at() -> datetime | None:
    with session_scope() as session:
        row = (
            session.query(Ticket.last_synced_at)
            .filter(Ticket.last_synced_at.isnot(None))
            .order_by(Ticket.last_synced_at.desc())
            .first()
        )
        return row[0] if row else None


__all__ = [
    "sync_tickets",
    "purge_non_project_tickets",
    "get_last_sync_at",
    "AdoApiError",
    "AdoConfigError",
]
