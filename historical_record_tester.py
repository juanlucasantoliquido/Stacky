"""
historical_record_tester.py — Historical Record Compatibility Test.

Tests batch processing with old/historical data that may have different formats.

Uso:
    from historical_record_tester import HistoricalRecordTester
    tester = HistoricalRecordTester(config)
    cases = tester.run(ticket_folder, config)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.historical")

HISTORICAL_SNAPSHOTS = [
    {"year": 2010, "desc": "Pre-migration SQL Server 2008 R2 records"},
    {"year": 2015, "desc": "ISO-8859-1 encoded records"},
    {"year": 2019, "desc": "Pre-REXTENSION column records"},
    {"year": 2022, "desc": "Legacy state 'T' deprecated records"},
]


@dataclass
class HistoricalTestCase:
    year: int
    description: str
    rows_tested: int = 0
    crashed: bool = False
    errors_in_log: int = 0
    passed: bool = False


class HistoricalRecordTester:
    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, historical_loader=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.historical_loader = historical_loader
        self.db = db

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> list[HistoricalTestCase]:
        if not self.batch_executor:
            return []

        cases = []
        tables = self._affected_tables(ticket_folder)

        for snapshot in HISTORICAL_SNAPSHOTS:
            try:
                case = self._test_snapshot(ticket_folder, snapshot, tables)
                cases.append(case)
            except Exception as e:
                cases.append(HistoricalTestCase(
                    year=snapshot["year"],
                    description=snapshot["desc"],
                    crashed=True,
                ))
                logger.error("[Historical] Error for %d: %s", snapshot["year"], e)
            finally:
                if self.db:
                    try:
                        self.db.rollback()
                    except Exception:
                        pass

        return cases

    def _test_snapshot(self, ticket_folder: str, snapshot: dict,
                       tables: list[str]) -> HistoricalTestCase:
        historical_data = None
        if self.historical_loader:
            try:
                historical_data = self.historical_loader.load(
                    snapshot["year"], tables=tables
                )
            except Exception:
                pass

        rows_tested = 0
        if historical_data and self.db:
            self.db.insert(historical_data)
            rows_tested = len(historical_data) if isinstance(historical_data, list) else 1

        result = self.batch_executor.run_minimal(ticket_folder)
        crashed = not result.passed if hasattr(result, "passed") else False

        errors = 0
        if hasattr(result, "stderr") and result.stderr:
            errors = result.stderr.count("Error") + result.stderr.count("Exception")

        return HistoricalTestCase(
            year=snapshot["year"],
            description=snapshot["desc"],
            rows_tested=rows_tested,
            crashed=crashed,
            errors_in_log=errors,
            passed=not crashed,
        )

    def _affected_tables(self, ticket_folder: str) -> list[str]:
        folder = Path(ticket_folder)
        tables = set()
        for fname in ["TAREAS_DESARROLLO.md", "ARQUITECTURA_SOLUCION.md"]:
            p = folder / fname
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r"\b(R[A-Z]{3,}[A-Z0-9_]*)\b", content):
                    tables.add(m.group(1))
        return list(tables)
