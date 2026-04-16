"""
correction_memory.py — Y-01: Memoria acumulativa de correcciones por ticket.

Registra todos los ciclos de rework de un ticket, acumulando los issues de cada
ciclo para que PM revision tenga visibilidad histórica completa.
"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger("mantis.correction_memory")


class CorrectionMemory:
    """
    Persiste en {ticket_folder}/CORRECTION_MEMORY.json.
    Cada ciclo tiene: número de ciclo, issues reportados, timestamp.
    """

    def __init__(self, ticket_folder: str):
        self.ticket_folder = ticket_folder
        self._path = os.path.join(ticket_folder, "CORRECTION_MEMORY.json")
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self._path):
            try:
                return json.load(open(self._path, encoding="utf-8"))
            except Exception:
                pass
        return {"cycles": [], "stagnation_count": 0}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("CorrectionMemory: error guardando: %s", e)

    def add_cycle(self, cycle_num: int, issues: list, qa_verdict: str = "") -> None:
        """Registra los issues de un ciclo de rework."""
        cycle = {
            "cycle_num":  cycle_num,
            "issues":     issues,
            "qa_verdict": qa_verdict,
            "ts":         datetime.now().isoformat(),
        }
        self._data["cycles"].append(cycle)
        self._save()

    def get_all_issues(self) -> list:
        """Retorna lista plana de todos los issues de todos los ciclos."""
        all_issues = []
        for cycle in self._data["cycles"]:
            for issue in cycle.get("issues", []):
                all_issues.append(f"[Ciclo {cycle['cycle_num']}] {issue}")
        return all_issues

    def get_cycle_count(self) -> int:
        return len(self._data["cycles"])

    def check_stagnation(self, min_improvement_ratio: float = 0.25) -> bool:
        """
        Detecta stagnation: si en las últimas 3 iteraciones la cantidad de issues
        no bajó al menos un min_improvement_ratio (25%), considera que está atascado.
        Retorna True si hay stagnation.
        """
        cycles = self._data["cycles"]
        if len(cycles) < 3:
            return False
        last_three = cycles[-3:]
        issue_counts = [len(c.get("issues", [])) for c in last_three]
        if issue_counts[0] == 0:
            return False
        improvement = (issue_counts[0] - issue_counts[-1]) / issue_counts[0]
        is_stagnated = improvement < min_improvement_ratio
        if is_stagnated:
            self._data["stagnation_count"] = self._data.get("stagnation_count", 0) + 1
            self._save()
        return is_stagnated

    def get_efficiency_score(self) -> float:
        """
        Retorna un score de 0.0 a 1.0 basado en la reducción de issues por ciclo.
        1.0 = resuelto en primer intento. 0.0 = sin progreso.
        """
        cycles = self._data["cycles"]
        if not cycles:
            return 1.0
        first = len(cycles[0].get("issues", [1]))  # default 1 para evitar div/0
        last  = len(cycles[-1].get("issues", []))
        if first == 0:
            return 1.0
        return max(0.0, 1.0 - (last / first))

    def clear(self) -> None:
        """Limpia la memoria (usado en reset/reimport)."""
        self._data = {"cycles": [], "stagnation_count": 0}
        self._save()
