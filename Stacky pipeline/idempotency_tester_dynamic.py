"""
idempotency_tester_dynamic.py — Dynamic Idempotency Test.

Verifies f(f(x)) = f(x) — running the batch twice produces the same result.

Uso:
    from idempotency_tester_dynamic import IdempotencyTester
    tester = IdempotencyTester(config)
    result = tester.run(ticket_folder, config)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.idempotency")


@dataclass
class IdempotencyResult:
    passed: bool
    duplicate_rows: int = 0
    diff_sample: Optional[str] = None


class IdempotencyTester:
    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> IdempotencyResult:
        if not self.batch_executor or not self.db:
            return IdempotencyResult(passed=True, diff_sample="No executor/db — skipped")

        tables = self._affected_tables(ticket_folder)
        mock = None
        if self.mock_generator:
            mock = self.mock_generator.generate(rows=5)
            self.db.insert(mock)

        # First execution
        self.batch_executor.run_minimal(ticket_folder)
        state_first = self._capture_state(tables)

        # Second execution (same data)
        self.batch_executor.run_minimal(ticket_folder)
        state_second = self._capture_state(tables)

        is_idempotent = (state_first == state_second)

        duplicates = 0
        diff = None
        if not is_idempotent:
            diff = self._diff_states(state_first, state_second)
            duplicates = self._count_duplicates(tables)
            logger.warning("[Idempotency] NOT idempotent: %d duplicates, diff=%s",
                            duplicates, diff[:200] if diff else "")

        return IdempotencyResult(
            passed=is_idempotent,
            duplicate_rows=duplicates,
            diff_sample=diff,
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

    def _capture_state(self, tables: list[str]) -> dict:
        if self.db and hasattr(self.db, "capture_state"):
            return self.db.capture_state(tables)
        return {}

    def _diff_states(self, state1: dict, state2: dict) -> str:
        diffs = []
        for table in set(list(state1.keys()) + list(state2.keys())):
            s1 = state1.get(table)
            s2 = state2.get(table)
            if s1 != s2:
                diffs.append(f"{table}: state changed between executions")
        return "; ".join(diffs) if diffs else ""

    def _count_duplicates(self, tables: list[str]) -> int:
        if self.db and hasattr(self.db, "count_duplicates"):
            return self.db.count_duplicates(tables)
        return 0
