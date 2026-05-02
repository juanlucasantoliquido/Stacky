"""
ado_manager — Facade único para operaciones ADO.

Reemplaza llamadas directas a mcp_azure-devops_*. Provee validación Pydantic,
dedupe por hash SHA256, idempotencia y log de acciones via T15.

Uso:
    from ado_manager import AdoManager

    mgr = AdoManager(org="UbimiaPacifico", project="Strategist_Pacifico")
    ctx = mgr.get_ticket_context(1234)
    result = mgr.publish_comment(1234, "## Análisis...")
"""
from .manager import AdoManager
from .operations import (
    TicketContext,
    PublishResult,
    UpdateStateResult,
    CreateTicketResult,
    SearchResult,
)

__all__ = [
    "AdoManager",
    "TicketContext",
    "PublishResult",
    "UpdateStateResult",
    "CreateTicketResult",
    "SearchResult",
]
