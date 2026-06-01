"""
Sincroniza work items reales de Azure DevOps con la BD local.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Iterable

from sqlalchemy import and_, or_

from db import session_scope
from models import AgentExecution, ExecutionLog, PackRun, Ticket, TicketStateHistory
from services.ado_client import AdoClient, AdoApiError, AdoConfigError
from services.project_context import build_ado_client, resolve_project_context

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


def _legacy_ticket_match(stacky_project_name: str | None, tracker_project: str):
    clauses = [Ticket.project == tracker_project]
    if stacky_project_name:
        clauses.append(Ticket.stacky_project_name == stacky_project_name)
        return or_(
            and_(Ticket.stacky_project_name == stacky_project_name),
            and_(Ticket.stacky_project_name.is_(None), Ticket.project == tracker_project),
        )
    return clauses[0]


def _client_project_metadata(client: AdoClient) -> tuple[str | None, str]:
    tracker_project = client.project
    stacky_project_name = getattr(client, "stacky_project_name", None)
    if stacky_project_name:
        return stacky_project_name, tracker_project
    ctx = resolve_project_context(tracker_project=tracker_project)
    return (ctx.stacky_project_name if ctx else None), tracker_project


def sync_tickets(client: AdoClient | None = None, project_name: str | None = None) -> dict:
    """Pulls work items from ADO and upserts into the local DB.

    - Tickets cuyo ado_id no esté en la respuesta y no tengan ejecuciones se eliminan.
    - Tickets con ejecuciones nunca se borran (puede que estén cerrados en ADO).
    """
    client = client or (
        build_ado_client(project_name=project_name)
        if project_name or resolve_project_context()
        else AdoClient()
    )
    items = client.fetch_open_work_items()
    now = datetime.utcnow()
    fetched_ids: set[int] = set()
    created = 0
    updated = 0
    stacky_project_name, tracker_project = _client_project_metadata(client)
    tracker_type = getattr(client, "tracker_type", None) or "azure_devops"

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

            # P6: extraer uniqueName del asignado (System.AssignedTo puede ser dict u objeto)
            assigned_raw = fields.get("System.AssignedTo") or {}
            if isinstance(assigned_raw, dict):
                assigned_to_ado = assigned_raw.get("uniqueName") or assigned_raw.get("displayName") or None
            else:
                assigned_to_ado = str(assigned_raw).strip() if assigned_raw else None
            if assigned_to_ado == "":
                assigned_to_ado = None

            new_state = str(fields.get("System.State") or "")

            existing = (
                session.query(Ticket)
                .filter(Ticket.external_id == ado_id)
                .filter(Ticket.tracker_type == tracker_type)
                .filter(_legacy_ticket_match(stacky_project_name, tracker_project))
                .first()
            )
            if existing is None:
                existing = (
                    session.query(Ticket)
                    .filter(Ticket.ado_id == ado_id)
                    .filter(_legacy_ticket_match(stacky_project_name, tracker_project))
                    .first()
                )
            if existing is None:
                new_ticket = Ticket(
                    ado_id=ado_id,
                    external_id=ado_id,
                    project=tracker_project,
                    stacky_project_name=stacky_project_name,
                    tracker_type=tracker_type,
                    title=str(fields.get("System.Title") or f"WI-{ado_id}"),
                    description=description,
                    ado_state=new_state,
                    ado_url=client.work_item_url(ado_id),
                    priority=priority_int,
                    work_item_type=work_item_type or None,
                    parent_ado_id=parent_ado_id,
                    last_synced_at=now,
                    assigned_to_ado=assigned_to_ado,
                )
                session.add(new_ticket)
                session.flush()  # Necesario para obtener new_ticket.id antes del commit
                # Registrar primera aparicion en historial de estados
                if new_state:
                    session.add(TicketStateHistory(
                        ticket_id=new_ticket.id,
                        ado_id=ado_id,
                        stacky_project_name=stacky_project_name,
                        old_state=None,
                        new_state=new_state,
                        assigned_to_ado=assigned_to_ado,
                        recorded_at=now,
                    ))
                created += 1
            else:
                prev_state = existing.ado_state
                existing.ado_id = ado_id
                existing.external_id = ado_id
                existing.project = tracker_project
                existing.stacky_project_name = stacky_project_name
                existing.tracker_type = tracker_type
                existing.title = str(fields.get("System.Title") or existing.title)
                existing.description = description or existing.description
                existing.ado_state = new_state or existing.ado_state
                existing.ado_url = client.work_item_url(ado_id)
                existing.priority = priority_int if priority_int is not None else existing.priority
                existing.work_item_type = work_item_type or existing.work_item_type
                existing.parent_ado_id = parent_ado_id if parent_ado_id is not None else existing.parent_ado_id
                existing.last_synced_at = now
                existing.assigned_to_ado = assigned_to_ado
                # P6-Panel: registrar transicion de estado si cambio
                if new_state and new_state != prev_state:
                    session.add(TicketStateHistory(
                        ticket_id=existing.id,
                        ado_id=ado_id,
                        stacky_project_name=stacky_project_name,
                        old_state=prev_state,
                        new_state=new_state,
                        assigned_to_ado=assigned_to_ado,
                        recorded_at=now,
                    ))
                updated += 1

        removed = _purge_orphans(session, tracker_project, fetched_ids)

    return {
        "project": tracker_project,
        "stacky_project_name": stacky_project_name,
        "fetched": len(fetched_ids),
        "created": created,
        "updated": updated,
        "removed": removed,
        "synced_at": now.isoformat(),
    }


def upsert_single_work_item(client: AdoClient, ado_id: int) -> dict | None:
    """Trae un work item puntual de ADO y lo upsertea en `tickets` de inmediato.

    Fase 2 plan creacion-tareas-comentarios-100-efectiva (§4 / §7 ado_sync):
    "Tras crear Task, upsert inmediato en tickets". Sin esto, una Task recien
    creada por Stacky no aparece en la UI local hasta el proximo sync general
    (que es incierto y puede no traerla si el WIQL no la incluye).

    No depende del sync masivo: hace un GET puntual del work item y mapea los
    mismos campos que sync_tickets. Idempotente: si el ticket ya existe, lo
    actualiza. Devuelve el dict del ticket upserteado o None si ADO falla.
    """
    try:
        wi = client.get_work_item(
            int(ado_id),
            fields=[
                "System.Id", "System.Title", "System.State", "System.Description",
                "System.WorkItemType", "System.Parent", "System.AssignedTo",
                "Microsoft.VSTS.Common.Priority",
            ],
        )
    except Exception as exc:  # noqa: BLE001 — el upsert es best-effort
        logger.warning("upsert_single_work_item(%s) — GET falló: %s", ado_id, exc)
        return None

    fields = wi.get("fields") or {}
    now = datetime.utcnow()
    stacky_project_name, tracker_project = _client_project_metadata(client)
    tracker_type = getattr(client, "tracker_type", None) or "azure_devops"

    description = _html_to_text(str(fields.get("System.Description") or ""))
    priority = fields.get("Microsoft.VSTS.Common.Priority")
    try:
        priority_int = int(priority) if priority is not None else None
    except (TypeError, ValueError):
        priority_int = None
    work_item_type = str(fields.get("System.WorkItemType") or "")
    parent_raw = fields.get("System.Parent")
    try:
        parent_ado_id = int(parent_raw) if parent_raw else None
    except (TypeError, ValueError):
        parent_ado_id = None
    assigned_raw = fields.get("System.AssignedTo") or {}
    if isinstance(assigned_raw, dict):
        assigned_to_ado = assigned_raw.get("uniqueName") or assigned_raw.get("displayName") or None
    else:
        assigned_to_ado = str(assigned_raw).strip() or None
    new_state = str(fields.get("System.State") or "")

    with session_scope() as session:
        existing = (
            session.query(Ticket)
            .filter(Ticket.external_id == int(ado_id))
            .filter(Ticket.tracker_type == tracker_type)
            .filter(_legacy_ticket_match(stacky_project_name, tracker_project))
            .first()
        )
        if existing is None:
            existing = (
                session.query(Ticket)
                .filter(Ticket.ado_id == int(ado_id))
                .filter(_legacy_ticket_match(stacky_project_name, tracker_project))
                .first()
            )
        if existing is None:
            ticket = Ticket(
                ado_id=int(ado_id),
                external_id=int(ado_id),
                project=tracker_project,
                stacky_project_name=stacky_project_name,
                tracker_type=tracker_type,
                title=str(fields.get("System.Title") or f"WI-{ado_id}"),
                description=description,
                ado_state=new_state,
                ado_url=client.work_item_url(int(ado_id)),
                priority=priority_int,
                work_item_type=work_item_type or None,
                parent_ado_id=parent_ado_id,
                last_synced_at=now,
                assigned_to_ado=assigned_to_ado,
            )
            session.add(ticket)
            session.flush()
            if new_state:
                session.add(TicketStateHistory(
                    ticket_id=ticket.id,
                    ado_id=int(ado_id),
                    stacky_project_name=stacky_project_name,
                    old_state=None,
                    new_state=new_state,
                    assigned_to_ado=assigned_to_ado,
                    recorded_at=now,
                ))
            result = ticket.to_dict()
        else:
            existing.title = str(fields.get("System.Title") or existing.title)
            existing.description = description or existing.description
            existing.ado_state = new_state or existing.ado_state
            existing.ado_url = client.work_item_url(int(ado_id))
            existing.priority = priority_int if priority_int is not None else existing.priority
            existing.work_item_type = work_item_type or existing.work_item_type
            existing.parent_ado_id = parent_ado_id if parent_ado_id is not None else existing.parent_ado_id
            existing.last_synced_at = now
            if assigned_to_ado is not None:
                existing.assigned_to_ado = assigned_to_ado
            result = existing.to_dict()
    logger.info("upsert_single_work_item(%s): ticket upserteado en BD local", ado_id)
    return result


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
    Preserva siempre el proyecto __demo__ (C2 PLAN_ADOPCION_DEVS): es un sandbox
    intencional que NO debe ser barrido por el sync ADO.
    """
    removed = 0
    with session_scope() as session:
        rows = (
            session.query(Ticket)
            .filter(Ticket.project != keep_project)
            .filter(Ticket.project != "__demo__")
            .all()
        )
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


def get_last_sync_at(project_name: str | None = None) -> datetime | None:
    ctx = resolve_project_context(project_name=project_name) if project_name or resolve_project_context() else None
    with session_scope() as session:
        q = session.query(Ticket.last_synced_at).filter(Ticket.last_synced_at.isnot(None))
        if ctx:
            q = q.filter(_legacy_ticket_match(ctx.stacky_project_name, ctx.tracker_project))
        row = q.order_by(Ticket.last_synced_at.desc()).first()
        return row[0] if row else None


__all__ = [
    "sync_tickets",
    "purge_non_project_tickets",
    "get_last_sync_at",
    "AdoApiError",
    "AdoConfigError",
]
