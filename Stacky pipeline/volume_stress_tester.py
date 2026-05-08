"""
volume_stress_tester.py — Volume Stress Test (Realistic Data Scale).

Tests batch execution at different data volumes to detect O(n^2) complexity.

Uso:
    from volume_stress_tester import VolumeStressTester
    tester = VolumeStressTester(config)
    result = tester.run(ticket_folder, config)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("stacky.volume_stress")

VOLUME_LEVELS = [
    {"rows": 100, "label": "small", "timeout": 30},
    {"rows": 5_000, "label": "medium", "timeout": 120},
    {"rows": 50_000, "label": "large", "timeout": 600},
]


@dataclass
class VolumeTestResult:
    timings: dict = field(default_factory=dict)
    complexity_ok: bool = True
    scalability_issue: bool = False
    passed: bool = True


class VolumeStressTester:
    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> VolumeTestResult:
        if not self.batch_executor or not self.mock_generator or not self.db:
            return VolumeTestResult()

        cfg = config or self.config
        levels = cfg.get("volume_levels", VOLUME_LEVELS)
        timings = {}

        for level in levels:
            label = level["label"]
            rows = level["rows"]
            timeout = level.get("timeout", 300)

            try:
                mock = self.mock_generator.generate(rows=rows)
                self.db.insert(mock)

                start = time.perf_counter()
                result = self.batch_executor.run_minimal(ticket_folder)
                elapsed = time.perf_counter() - start

                timed_out = not result.passed if hasattr(result, "passed") else False
                rps = round(rows / elapsed, 1) if elapsed > 0 else 0

                timings[label] = {
                    "rows": rows,
                    "elapsed_sec": round(elapsed, 2),
                    "rows_per_sec": rps,
                    "timeout": timed_out,
                }

                logger.info("[Volume] %s: %d rows in %.1fs (%.0f rows/s)",
                             label, rows, elapsed, rps)

            except Exception as e:
                timings[label] = {
                    "rows": rows,
                    "elapsed_sec": -1,
                    "rows_per_sec": 0,
                    "timeout": True,
                }
                logger.error("[Volume] %s failed: %s", label, e)
            finally:
                try:
                    self.db.rollback()
                except Exception:
                    pass

        # Detect algorithmic complexity
        complexity_ok = True
        scalability_issue = False

        if "small" in timings and "medium" in timings:
            small_rps = timings["small"].get("rows_per_sec", 1)
            medium_rps = timings["medium"].get("rows_per_sec", 1)
            if small_rps > 0:
                complexity_ok = (medium_rps > small_rps * 0.5)

        if "small" in timings and "large" in timings:
            small_timeout = timings["small"].get("timeout", False)
            large_timeout = timings["large"].get("timeout", False)
            scalability_issue = (not small_timeout and large_timeout)

        return VolumeTestResult(
            timings=timings,
            complexity_ok=complexity_ok,
            scalability_issue=scalability_issue,
            passed=complexity_ok and not scalability_issue,
        )
