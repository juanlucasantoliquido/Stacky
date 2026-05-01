"""
issue_provider — Abstracción de proveedor de tickets/issues para Stacky.

Desacopla Stacky del backend concreto (Azure DevOps, ...).
El daemon y el dashboard solo ven la interfaz `IssueProvider`.

Uso típico:

    from issue_provider import get_provider
    provider = get_provider(project_name="RSPACIFICO")
    tickets  = provider.fetch_open_tickets()
    provider.add_comment(ticket_id, "Pipeline completado", kind="resolution")

Sync local (escribe el layout de archivos que consume Stacky):

    from issue_provider import sync_tickets
    sync_tickets(project_name="RSPACIFICO")
"""

from .base import IssueProvider, ProviderError, TicketNotFound
from .types import (
    Ticket,
    TicketDetail,
    TicketComment,
    TicketAttachment,
    CommentKind,
)
from .factory import get_provider, load_tracker_config
from .sync import sync_tickets

__all__ = [
    "IssueProvider",
    "ProviderError",
    "TicketNotFound",
    "Ticket",
    "TicketDetail",
    "TicketComment",
    "TicketAttachment",
    "CommentKind",
    "get_provider",
    "load_tracker_config",
    "sync_tickets",
]
