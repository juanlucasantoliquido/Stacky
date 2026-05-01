"""
concurrency_safety_tester.py — Concurrency Safety Test.

Runs batch process multiple times in parallel to detect deadlocks,
race conditions, and data duplication.

Uso:
    from concurrency_safety_tester import ConcurrencySafetyTester
    tester = ConcurrencySafetyTester(config)
    result = tester.run(ticket_folder, config)
"""

import logging
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("stacky.concurrency")


@dataclass
class ConcurrencyTestResult:
    all_completed: bool = False
    duplicates_found: bool = False
    deadlock_detected: bool = False
    individual_results: list = None

    def __post_init__(self):
        if self.individual_results is None:
            self.individual_results = []

    @property
    def passed(self):
        return self.all_completed and not self.duplicates_found and not self.deadlock_detected


class ConcurrencySafetyTester:
    PARALLEL_INSTANCES = 2
    THREAD_TIMEOUT = 120  # seconds

    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> ConcurrencyTestResult:
        cfg = config or self.config
        instances = cfg.get("parallel_instances", self.PARALLEL_INSTANCES)

        if not self.batch_executor:
            return ConcurrencyTestResult(
                all_completed=False,
                individual_results=["No batch executor configured"]
            )

        # Generate separate mock datasets
        mock_sets = []
        if self.mock_generator:
            for i in range(instances):
                try:
                    mock = self.mock_generator.generate(rows=5, seed=i)
                    mock_sets.append(mock)
                except Exception:
                    pass

        # Insert all mock data
        if self.db and mock_sets:
            for ms in mock_sets:
                try:
                    self.db.insert(ms)
                except Exception as e:
                    logger.warning("Mock insert failed: %s", e)

        # Run parallel instances
        results = [None] * instances
        errors = [None] * instances

        def run_instance(idx):
            try:
                results[idx] = self.batch_executor.run_minimal(ticket_folder)
            except Exception as e:
                errors[idx] = str(e)

        threads = []
        for i in range(instances):
            t = threading.Thread(target=run_instance, args=(i,), name=f"conc-{i}")
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=self.THREAD_TIMEOUT)

        # Collect results
        all_completed = all(r is not None for r in results)
        deadlock = any(t.is_alive() for t in threads)

        # Check for duplicates
        duplicates_found = False
        if self.db:
            try:
                duplicates_found = self.db.count_duplicates([]) > 0
            except Exception:
                pass

        return ConcurrencyTestResult(
            all_completed=all_completed,
            duplicates_found=duplicates_found,
            deadlock_detected=deadlock,
            individual_results=[
                {"index": i, "completed": results[i] is not None,
                 "error": errors[i]}
                for i in range(instances)
            ]
        )
