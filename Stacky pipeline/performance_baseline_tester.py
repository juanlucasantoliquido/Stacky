"""
performance_baseline_tester.py — Performance Baseline Test.

Measures execution time and compares against historical baselines.

Uso:
    from performance_baseline_tester import PerformanceBaselineTester
    tester = PerformanceBaselineTester()
    result = tester.run("ProcessPagos", lambda: my_batch.execute())
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Callable, Optional

logger = logging.getLogger("stacky.perf_baseline")

BASELINES_FILE = Path(__file__).parent / "data" / "performance_baselines.json"


@dataclass
class PerformanceResult:
    elapsed: float
    baseline: Optional[float]
    ratio: float
    verdict: str  # "pass", "warning", "fail", "baseline_established"
    process_name: str = ""


class PerformanceBaselineTester:
    THRESHOLD_WARNING = 1.5   # 50% slower → WARNING
    THRESHOLD_FAIL = 3.0      # 3x slower → FAIL
    MAX_HISTORY = 20

    def __init__(self, baselines_file: Optional[Path] = None):
        self._file = baselines_file or BASELINES_FILE
        self._data = self._load()

    def run(self, process_name: str, exec_fn: Callable) -> PerformanceResult:
        start = time.perf_counter()
        exec_fn()
        elapsed = time.perf_counter() - start

        baseline = self._get_baseline(process_name)

        if baseline is None:
            self._record(process_name, elapsed)
            return PerformanceResult(
                elapsed=round(elapsed, 3),
                baseline=None,
                ratio=1.0,
                verdict="baseline_established",
                process_name=process_name,
            )

        ratio = elapsed / baseline if baseline > 0 else 1.0

        if ratio < self.THRESHOLD_WARNING:
            verdict = "pass"
        elif ratio < self.THRESHOLD_FAIL:
            verdict = "warning"
        else:
            verdict = "fail"

        self._record(process_name, elapsed)

        return PerformanceResult(
            elapsed=round(elapsed, 3),
            baseline=round(baseline, 3),
            ratio=round(ratio, 2),
            verdict=verdict,
            process_name=process_name,
        )

    def _get_baseline(self, process_name: str) -> Optional[float]:
        history = self._data.get(process_name, [])
        if not history:
            return None
        return mean(history[-5:])  # average of last 5

    def _record(self, process_name: str, elapsed: float):
        if process_name not in self._data:
            self._data[process_name] = []
        self._data[process_name].append(round(elapsed, 3))
        if len(self._data[process_name]) > self.MAX_HISTORY:
            self._data[process_name] = self._data[process_name][-self.MAX_HISTORY:]
        self._save()

    def _load(self) -> dict:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self):
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(self._data, indent=2), encoding="utf-8"
        )
