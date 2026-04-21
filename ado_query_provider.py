"""
ado_query_provider.py — WIQL avanzado para priorización inteligente de tickets.

Reemplaza el WIQL básico con queries especializados que priorizan:
1. Tickets en rework (ya tienen análisis hecho)
2. Tickets críticos/urgentes (P1, Severity 1)
3. Tickets normales por fecha
4. Tickets bloqueados (al final)

Uso:
    from ado_query_provider import ADOQueryProvider
    provider = ADOQueryProvider(ado_client)
    queue = provider.get_prioritized_queue()
"""

import logging
from typing import Optional

logger = logging.getLogger("stacky.ado_query")


WIQL_CRITICAL_FIRST = """
SELECT [System.Id], [System.Title], [System.State],
       [Microsoft.VSTS.Common.Priority], [Microsoft.VSTS.Common.Severity],
       [System.Tags], [System.ChangedDate]
FROM WorkItems
WHERE
    [System.TeamProject] = @project
    AND [System.AssignedTo] = @me
    AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
    AND (
        [Microsoft.VSTS.Common.Priority] = 1
        OR [System.Tags] CONTAINS 'urgente'
        OR [System.Tags] CONTAINS 'bloqueante'
    )
ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
"""

WIQL_REWORK_NEEDED = """
SELECT [System.Id], [System.Title], [System.Tags]
FROM WorkItems
WHERE
    [System.TeamProject] = @project
    AND [System.Tags] CONTAINS 'stacky:state_qa_rework'
ORDER BY [System.ChangedDate] ASC
"""

WIQL_STALE_IN_PROGRESS = """
SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
FROM WorkItems
WHERE
    [System.TeamProject] = @project
    AND [System.AssignedTo] = @me
    AND [System.State] = 'Active'
    AND [System.ChangedDate] < @today - 3
    AND [System.Tags] NOT CONTAINS 'stacky:state_'
ORDER BY [System.ChangedDate] ASC
"""

WIQL_BLOCKED_ITEMS = """
SELECT [System.Id], [System.Title], [System.State], [System.Tags]
FROM WorkItems
WHERE
    [System.TeamProject] = @project
    AND [System.Tags] CONTAINS 'stacky:state_bloqueado'
ORDER BY [System.ChangedDate] ASC
"""

WIQL_ALL_ASSIGNED = """
SELECT [System.Id], [System.Title], [System.State],
       [Microsoft.VSTS.Common.Priority], [System.Tags], [System.ChangedDate]
FROM WorkItems
WHERE
    [System.TeamProject] = @project
    AND [System.AssignedTo] = @me
    AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
"""


class ADOQueryProvider:
    """Provides prioritized ticket queues using WIQL queries."""

    def __init__(self, ado_client=None):
        self._ado_client = ado_client

    @property
    def ado_client(self):
        if self._ado_client is None:
            try:
                from ado_enricher import _get_ado_client
                self._ado_client = _get_ado_client()
            except Exception as e:
                logger.error("Cannot initialize ADO client: %s", e)
                raise
        return self._ado_client

    def get_prioritized_queue(self, max_items: int = 50) -> list[dict]:
        """
        Returns tickets ordered with intelligent logic:
        1. Tickets in rework (already have analysis, just need correction)
        2. Critical/urgent tickets (P1, Severity 1)
        3. Normal tickets by date
        4. Blocked tickets (at the end, to not waste slots)
        """
        reworks = self._run_wiql_safe(WIQL_REWORK_NEEDED)
        critical = self._run_wiql_safe(WIQL_CRITICAL_FIRST)
        normal = self._run_wiql_safe(WIQL_ALL_ASSIGNED)
        blocked = self._run_wiql_safe(WIQL_BLOCKED_ITEMS)

        # Deduplicate and combine in priority order
        seen = set()
        queue = []
        for wi in reworks + critical + normal:
            wi_id = wi.get("id")
            if wi_id and wi_id not in seen:
                seen.add(wi_id)
                queue.append(wi)
                if len(queue) >= max_items:
                    break

        # Blocked at the end
        for wi in blocked:
            wi_id = wi.get("id")
            if wi_id and wi_id not in seen:
                seen.add(wi_id)
                queue.append(wi)

        logger.info("Prioritized queue: %d items (rework=%d, critical=%d, normal=%d, blocked=%d)",
                     len(queue), len(reworks), len(critical), len(normal), len(blocked))
        return queue

    def get_rework_tickets(self) -> list[dict]:
        """Get only tickets that need rework."""
        return self._run_wiql_safe(WIQL_REWORK_NEEDED)

    def get_critical_tickets(self) -> list[dict]:
        """Get only critical/urgent tickets."""
        return self._run_wiql_safe(WIQL_CRITICAL_FIRST)

    def get_stale_tickets(self) -> list[dict]:
        """Get tickets that haven't been touched by Stacky in 3+ days."""
        return self._run_wiql_safe(WIQL_STALE_IN_PROGRESS)

    def get_blocked_tickets(self) -> list[dict]:
        """Get tickets that Stacky marked as blocked."""
        return self._run_wiql_safe(WIQL_BLOCKED_ITEMS)

    def _run_wiql_safe(self, wiql: str) -> list[dict]:
        """Run a WIQL query and return results, handling errors gracefully."""
        try:
            result = self.ado_client.query_wiql(wiql)
            work_items = result.get("workItems", [])
            return work_items
        except Exception as e:
            logger.error("WIQL query failed: %s", e)
            return []
