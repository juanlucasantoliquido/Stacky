"""
context_freshness_monitor.py — Regenerar contexto si el repo cambió.

Verifica si el workspace tuvo cambios desde la última indexación antes de invocar
cada agente. Si hay cambios relevantes en los archivos del ticket, re-indexa.

Uso:
    from context_freshness_monitor import ContextFreshnessMonitor
    monitor = ContextFreshnessMonitor()
    monitor.ensure_fresh_context(ticket_folder, workspace_root)
"""

import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.context_freshness")


class ContextFreshnessMonitor:
    """Monitors workspace changes and triggers re-indexing when context is stale."""

    FRESHNESS_SECONDS = 300  # 5 minutes

    def __init__(self, indexer=None):
        self._indexer = indexer

    @property
    def indexer(self):
        if self._indexer is None:
            try:
                from codebase_indexer import CodebaseIndexer
                self._indexer = CodebaseIndexer()
            except ImportError:
                logger.warning("codebase_indexer not available")
        return self._indexer

    def is_stale(self, ticket_folder: str, workspace_root: str) -> bool:
        """
        Check if the context for a ticket needs regeneration.

        Returns True if:
        - No index exists
        - Index is older than FRESHNESS_SECONDS
        - Relevant files changed since last indexing
        """
        index_mtime = self._get_index_mtime(ticket_folder)
        if index_mtime is None:
            return True

        age = time.time() - index_mtime
        if age < self.FRESHNESS_SECONDS:
            return False

        # Check if any relevant files changed since indexing
        relevant_files = self._get_relevant_files(ticket_folder)
        for rel_path in relevant_files:
            full_path = Path(workspace_root) / rel_path
            if full_path.exists():
                try:
                    if full_path.stat().st_mtime > index_mtime:
                        logger.info("[Freshness] File changed since indexing: %s",
                                    rel_path)
                        return True
                except OSError:
                    continue

        return False

    def ensure_fresh_context(self, ticket_folder: str, workspace_root: str) -> bool:
        """
        Check freshness and re-index if stale.

        Returns True if re-indexing was triggered.
        """
        if not self.is_stale(ticket_folder, workspace_root):
            return False

        logger.info("[Freshness] Context stale — re-indexing...")

        relevant_files = self._get_relevant_files(ticket_folder)
        if self.indexer and relevant_files:
            try:
                if hasattr(self.indexer, "reindex_files"):
                    self.indexer.reindex_files(relevant_files, workspace_root)
                elif hasattr(self.indexer, "index_files"):
                    self.indexer.index_files(relevant_files, workspace_root)
                else:
                    logger.warning("Indexer has no reindex/index method")
                    return False

                # Update the freshness timestamp
                self._touch_index(ticket_folder)
                logger.info("[Freshness] Re-indexed %d files", len(relevant_files))
                return True
            except Exception as e:
                logger.error("[Freshness] Re-indexing failed: %s", e)

        return False

    def _get_index_mtime(self, ticket_folder: str) -> Optional[float]:
        """Get the modification time of the context index for this ticket."""
        folder = Path(ticket_folder)

        # Check for index markers
        markers = [
            folder / ".context_indexed",
            folder / "ARQUITECTURA_SOLUCION.md",  # fallback: use architecture file mtime
        ]
        for marker in markers:
            if marker.exists():
                try:
                    return marker.stat().st_mtime
                except OSError:
                    continue
        return None

    def _touch_index(self, ticket_folder: str):
        """Update the freshness timestamp marker."""
        marker = Path(ticket_folder) / ".context_indexed"
        try:
            marker.write_text(str(time.time()), encoding="utf-8")
        except Exception as e:
            logger.warning("Could not update freshness marker: %s", e)

    def _get_relevant_files(self, ticket_folder: str) -> list[str]:
        """
        Extract file paths mentioned in the ticket's architecture/analysis files.
        These are the files that matter for context freshness.
        """
        folder = Path(ticket_folder)
        files = set()

        scan_files = [
            "ARQUITECTURA_SOLUCION.md",
            "ANALISIS_TECNICO.md",
            "TAREAS_DESARROLLO.md",
        ]

        file_pattern = re.compile(
            r"\b([\w/\\]+\.(?:cs|aspx|aspx\.cs|sql|vb|config))\b",
            re.IGNORECASE
        )

        for fname in scan_files:
            fpath = folder / fname
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                for match in file_pattern.finditer(content):
                    files.add(match.group(1))
            except Exception:
                continue

        return list(files)
