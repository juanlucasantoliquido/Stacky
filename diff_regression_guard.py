"""
diff_regression_guard.py — Detectar si DEV revirtió un fix de rework.

Antes de invocar QA en rondas 2+, compara el DEV_COMPLETADO.md actual con el anterior
y alerta si desaparecieron referencias a archivos que antes estaban.

Uso:
    from diff_regression_guard import DiffRegressionGuard
    guard = DiffRegressionGuard()
    regressions = guard.check_rework(ticket_folder, rework_round=2)
"""

import re
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger("stacky.diff_regression_guard")


@dataclass
class RegressionAlert:
    """A detected potential regression between rework rounds."""
    file_path: str
    alert_type: str  # "file_disappeared", "method_disappeared", "content_shrunk"
    description: str
    round_before: int
    round_after: int


class DiffRegressionGuard:
    """
    Compares DEV output between rework rounds to detect potential regressions.
    """

    def check_rework(
        self,
        ticket_folder: str,
        rework_round: int,
    ) -> list[str]:
        """
        Compare DEV_COMPLETADO.md between consecutive rework rounds.
        Returns list of regression warnings (empty if no regressions detected).
        """
        if rework_round < 2:
            return []

        current = self._load_dev_completado(ticket_folder, rework_round)
        previous = self._load_dev_completado(ticket_folder, rework_round - 1)

        if not previous:
            logger.debug("No previous DEV output found for round %d", rework_round - 1)
            return []

        if not current:
            return [
                f"⚠️ REGRESIÓN: No se encontró DEV_COMPLETADO para round {rework_round}. "
                f"¿Se ejecutó el rework?"
            ]

        regressions = []

        # Check for files that disappeared
        prev_files = self._extract_file_references(previous)
        curr_files = self._extract_file_references(current)
        disappeared = prev_files - curr_files

        for f in disappeared:
            regressions.append(
                f"⚠️ POSIBLE REGRESIÓN: '{f}' fue modificado en round "
                f"{rework_round - 1} pero no aparece en round {rework_round}. "
                f"¿Se revirtió el fix?"
            )

        # Check for methods that disappeared
        prev_methods = self._extract_method_references(previous)
        curr_methods = self._extract_method_references(current)
        lost_methods = prev_methods - curr_methods

        for m in lost_methods:
            regressions.append(
                f"⚠️ POSIBLE REGRESIÓN: El método '{m}' era referenciado en round "
                f"{rework_round - 1} pero ya no aparece en round {rework_round}."
            )

        # Check for significant content reduction
        prev_len = len(previous.splitlines())
        curr_len = len(current.splitlines())
        if prev_len > 10 and curr_len < prev_len * 0.5:
            regressions.append(
                f"⚠️ POSIBLE REGRESIÓN: DEV_COMPLETADO se redujo significativamente "
                f"({prev_len} → {curr_len} líneas). Verificar que no se perdió contenido."
            )

        if regressions:
            logger.warning("Detected %d potential regressions in round %d",
                           len(regressions), rework_round)

        return regressions

    def build_qa_injection_block(self, regressions: list[str]) -> str:
        """Build a markdown block for injection into the QA prompt."""
        if not regressions:
            return ""

        lines = [
            "## ⚠️ Alertas de regresión detectadas (Diff Regression Guard)",
            "",
            "Las siguientes posibles regresiones fueron detectadas entre rounds "
            "de rework. **Verificá específicamente cada una:**",
            "",
        ]
        for r in regressions:
            lines.append(f"- {r}")

        lines.append("")
        return "\n".join(lines)

    def _load_dev_completado(
        self,
        ticket_folder: str,
        rework_round: int,
    ) -> str:
        """
        Load DEV_COMPLETADO for a specific rework round.

        Naming convention:
        - Round 1 (original): DEV_COMPLETADO.md
        - Round 2+: DEV_COMPLETADO_round_N.md or latest DEV_COMPLETADO.md
        """
        folder = Path(ticket_folder)

        # Try round-specific file first
        if rework_round >= 2:
            round_file = folder / f"DEV_COMPLETADO_round_{rework_round}.md"
            if round_file.exists():
                return round_file.read_text(encoding="utf-8", errors="replace")

        # Fallback to main file for round 1 or if round-specific doesn't exist
        if rework_round == 1:
            main_file = folder / "DEV_COMPLETADO.md"
            if main_file.exists():
                return main_file.read_text(encoding="utf-8", errors="replace")

        # Check alternative naming: DEV_COMPLETADO_v2.md, etc.
        alt_patterns = [
            f"DEV_COMPLETADO_v{rework_round}.md",
            f"DEV_COMPLETADO_{rework_round}.md",
        ]
        for alt in alt_patterns:
            alt_file = folder / alt
            if alt_file.exists():
                return alt_file.read_text(encoding="utf-8", errors="replace")

        return ""

    def _extract_file_references(self, content: str) -> set[str]:
        """Extract file path references from DEV_COMPLETADO content."""
        pattern = re.compile(
            r"\b[\w/\\]+\.(?:cs|aspx|aspx\.cs|sql|vb|config|js|css)\b",
            re.IGNORECASE
        )
        return set(pattern.findall(content))

    def _extract_method_references(self, content: str) -> set[str]:
        """Extract method name references from DEV_COMPLETADO content."""
        patterns = [
            re.compile(r"\b(\w+)\s*\(", re.MULTILINE),  # method()
            re.compile(r"método\s+[`']?(\w+)[`']?", re.IGNORECASE),  # método X
        ]
        methods = set()
        for pattern in patterns:
            for match in pattern.finditer(content):
                name = match.group(1)
                # Filter common words that are not method names
                if len(name) > 3 and name not in _COMMON_WORDS:
                    methods.add(name)
        return methods


_COMMON_WORDS = {
    "void", "string", "int", "bool", "null", "true", "false",
    "this", "return", "class", "public", "private", "static",
    "foreach", "while", "catch", "throw", "finally",
    "Verificar", "Modificar", "Agregar", "Eliminar",
}
