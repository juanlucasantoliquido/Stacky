"""
regression_sweeper.py — Sweep post-resolución en módulos vecinos.

Cuando un ticket completa, analiza archivos vecinos para detectar si el mismo
patrón de bug existe en otros archivos del mismo módulo.

Uso:
    from regression_sweeper import RegressionSweeper
    sweeper = RegressionSweeper()
    sweeper.schedule_sweep(ticket_folder, files_modified)
"""

import logging
import re
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.regression_sweeper")


class RegressionSweeper:
    MAX_NEIGHBORS = 5
    MAX_PITFALLS_PER_FILE = 3

    def __init__(self, codebase_indexer=None, pitfall_registry=None, notifier=None):
        self._indexer = codebase_indexer
        self._pitfall_registry = pitfall_registry
        self._notifier = notifier

    def schedule_sweep(self, ticket_folder: str, files_modified: list[str]):
        thread = threading.Thread(
            target=self._run_sweep,
            args=(ticket_folder, files_modified),
            daemon=True,
            name="regression-sweep"
        )
        thread.start()
        logger.info("[Sweep] Scheduled for %d files", len(files_modified))

    def sweep_sync(self, ticket_folder: str, files_modified: list[str]) -> list[dict]:
        return self._run_sweep(ticket_folder, files_modified)

    def _run_sweep(self, ticket_folder: str, files_modified: list[str]) -> list[dict]:
        findings = []
        for f in files_modified:
            neighbors = self._get_similar_files(f)
            pitfalls = self._get_known_pitfalls(f)

            for neighbor in neighbors[:self.MAX_NEIGHBORS]:
                neighbor_content = self._read_file_safe(neighbor)
                if not neighbor_content:
                    continue

                for pitfall in pitfalls[:self.MAX_PITFALLS_PER_FILE]:
                    if self._pattern_exists_in(pitfall, neighbor_content):
                        finding = {
                            "source_file": f,
                            "neighbor_file": neighbor,
                            "pitfall": pitfall,
                            "severity": "warning",
                        }
                        findings.append(finding)
                        logger.warning(
                            "[Sweep] Pattern from '%s' found in '%s': %s",
                            f, neighbor, pitfall.get("description", "")[:80]
                        )

        if findings and self._notifier:
            try:
                self._notifier.alert(
                    f"SWEEP POST-RESOLUCIÓN: {len(findings)} patrones problemáticos "
                    f"encontrados en archivos vecinos. Revisar dashboard."
                )
            except Exception:
                pass

        return findings

    def _get_similar_files(self, file_path: str) -> list[str]:
        if self._indexer and hasattr(self._indexer, "get_similar_files"):
            try:
                return self._indexer.get_similar_files(file_path, top_k=self.MAX_NEIGHBORS)
            except Exception:
                pass
        # Fallback: find files in same directory with same extension
        p = Path(file_path)
        if p.parent.exists():
            ext = p.suffix
            return [
                str(f) for f in p.parent.glob(f"*{ext}")
                if f.name != p.name
            ][:self.MAX_NEIGHBORS]
        return []

    def _get_known_pitfalls(self, file_path: str) -> list[dict]:
        if self._pitfall_registry:
            try:
                if hasattr(self._pitfall_registry, "get_pitfalls_for_file"):
                    return self._pitfall_registry.get_pitfalls_for_file(file_path)
                warnings = self._pitfall_registry.get_warnings_for_files([file_path])
                return [{"description": w, "pattern": ""} for w in warnings]
            except Exception:
                pass
        return []

    def _pattern_exists_in(self, pitfall: dict, content: str) -> bool:
        pattern = pitfall.get("pattern", "")
        desc = pitfall.get("description", "")
        if pattern:
            try:
                return bool(re.search(pattern, content, re.IGNORECASE))
            except re.error:
                pass
        # Fallback: check for key phrases from the description
        keywords = [w for w in desc.lower().split() if len(w) > 4][:3]
        return all(k in content.lower() for k in keywords) if keywords else False

    def _read_file_safe(self, path: str) -> str:
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
