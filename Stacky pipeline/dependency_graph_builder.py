"""
dependency_graph_builder.py — Detectar tickets que se bloquean entre sí.

Construye un grafo de dependencias entre tickets basado en los archivos estimados
que cada uno va a modificar. Si dos tickets tocan el mismo archivo, el más viejo
debe completarse primero.

Uso:
    from dependency_graph_builder import TicketDependencyGraph
    graph = TicketDependencyGraph()
    order = graph.get_safe_execution_order(ticket_queue)
"""

import logging
import re
from collections import defaultdict
from typing import Optional

logger = logging.getLogger("stacky.dependency_graph")


class TicketDependencyGraph:
    """
    Builds a dependency graph between tickets and determines safe execution order.
    When multiple tickets touch the same file, they must be serialized.
    """

    def build_from_queue(self, ticket_queue: list[dict]) -> dict:
        """
        Build dependency graph from a ticket queue.

        Args:
            ticket_queue: List of dicts with at least 'id' and 'description' keys

        Returns:
            dict with 'edges' (list of (from, to, reason) tuples) and 'nodes' (set of ids)
        """
        file_to_tickets = defaultdict(list)
        nodes = set()

        for ticket in ticket_queue:
            ticket_id = str(ticket.get("id", ""))
            description = ticket.get("description", "")
            nodes.add(ticket_id)

            estimated_files = self._estimate_affected_files(description)
            for f in estimated_files:
                file_to_tickets[f].append(ticket_id)

        edges = []
        # Tickets that touch the same file: older precedes newer (by queue order)
        for f, tickets in file_to_tickets.items():
            if len(tickets) > 1:
                for i in range(len(tickets) - 1):
                    edges.append((tickets[i], tickets[i + 1], f"shared file: {f}"))

        logger.info("Dependency graph: %d nodes, %d edges, %d shared files",
                     len(nodes), len(edges),
                     sum(1 for t in file_to_tickets.values() if len(t) > 1))

        return {"edges": edges, "nodes": nodes}

    def get_safe_execution_order(self, ticket_queue: list[dict]) -> list[str]:
        """
        Return topologically sorted ticket IDs (blockers first).

        If cycles are detected, falls back to original queue order.
        """
        graph = self.build_from_queue(ticket_queue)
        edges = graph["edges"]
        nodes = graph["nodes"]

        if not edges:
            return [str(t.get("id", "")) for t in ticket_queue]

        # Build adjacency list for topological sort
        adj = defaultdict(list)
        in_degree = defaultdict(int)
        for node in nodes:
            in_degree[node] = 0

        for src, dst, reason in edges:
            adj[src].append(dst)
            in_degree[dst] = in_degree.get(dst, 0) + 1

        # Kahn's algorithm for topological sort
        queue = [n for n in nodes if in_degree[n] == 0]
        result = []

        while queue:
            # Sort by original position for determinism
            queue.sort(key=lambda x: self._get_queue_position(x, ticket_queue))
            node = queue.pop(0)
            result.append(node)

            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(nodes):
            # Cycle detected
            missing = nodes - set(result)
            logger.warning(
                "Cycle detected in dependency graph. Affected tickets: %s. "
                "Using original order for cyclic nodes.",
                missing
            )
            # Append cyclic nodes in original order
            for t in ticket_queue:
                tid = str(t.get("id", ""))
                if tid in missing and tid not in result:
                    result.append(tid)

        return result

    def get_blocking_info(self, ticket_queue: list[dict]) -> dict:
        """
        Get a map of ticket_id → list of tickets that block it.

        Returns:
            {ticket_id: [{"blocker": id, "reason": str}, ...]}
        """
        graph = self.build_from_queue(ticket_queue)
        blockers = defaultdict(list)

        for src, dst, reason in graph["edges"]:
            blockers[dst].append({"blocker": src, "reason": reason})

        return dict(blockers)

    def _estimate_affected_files(self, description: str) -> list[str]:
        """
        Estimate which files a ticket will modify based on its description.
        Extracts file path references from the text.
        """
        if not description:
            return []

        pattern = re.compile(
            r"\b([\w/\\]+\.(?:cs|aspx|aspx\.cs|sql|vb|config|js))\b",
            re.IGNORECASE
        )
        files = list(set(pattern.findall(description)))
        return files

    def _get_queue_position(self, ticket_id: str, queue: list[dict]) -> int:
        """Get the position of a ticket in the original queue."""
        for i, t in enumerate(queue):
            if str(t.get("id", "")) == ticket_id:
                return i
        return 999
