"""handoff_scorer.py — Q-02: Pre-flight Handoff Score PM → DEV."""

import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger("stacky.handoff_scorer")

ARCH_FILENAMES  = ("ARQUITECTURA_SOLUCION.md", "ARQUITECTURA.md")
TASKS_FILENAMES = ("TAREAS_DESARROLLO.md", "TAREAS.md")
QUERY_FILENAMES = ("QUERIES_ANALISIS.sql", "QUERIES_RESULTADOS.md", "QUERIES.md", "QUERIES.sql")
NOTES_FILENAMES = ("NOTAS_IMPLEMENTACION.md", "NOTAS.md")
ANALYSIS_FILENAMES = ("ANALISIS_TECNICO.md", "ANALISIS.md", "ANALISIS_COMPLETADO.md")

# Case-sensitive markers (code-style placeholders) — avoid matching Spanish "todo"
PLACEHOLDERS_CASE_SENSITIVE = ("TODO", "TBD", "XXX", "FIXME", "[PLACEHOLDER]")
# Case-insensitive markers (prose placeholders)
PLACEHOLDERS_CASE_INSENSITIVE = ("<completar>", "_A completar por PM_")

_CODE_PATH_PATTERNS = (
    re.compile(r"\b(?:trunk/)?(?:Batch|Negocio|Online|BusInchost|RSFac|RSBus|RSDalc)[/\\][\w./\\-]+", re.IGNORECASE),
    re.compile(r"\b[\w./\\-]+\.(?:cs|aspx|aspx\.cs|vb|sql|config|vbproj|csproj)\b", re.IGNORECASE),
)


@dataclass
class HandoffScore:
    score: int
    missing_signals: list = field(default_factory=list)
    recommendation: str = ""

    def __post_init__(self):
        if not self.recommendation:
            self.recommendation = "PM incompleto" if self.score < 60 else "PM aceptable"


class HandoffScorer:
    def score_pm_to_dev(self, ticket_folder: str) -> HandoffScore:
        checks = {
            "arquitectura_tiene_paths_codigo": self._has_code_paths(ticket_folder),
            "tareas_son_especificas":          self._tasks_are_specific(ticket_folder),
            "queries_tienen_resultados":       self._queries_have_results(ticket_folder),
            "notas_implementacion_no_vacias":  self._notes_not_empty(ticket_folder),
            "sin_placeholders":                self._no_placeholders(ticket_folder),
        }
        score = sum(20 for ok in checks.values() if ok)
        missing = [k for k, ok in checks.items() if not ok]
        logger.info("[Handoff] %s → score=%d, missing=%s", ticket_folder, score, missing)
        return HandoffScore(score=score, missing_signals=missing)

    # ── checks ──────────────────────────────────────────────────────────────

    def _has_code_paths(self, ticket_folder: str) -> bool:
        content = self._read_first_existing(ticket_folder, ARCH_FILENAMES)
        if not content:
            return False
        for pat in _CODE_PATH_PATTERNS:
            if pat.search(content):
                return True
        return False

    def _tasks_are_specific(self, ticket_folder: str) -> bool:
        content = self._read_first_existing(ticket_folder, TASKS_FILENAMES)
        if not content:
            return False
        items = re.findall(
            r"(?m)^\s*(?:[-*+]|\d+\.|\|\s*\d+\s*\||###\s+TAREA)\s+(.+)$",
            content,
        )
        meaningful = [it.strip() for it in items if len(it.strip()) > 30]
        return len(meaningful) >= 2

    def _queries_have_results(self, ticket_folder: str) -> bool:
        content = self._read_first_existing(ticket_folder, QUERY_FILENAMES)
        if not content:
            return False
        has_sql = (
            "```sql" in content.lower()
            or re.search(r"\b(select|insert|update|delete|create|alter)\b", content, re.IGNORECASE) is not None
        )
        has_results = (
            "|" in content
            or "rows affected" in content.lower()
            or "resultado" in content.lower()
            or re.search(r"^\s*--\s*\d+\s+rows", content, re.IGNORECASE | re.MULTILINE) is not None
        )
        return has_sql and has_results

    def _notes_not_empty(self, ticket_folder: str) -> bool:
        content = self._read_first_existing(ticket_folder, NOTES_FILENAMES)
        if not content:
            return False
        stripped = re.sub(r"\s+", "", content)
        return len(stripped) > 100

    def _no_placeholders(self, ticket_folder: str) -> bool:
        all_files = ARCH_FILENAMES + TASKS_FILENAMES + QUERY_FILENAMES + NOTES_FILENAMES + ANALYSIS_FILENAMES
        for name in all_files:
            path = os.path.join(ticket_folder, name)
            if not os.path.isfile(path):
                continue
            content = self._read_safe(path)
            if not content:
                continue
            for ph in PLACEHOLDERS_CASE_SENSITIVE:
                if re.search(r"\b" + re.escape(ph) + r"\b", content):
                    return False
            lower = content.lower()
            for ph in PLACEHOLDERS_CASE_INSENSITIVE:
                if ph.lower() in lower:
                    return False
        return True

    # ── helpers ─────────────────────────────────────────────────────────────

    def _read_first_existing(self, ticket_folder: str, names: tuple) -> str:
        for name in names:
            path = os.path.join(ticket_folder, name)
            if os.path.isfile(path):
                return self._read_safe(path)
        return ""

    def _read_safe(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except OSError as e:
            logger.warning("[Handoff] No pude leer %s: %s", path, e)
            return ""
