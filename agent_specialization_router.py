"""
agent_specialization_router.py — Elige variante de prompt óptima por módulo.

Mantiene múltiples variantes de prompt por agente/módulo y aprende cuál funciona
mejor para cada combinación basado en historial de éxito.

Uso:
    from agent_specialization_router import AgentSpecializationRouter
    router = AgentSpecializationRouter()
    variant = router.select_best_variant("pm", ticket_folder)
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.specialization")

DATA_DIR = Path(__file__).parent / "data"
SPECIALIZATION_STATS = DATA_DIR / "specialization_stats.json"

VARIANTS_PER_AGENT = {
    "pm": ["pm_standard", "pm_batch_dalc", "pm_online_aspx", "pm_ddl"],
    "dev": ["dev_standard", "dev_batch_dalc", "dev_online_aspx"],
    "tester": ["tester_standard", "tester_ddl", "tester_online"],
}

MODULE_DETECTION = {
    "batch_dalc": [r"dalc", r"batch/negocio", r"\.dalc\.cs"],
    "online_aspx": [r"\.aspx", r"frm\w+", r"online/", r"agenda"],
    "ddl": [r"alter\s+table", r"create\s+index", r"\.sql\b"],
}


class AgentSpecializationRouter:
    MIN_HISTORY_FOR_SELECTION = 5

    def __init__(self):
        self._stats = self._load_stats()

    def select_best_variant(self, agent: str, ticket_folder: str) -> str:
        module_type = self._detect_module_type(ticket_folder)
        default = f"{agent}_standard"

        if agent not in VARIANTS_PER_AGENT:
            return default

        variants = VARIANTS_PER_AGENT[agent]
        best_variant = default
        best_rate = -1.0

        for variant in variants:
            key = f"{variant}:{module_type}"
            stats = self._stats.get(key, {})
            total = stats.get("total", 0)
            if total < self.MIN_HISTORY_FOR_SELECTION:
                continue
            success_rate = stats.get("success", 0) / total
            if success_rate > best_rate:
                best_rate = success_rate
                best_variant = variant

        if best_rate >= 0:
            logger.info("[Specialization] %s → %s (module: %s, rate: %.0f%%)",
                         agent, best_variant, module_type, best_rate * 100)
        return best_variant

    def record_result(self, variant: str, module_type: str, success: bool):
        key = f"{variant}:{module_type}"
        if key not in self._stats:
            self._stats[key] = {"total": 0, "success": 0}
        self._stats[key]["total"] += 1
        if success:
            self._stats[key]["success"] += 1
        self._save_stats()

    def get_all_stats(self) -> dict:
        return dict(self._stats)

    def _detect_module_type(self, ticket_folder: str) -> str:
        folder = Path(ticket_folder)
        scan_files = ["ARQUITECTURA_SOLUCION.md", "TAREAS_DESARROLLO.md", "ANALISIS_TECNICO.md"]
        combined = ""
        for f in scan_files:
            p = folder / f
            if p.exists():
                try:
                    combined += p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        for module, patterns in MODULE_DETECTION.items():
            if any(re.search(p, combined, re.IGNORECASE) for p in patterns):
                return module
        return "general"

    def _load_stats(self) -> dict:
        if SPECIALIZATION_STATS.exists():
            try:
                return json.loads(SPECIALIZATION_STATS.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_stats(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SPECIALIZATION_STATS.write_text(
            json.dumps(self._stats, indent=2, ensure_ascii=False), encoding="utf-8"
        )
