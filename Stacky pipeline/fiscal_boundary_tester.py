"""
fiscal_boundary_tester.py — Fiscal Year Boundary Test.

Tests batch processes at fiscal year boundaries (Dec 31/Jan 1) to catch
year-crossing bugs.

Uso:
    from fiscal_boundary_tester import FiscalBoundaryTester
    tester = FiscalBoundaryTester(config)
    cases = tester.run(ticket_folder, config)
"""

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.fiscal_boundary")

BOUNDARY_DATES = [
    date(2025, 12, 31),
    date(2026, 1, 1),
    date(2025, 12, 30),
    date(2026, 1, 2),
    date(2025, 6, 30),
]


@dataclass
class FiscalTestCase:
    test_date: date
    proceso_date_correct: bool = True
    no_crash: bool = True
    passed: bool = False


class FiscalBoundaryTester:
    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> list[FiscalTestCase]:
        if not self._involves_fechas(ticket_folder):
            return []

        if not self.batch_executor:
            return []

        cases = []
        for boundary_date in BOUNDARY_DATES:
            try:
                case = self._test_boundary(ticket_folder, boundary_date)
                cases.append(case)
            except Exception as e:
                cases.append(FiscalTestCase(
                    test_date=boundary_date,
                    no_crash=False,
                    passed=False,
                ))
                logger.error("[Fiscal] Error for %s: %s", boundary_date, e)
            finally:
                if self.db:
                    try:
                        self.db.rollback()
                    except Exception:
                        pass

        return cases

    def _test_boundary(self, ticket_folder: str, boundary_date: date) -> FiscalTestCase:
        mock = None
        if self.mock_generator and hasattr(self.mock_generator, "generate_with_date"):
            mock = self.mock_generator.generate_with_date(boundary_date)
        else:
            mock = {"RFEC_PROCESO": boundary_date.isoformat()}

        if self.db and mock:
            self.db.insert(mock)

        result = self.batch_executor.run_minimal(ticket_folder)
        no_crash = result.passed if hasattr(result, "passed") else True

        # Check if the date was processed correctly
        fecha_correct = True
        if self.db and mock and hasattr(self.db, "read_result"):
            try:
                result_row = self.db.read_result(mock.get("id"))
                if result_row:
                    fecha_proc = result_row.get("RFEC_PROCESO")
                    if fecha_proc and hasattr(fecha_proc, "year"):
                        fecha_correct = (fecha_proc.year == boundary_date.year)
            except Exception:
                pass

        return FiscalTestCase(
            test_date=boundary_date,
            proceso_date_correct=fecha_correct,
            no_crash=no_crash,
            passed=(no_crash and fecha_correct),
        )

    def _involves_fechas(self, ticket_folder: str) -> bool:
        folder = Path(ticket_folder)
        for fname in ["TAREAS_DESARROLLO.md", "ARQUITECTURA_SOLUCION.md"]:
            p = folder / fname
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="replace").lower()
                if any(k in content for k in [
                    "fecha", "rfec_", "date", "periodo", "ejercicio",
                    "año", "cierre"
                ]):
                    return True
        return False
