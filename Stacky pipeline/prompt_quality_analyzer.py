"""
prompt_quality_analyzer.py — Análisis de calidad del prompt (autoevaluación sin IA).

Analiza el historial de ejecuciones para determinar qué versiones de prompts
tienen mejor performance para cada tipo de ticket. Proporciona scores compuestos
basados en: tasa de éxito al primer intento, promedio de placeholders, tasa de rework.

Uso:
    from prompt_quality_analyzer import PromptQualityAnalyzer
    analyzer = PromptQualityAnalyzer()
    score = analyzer.score_prompt_version("pm_v3", "bug", "pm")
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.prompt_quality")

DATA_DIR = Path(__file__).parent / "data"
PROMPT_HISTORY_FILE = DATA_DIR / "prompt_execution_history.json"


@dataclass
class PromptScore:
    """Score result for a prompt version."""
    version: str
    score: float
    first_attempt_rate: float = 0.0
    avg_placeholders: float = 0.0
    rework_rate: float = 0.0
    sample_size: int = 0
    confidence: str = "low"  # "high" if sample_size >= 10


@dataclass
class ExecutionRecord:
    """Record of a single prompt execution."""
    prompt_version: str
    ticket_type: str
    stage: str
    result: str  # "ok", "error", "timeout"
    retries: int = 0
    placeholder_count: int = 0
    had_rework: bool = False
    duration_seconds: float = 0.0
    timestamp: str = ""


class PromptQualityAnalyzer:
    """Analyzes prompt performance based on execution history."""

    def __init__(self, history_file: Optional[Path] = None):
        self._history_file = history_file or PROMPT_HISTORY_FILE

    def record_execution(self, record: ExecutionRecord):
        """Record a prompt execution result."""
        history = self._load_history()
        if record.timestamp == "":
            record.timestamp = datetime.now().isoformat()

        entry = {
            "prompt_version": record.prompt_version,
            "ticket_type": record.ticket_type,
            "stage": record.stage,
            "result": record.result,
            "retries": record.retries,
            "placeholder_count": record.placeholder_count,
            "had_rework": record.had_rework,
            "duration_seconds": record.duration_seconds,
            "timestamp": record.timestamp,
        }
        history.append(entry)
        self._save_history(history)
        logger.debug("Recorded execution: %s/%s → %s",
                      record.prompt_version, record.stage, record.result)

    def score_prompt_version(
        self,
        prompt_version: str,
        ticket_type: str,
        stage: str,
    ) -> PromptScore:
        """
        Calculate a composite score for a prompt version based on execution history.

        Score = (first_attempt_rate * 0.5) + (1 - avg_placeholders/10) * 0.3 + (1 - rework_rate) * 0.2
        """
        history = self._get_filtered_history(prompt_version, ticket_type, stage)

        if not history:
            return PromptScore(version=prompt_version, score=0.0, confidence="low")

        n = len(history)

        first_attempt_success = sum(
            1 for e in history if e["retries"] == 0 and e["result"] == "ok"
        ) / n

        avg_placeholders = sum(
            e.get("placeholder_count", 0) for e in history
        ) / n

        rework_rate = sum(
            1 for e in history if e.get("had_rework", False)
        ) / n

        score = (
            first_attempt_success * 0.5
            + max(0, (1 - avg_placeholders / 10)) * 0.3
            + (1 - rework_rate) * 0.2
        )

        return PromptScore(
            version=prompt_version,
            score=round(score, 3),
            first_attempt_rate=round(first_attempt_success, 3),
            avg_placeholders=round(avg_placeholders, 2),
            rework_rate=round(rework_rate, 3),
            sample_size=n,
            confidence="high" if n >= 10 else "medium" if n >= 5 else "low",
        )

    def suggest_prompt_upgrade(
        self,
        stage: str,
        ticket_type: str,
    ) -> Optional[str]:
        """
        If there's a better prompt version for this ticket type, suggest it.

        Returns the version name of the best prompt, or None if current is fine.
        """
        history = self._load_history()

        # Group by prompt version
        versions = set()
        for e in history:
            if e.get("stage") == stage and e.get("ticket_type") == ticket_type:
                versions.add(e["prompt_version"])

        if len(versions) < 2:
            return None  # Not enough versions to compare

        scores = {}
        for v in versions:
            score = self.score_prompt_version(v, ticket_type, stage)
            if score.confidence in ("high", "medium"):
                scores[v] = score

        if not scores:
            return None

        best = max(scores.values(), key=lambda s: s.score)
        return best.version if best.score > 0.6 else None

    def get_all_scores(self, stage: str) -> list[PromptScore]:
        """Get scores for all prompt versions for a given stage."""
        history = self._load_history()
        versions = set()
        ticket_types = set()

        for e in history:
            if e.get("stage") == stage:
                versions.add(e["prompt_version"])
                ticket_types.add(e.get("ticket_type", "unknown"))

        scores = []
        for v in versions:
            for tt in ticket_types:
                score = self.score_prompt_version(v, tt, stage)
                if score.sample_size > 0:
                    scores.append(score)

        return sorted(scores, key=lambda s: -s.score)

    def _get_filtered_history(
        self,
        prompt_version: str,
        ticket_type: str,
        stage: str,
    ) -> list[dict]:
        """Filter history by version, ticket type, and stage."""
        history = self._load_history()
        return [
            e for e in history
            if e.get("prompt_version") == prompt_version
            and e.get("ticket_type") == ticket_type
            and e.get("stage") == stage
        ]

    def _load_history(self) -> list[dict]:
        """Load execution history from file."""
        if self._history_file.exists():
            try:
                return json.loads(
                    self._history_file.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Error loading history: %s", e)
        return []

    def _save_history(self, history: list[dict]):
        """Save execution history to file."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._history_file.write_text(
            json.dumps(history, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
