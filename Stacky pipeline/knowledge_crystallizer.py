"""
knowledge_crystallizer.py — Destilado semanal de sabiduría acumulada.

Cada viernes, lee todos los DEV_COMPLETADO.md y TESTER_COMPLETADO.md de la semana,
extrae patrones y soluciones frecuentes, y los destila en PROJECT_WISDOM.md.

Uso:
    from knowledge_crystallizer import KnowledgeCrystallizer
    crystallizer = KnowledgeCrystallizer()
    crystallizer.crystallize_week(workspace_root)
"""

import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.knowledge_crystallizer")

DATA_DIR = Path(__file__).parent / "data"
WISDOM_FILE = DATA_DIR / "PROJECT_WISDOM.md"


class KnowledgeCrystallizer:
    TOP_PATTERNS_COUNT = 20

    def __init__(self, projects_dir: Optional[str] = None):
        self._projects_dir = Path(projects_dir) if projects_dir else Path(__file__).parent / "projects"

    def crystallize_week(self, output_file: Optional[str] = None) -> str:
        output_path = Path(output_file) if output_file else WISDOM_FILE
        completed_folders = self._get_this_week_completed_tickets()

        if not completed_folders:
            logger.info("[Crystallizer] No completed tickets this week")
            return ""

        patterns = []
        for folder in completed_folders:
            patterns.extend(self._extract_from_dev_completado(folder))
            patterns.extend(self._extract_from_tester_completado(folder))

        if not patterns:
            logger.info("[Crystallizer] No patterns extracted")
            return ""

        ranked = self._rank_by_frequency(patterns)
        top = ranked[:self.TOP_PATTERNS_COUNT]

        wisdom = self._format_wisdom_document(top, len(completed_folders))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(wisdom, encoding="utf-8")

        logger.info("[Crystallizer] PROJECT_WISDOM.md: %d patterns from %d tickets",
                     len(top), len(completed_folders))
        return wisdom

    def get_wisdom_block(self) -> str:
        if WISDOM_FILE.exists():
            try:
                return WISDOM_FILE.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
        return ""

    def _get_this_week_completed_tickets(self) -> list[str]:
        folders = []
        now = datetime.now()
        week_ago = now - timedelta(days=7)

        if not self._projects_dir.exists():
            return []

        for project_dir in self._projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for state in ["completado", "en_proceso"]:
                tickets_dir = project_dir / "tickets" / state
                if not tickets_dir.exists():
                    continue
                for ticket_dir in tickets_dir.iterdir():
                    if not ticket_dir.is_dir():
                        continue
                    dev_done = ticket_dir / "DEV_COMPLETADO.md"
                    if dev_done.exists():
                        try:
                            mtime = dev_done.stat().st_mtime
                            if mtime > week_ago.timestamp():
                                folders.append(str(ticket_dir))
                        except OSError:
                            continue
        return folders

    def _extract_from_dev_completado(self, ticket_folder: str) -> list[dict]:
        path = Path(ticket_folder) / "DEV_COMPLETADO.md"
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        return self._extract_patterns(content, "dev")

    def _extract_from_tester_completado(self, ticket_folder: str) -> list[dict]:
        path = Path(ticket_folder) / "TESTER_COMPLETADO.md"
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        return self._extract_patterns(content, "qa")

    def _extract_patterns(self, content: str, source: str) -> list[dict]:
        patterns = []
        # Extract validation/check patterns
        for match in re.finditer(r"validaci[oó]n\s+(?:de\s+)?(.+?)[\.\n]",
                                  content, re.IGNORECASE):
            patterns.append({"category": "validación", "description": match.group(1).strip(),
                             "source": source})
        # Extract error fixes
        for match in re.finditer(r"(?:corregir?|fix|solucionar?)\s+(.+?)[\.\n]",
                                  content, re.IGNORECASE):
            patterns.append({"category": "fix", "description": match.group(1).strip(),
                             "source": source})
        # Extract null checks
        if re.search(r"null\s*(?:check|guard|validat)", content, re.IGNORECASE):
            patterns.append({"category": "null_guard", "description": "NULL check requerido",
                             "source": source})
        return patterns

    def _rank_by_frequency(self, patterns: list[dict]) -> list[dict]:
        counter = Counter()
        pattern_map = {}
        for p in patterns:
            key = f"{p['category']}:{p['description'][:50]}"
            counter[key] += 1
            pattern_map[key] = p

        ranked = []
        for key, count in counter.most_common():
            p = pattern_map[key].copy()
            p["occurrences"] = count
            ranked.append(p)
        return ranked

    def _format_wisdom_document(self, patterns: list[dict], ticket_count: int) -> str:
        lines = [
            "# PROJECT WISDOM — Conocimiento destilado (actualizado automáticamente)",
            f"*Última actualización: {datetime.now().strftime('%Y-%m-%d')}*",
            f"*Tickets procesados esta semana: {ticket_count}*",
            "",
            "## Patrones más frecuentes esta semana",
            "",
        ]
        for p in patterns:
            lines.append(
                f"- **{p['category']}** ({p.get('occurrences', 1)}x): "
                f"{p['description']}"
            )
        lines.append("")
        lines.append("---")
        lines.append("*Generado automáticamente por Stacky Knowledge Crystallizer.*")
        return "\n".join(lines)
