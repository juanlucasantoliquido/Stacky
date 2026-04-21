"""
intelligent_retry.py — Reintentos con estrategia escalada.

Cada reintento usa una estrategia diferente:
- Retry 1: prompt original + contexto del fallo anterior
- Retry 2: prompt reducido al mínimo (sin contexto extra)
- Retry 3: split del ticket en subtareas más simples

Uso:
    from intelligent_retry import IntelligentRetryStrategy
    strategy = IntelligentRetryStrategy()
    new_prompt = strategy.build_retry_prompt(original, attempt=2, failure_reason, folder)
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.intelligent_retry")


class IntelligentRetryStrategy:
    """Builds increasingly different retry prompts for failed agent invocations."""

    STRATEGIES = [
        "augment_with_failure_reason",
        "minimal_prompt",
        "split_subtasks",
    ]

    def get_strategy_name(self, attempt: int) -> str:
        """Get the strategy name for a given retry attempt (1-based)."""
        idx = min(attempt - 1, len(self.STRATEGIES) - 1)
        return self.STRATEGIES[idx]

    def build_retry_prompt(
        self,
        original_prompt: str,
        attempt: int,
        failure_reason: str,
        ticket_folder: str,
        stage: str = "dev",
    ) -> str:
        """
        Build a retry prompt using the strategy appropriate for the attempt number.

        Args:
            original_prompt: The original prompt that failed
            attempt: Retry attempt number (1-based)
            failure_reason: Description of why the previous attempt failed
            ticket_folder: Path to the ticket folder
            stage: Pipeline stage (pm, dev, tester)

        Returns:
            Modified prompt for the retry attempt
        """
        strategy = self.get_strategy_name(attempt)
        logger.info("[Retry] Attempt %d, strategy: %s, reason: %s",
                     attempt, strategy, failure_reason[:100])

        if strategy == "augment_with_failure_reason":
            return self._augment_with_failure_context(
                original_prompt, failure_reason, attempt
            )
        elif strategy == "minimal_prompt":
            return self._build_minimal_prompt(
                ticket_folder, stage, failure_reason
            )
        elif strategy == "split_subtasks":
            return self._build_first_subtask_prompt(
                ticket_folder, stage, failure_reason
            )
        else:
            return original_prompt

    def _augment_with_failure_context(
        self,
        original_prompt: str,
        failure_reason: str,
        attempt: int,
    ) -> str:
        """Strategy 1: Add failure context to the original prompt."""
        context_block = (
            f"## ⚠️ CONTEXTO DE REINTENTO (intento #{attempt})\n\n"
            f"El intento anterior falló. Causa detectada:\n"
            f"```\n{failure_reason}\n```\n\n"
            f"**IMPORTANTE:** Prestá especial atención al error anterior. "
            f"Evitá repetir el mismo patrón que causó la falla.\n\n"
            f"---\n\n"
        )
        return context_block + original_prompt

    def _build_minimal_prompt(
        self,
        ticket_folder: str,
        stage: str,
        failure_reason: str,
    ) -> str:
        """Strategy 2: Stripped-down prompt with only essential information."""
        folder = Path(ticket_folder)

        # Read only the most essential files
        inc_content = self._read_file_safe(folder, "INC-*.md", "INCIDENTE.md")
        tareas = self._read_file_safe(folder, None, "TAREAS_DESARROLLO.md")

        prompt = (
            f"# REINTENTO SIMPLIFICADO — Solo lo esencial\n\n"
            f"Los intentos anteriores fallaron. Este prompt está reducido al mínimo.\n"
            f"**Causa del fallo anterior:** {failure_reason}\n\n"
            f"## Incidente\n{inc_content[:2000]}\n\n"
        )

        if tareas:
            prompt += f"## Tareas\n{tareas[:2000]}\n\n"

        stage_instructions = {
            "pm": (
                "Generá un análisis técnico breve y directo. "
                "No elabores de más. Enfocate en: causa raíz + archivos a modificar."
            ),
            "dev": (
                "Implementá los cambios mínimos necesarios. "
                "No refactorices. Resolvé solo el problema reportado."
            ),
            "tester": (
                "Verificá solo los cambios de DEV contra el incidente reportado. "
                "No generes casos genéricos."
            ),
        }

        prompt += (
            f"## Instrucción\n"
            f"{stage_instructions.get(stage, 'Completá la tarea.')}\n"
        )

        return prompt

    def _build_first_subtask_prompt(
        self,
        ticket_folder: str,
        stage: str,
        failure_reason: str,
    ) -> str:
        """Strategy 3: Split into subtasks and attempt just the first one."""
        folder = Path(ticket_folder)
        tareas = self._read_file_safe(folder, None, "TAREAS_DESARROLLO.md")

        subtasks = self._extract_subtasks(tareas) if tareas else []

        if not subtasks:
            # Can't split — fall back to minimal
            return self._build_minimal_prompt(ticket_folder, stage, failure_reason)

        first_task = subtasks[0]

        prompt = (
            f"# REINTENTO — SUBTAREA 1 de {len(subtasks)}\n\n"
            f"El ticket completo es demasiado complejo para un solo intento.\n"
            f"Resolvé SOLO esta subtarea:\n\n"
            f"## Subtarea\n{first_task}\n\n"
            f"**Fallo anterior:** {failure_reason}\n\n"
            f"## Contexto mínimo\n"
        )

        inc_content = self._read_file_safe(folder, "INC-*.md", "INCIDENTE.md")
        if inc_content:
            prompt += f"{inc_content[:1000]}\n\n"

        prompt += (
            f"## Instrucción\n"
            f"Resolvé ÚNICAMENTE la subtarea indicada. "
            f"No intentes resolver el ticket completo.\n"
        )

        return prompt

    def _extract_subtasks(self, tareas_content: str) -> list[str]:
        """Extract individual task blocks from TAREAS_DESARROLLO.md."""
        if not tareas_content:
            return []

        # Pattern: ## [STATE] Task title
        blocks = re.split(r"(?=^##\s*\[)", tareas_content, flags=re.MULTILINE)
        tasks = [b.strip() for b in blocks if b.strip() and b.strip().startswith("##")]

        if not tasks:
            # Fallback: checkbox items
            lines = re.findall(r"^-\s*\[[ x]\]\s*(.+)$", tareas_content,
                               re.MULTILINE | re.IGNORECASE)
            tasks = lines

        return tasks

    def _read_file_safe(
        self,
        folder: Path,
        glob_pattern: Optional[str],
        fallback_name: str,
    ) -> str:
        """Read a file from the ticket folder safely."""
        if glob_pattern:
            matches = list(folder.glob(glob_pattern))
            if matches:
                try:
                    return matches[0].read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        fpath = folder / fallback_name
        if fpath.exists():
            try:
                return fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

        return ""
