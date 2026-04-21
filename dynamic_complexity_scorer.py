"""
dynamic_complexity_scorer.py — Umbral dinámico de complejidad basado en historial ADO.

Calibra dinámicamente timeouts y estrategias por tipo de ticket y módulo usando
datos históricos reales de ejecuciones pasadas.

Uso:
    from dynamic_complexity_scorer import DynamicComplexityScorer
    scorer = DynamicComplexityScorer()
    result = scorer.score(inc_content)
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Optional

logger = logging.getLogger("stacky.dynamic_complexity")

DATA_DIR = Path(__file__).parent / "data"
MODULE_STATS_FILE = DATA_DIR / "module_stats.json"

# Default timeouts in seconds
DEFAULT_TIMEOUT_PM = 600    # 10 min
DEFAULT_TIMEOUT_DEV = 900   # 15 min
DEFAULT_TIMEOUT_QA = 600    # 10 min


@dataclass
class ComplexityScore:
    """Result of complexity scoring."""
    complexity: str  # "simple", "medio", "complejo"
    timeout_pm: int
    timeout_dev: int
    timeout_qa: int
    confidence: str  # "high", "medium", "low"
    modules_detected: list[str]
    similar_tickets_count: int = 0
    estimated_total_minutes: int = 0


class DynamicComplexityScorer:
    """
    Scores ticket complexity using both static heuristics and historical data.
    Dynamically adjusts timeouts based on past performance per module.
    """

    # Static complexity signals
    COMPLEXITY_SIGNALS = {
        "complejo": [
            r"rendimiento",
            r"migración",
            r"integración",
            r"todos\s+los\s+registros",
            r"multi-?\s*empresa",
            r"concurrencia",
            r"seguridad",
            r"stored\s+procedure",
            r"trigger",
            r"cursor",
        ],
        "medio": [
            r"formulario",
            r"reporte",
            r"grilla",
            r"validación",
            r"campo\s+nuevo",
            r"filtro",
        ],
        "simple": [
            r"alter\s+table",
            r"create\s+index",
            r"sp_rename",
            r"agregar\s+columna",
            r"cambiar\s+tipo",
            r"texto\s+de\s+etiqueta",
        ],
    }

    # Module detection patterns
    MODULE_PATTERNS = [
        (r"\bBatch/Negocio/(\w+)\.cs", "batch_negocio"),
        (r"\bBatch/(\w+)\.cs", "batch"),
        (r"\bOnLine/(\w+)\.aspx", "online"),
        (r"\bBD/(\w+)\.sql", "bd"),
        (r"\bVB/(\w+)\.vb", "vb"),
        (r"\b(RPAGOS|RDEUDA|RCLIE|RDIRE|REMP|RSALD)\b", "tabla"),
    ]

    def __init__(self, knowledge_base=None):
        self._knowledge_base = knowledge_base
        self._module_stats = self._load_module_stats()

    def score(self, inc_content: str, work_item_id: int = 0) -> ComplexityScore:
        """
        Score ticket complexity combining static heuristics and historical data.

        Args:
            inc_content: Content of the incident description
            work_item_id: Optional ADO Work Item ID for historical lookup
        """
        # Static scoring
        static_complexity = self._score_static(inc_content)

        # Module detection
        modules = self._extract_modules(inc_content)

        # Historical scoring (if knowledge base available)
        similar = self._find_similar_tickets(inc_content)
        historical_complexity = static_complexity
        similar_count = 0

        if similar:
            similar_count = len(similar)
            avg_duration = mean(t.get("total_duration_min", 30) for t in similar)
            avg_rework = mean(t.get("rework_cycles", 0) for t in similar)

            if avg_duration > 60 or avg_rework > 1:
                historical_complexity = "complejo"
            elif avg_duration > 25:
                historical_complexity = "medio"
            else:
                historical_complexity = "simple"

        # Final complexity: worst of static and historical
        complexity_rank = {"simple": 1, "medio": 2, "complejo": 3}
        final_complexity = max(
            [static_complexity, historical_complexity],
            key=lambda c: complexity_rank.get(c, 2)
        )

        # Module time factor
        module_factor = self._get_module_factor(modules)

        # Calculate timeouts
        base_timeouts = {
            "simple": (DEFAULT_TIMEOUT_PM * 0.7, DEFAULT_TIMEOUT_DEV * 0.7, DEFAULT_TIMEOUT_QA * 0.7),
            "medio": (DEFAULT_TIMEOUT_PM, DEFAULT_TIMEOUT_DEV, DEFAULT_TIMEOUT_QA),
            "complejo": (DEFAULT_TIMEOUT_PM * 1.5, DEFAULT_TIMEOUT_DEV * 2, DEFAULT_TIMEOUT_QA * 1.5),
        }
        base_pm, base_dev, base_qa = base_timeouts.get(
            final_complexity,
            (DEFAULT_TIMEOUT_PM, DEFAULT_TIMEOUT_DEV, DEFAULT_TIMEOUT_QA)
        )

        return ComplexityScore(
            complexity=final_complexity,
            timeout_pm=int(base_pm * module_factor),
            timeout_dev=int(base_dev * module_factor),
            timeout_qa=int(base_qa * module_factor),
            confidence="high" if similar_count >= 3 else "medium" if similar_count >= 1 else "low",
            modules_detected=modules,
            similar_tickets_count=similar_count,
            estimated_total_minutes=int((base_pm + base_dev + base_qa) * module_factor / 60),
        )

    def record_execution(self, module: str, duration_seconds: float):
        """Record actual execution time for a module to improve future estimates."""
        if module not in self._module_stats:
            self._module_stats[module] = {"times": [], "avg_multiplier": 1.0}

        stats = self._module_stats[module]
        stats["times"].append(duration_seconds)

        # Keep last 20 entries
        if len(stats["times"]) > 20:
            stats["times"] = stats["times"][-20:]

        # Recalculate average multiplier
        avg_time = mean(stats["times"])
        default_time = (DEFAULT_TIMEOUT_PM + DEFAULT_TIMEOUT_DEV + DEFAULT_TIMEOUT_QA) / 3
        stats["avg_multiplier"] = round(avg_time / default_time, 2) if default_time > 0 else 1.0

        self._save_module_stats()

    def _score_static(self, content: str) -> str:
        """Score complexity using keyword heuristics."""
        content_lower = content.lower()

        for complexity, patterns in self.COMPLEXITY_SIGNALS.items():
            if any(re.search(p, content_lower) for p in patterns):
                return complexity

        return "medio"  # default

    def _extract_modules(self, content: str) -> list[str]:
        """Detect which modules/components are mentioned in the content."""
        modules = set()
        for pattern, module_type in self.MODULE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                modules.add(module_type)
        return list(modules)

    def _get_module_factor(self, modules: list[str]) -> float:
        """Get the time multiplier based on modules involved."""
        if not modules:
            return 1.0

        factors = []
        for m in modules:
            stats = self._module_stats.get(m)
            if stats:
                factors.append(stats.get("avg_multiplier", 1.0))

        return max(factors) if factors else 1.0

    def _find_similar_tickets(self, content: str) -> list[dict]:
        """Find historically similar tickets from the knowledge base."""
        if self._knowledge_base is None:
            try:
                from knowledge_base import KnowledgeBase
                self._knowledge_base = KnowledgeBase()
            except ImportError:
                return []

        try:
            if hasattr(self._knowledge_base, "get_similar_tickets"):
                return self._knowledge_base.get_similar_tickets(content, top_k=5)
            elif hasattr(self._knowledge_base, "search"):
                return self._knowledge_base.search(content, top_k=5)
        except Exception as e:
            logger.debug("Knowledge base query failed: %s", e)

        return []

    def _load_module_stats(self) -> dict:
        if MODULE_STATS_FILE.exists():
            try:
                return json.loads(MODULE_STATS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_module_stats(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        MODULE_STATS_FILE.write_text(
            json.dumps(self._module_stats, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
