"""
error_path_tester.py — Error Path & Exception Handling Test.

Tests how batch processes handle invalid data: crash, silent corruption, or proper logging.

Uso:
    from error_path_tester import ErrorPathTester
    tester = ErrorPathTester(config)
    results = tester.run(ticket_folder, config)
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.error_path")


@dataclass
class ErrorPathResult:
    scenario: str
    crashed: bool = False
    error_logged: bool = False
    others_processed: bool = False
    passed: bool = False
    evidence: str = ""


class ErrorPathTester:
    ERROR_SCENARIOS = [
        "cliente_inexistente",
        "empresa_inexistente",
        "importe_nulo",
        "fecha_invalida",
        "referencia_circular",
    ]

    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> list[ErrorPathResult]:
        if not self.batch_executor or not self.mock_generator or not self.db:
            return [ErrorPathResult(
                scenario="all",
                evidence="No executor/generator/db — skipped"
            )]

        results = []
        for scenario in self.ERROR_SCENARIOS:
            try:
                result = self._test_scenario(ticket_folder, scenario)
                results.append(result)
            except Exception as e:
                results.append(ErrorPathResult(
                    scenario=scenario,
                    crashed=True,
                    evidence=str(e)[:200]
                ))
            finally:
                try:
                    self.db.rollback()
                except Exception:
                    pass

        return results

    def _test_scenario(self, ticket_folder: str, scenario: str) -> ErrorPathResult:
        bad_mock = self.mock_generator.generate_invalid(scenario)
        self.db.insert(bad_mock)

        batch_result = self.batch_executor.run_minimal(ticket_folder)
        crashed = not batch_result.passed

        error_logged = False
        if self.db and hasattr(self.db, "check_error_logged"):
            error_logged = self.db.check_error_logged(bad_mock.get("id"))

        others_processed = False
        if self.db and hasattr(self.db, "check_others_processed"):
            others_processed = self.db.check_others_processed(bad_mock)

        return ErrorPathResult(
            scenario=scenario,
            crashed=crashed,
            error_logged=error_logged,
            others_processed=others_processed,
            passed=(not crashed and error_logged),
        )
