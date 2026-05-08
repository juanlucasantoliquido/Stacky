"""
config_flag_tester.py — Configuration Flag Behavior Test.

Tests batch behavior with different configuration flag values (S/N, 1/0).

Uso:
    from config_flag_tester import ConfigFlagTester
    tester = ConfigFlagTester(config)
    cases = tester.run(ticket_folder, config)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.config_flags")


@dataclass
class FlagTestCase:
    flag: str
    value: str
    crashed: bool = False
    expected_behavior: str = ""
    actual_behavior: str = ""
    passed: bool = False


class ConfigFlagTester:
    POSSIBLE_VALUES = ["S", "N", "1", "0"]

    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> list[FlagTestCase]:
        if not self.batch_executor or not self.db:
            return []

        flags = self._extract_config_flags(ticket_folder)
        if not flags:
            return []

        cases = []
        for flag_name, flag_table in flags:
            for flag_value in self.POSSIBLE_VALUES:
                try:
                    case = self._test_flag(
                        ticket_folder, flag_name, flag_table, flag_value
                    )
                    cases.append(case)
                except Exception as e:
                    cases.append(FlagTestCase(
                        flag=flag_name,
                        value=flag_value,
                        crashed=True,
                    ))
                    logger.error("[ConfigFlag] Error for %s=%s: %s",
                                  flag_name, flag_value, e)
                finally:
                    if self.db:
                        try:
                            self.db.rollback()
                        except Exception:
                            pass

        return cases

    def _test_flag(self, ticket_folder: str, flag_name: str,
                   flag_table: str, flag_value: str) -> FlagTestCase:
        # Set the flag
        try:
            cursor = self.db.cursor() if hasattr(self.db, "cursor") else None
            if cursor:
                cursor.execute(
                    f"UPDATE {flag_table} SET RVALOR = ? WHERE RCOD_PARAM = ?",
                    (flag_value, flag_name)
                )
                self.db.commit() if hasattr(self.db, "commit") else None
        except Exception:
            pass

        mock = None
        if self.mock_generator:
            mock = self.mock_generator.generate(rows=3)
            self.db.insert(mock)

        result = self.batch_executor.run_minimal(ticket_folder)
        crashed = not result.passed if hasattr(result, "passed") else False

        return FlagTestCase(
            flag=flag_name,
            value=flag_value,
            crashed=crashed,
            expected_behavior=f"Process runs with {flag_name}={flag_value}",
            actual_behavior="crash" if crashed else "ok",
            passed=not crashed,
        )

    def _extract_config_flags(self, ticket_folder: str) -> list[tuple[str, str]]:
        folder = Path(ticket_folder)
        flags = []
        for fname in ["TAREAS_DESARROLLO.md", "ARQUITECTURA_SOLUCION.md",
                       "NOTAS_IMPLEMENTACION.md"]:
            p = folder / fname
            if not p.exists():
                continue
            content = p.read_text(encoding="utf-8", errors="replace")
            # Find flag references: RPARAM, RCONFIG, etc.
            for m in re.finditer(
                r"(RPARAM|RCONFIG)\s*[.\[]?\s*['\"]?(\w+)['\"]?",
                content, re.IGNORECASE
            ):
                table = m.group(1).upper()
                param = m.group(2)
                flags.append((param, table))
        return flags
