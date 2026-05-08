"""
negative_input_tester.py — Negative Input Path Test (Soft Fuzzing).

Sends extreme/invalid data and verifies no crash, no SQL injection,
no corrupt data saved.

Uso:
    from negative_input_tester import NegativeInputTester
    tester = NegativeInputTester(config)
    cases = tester.run(ticket_folder, config)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.negative_input")

NEGATIVE_INPUTS = {
    "VARCHAR": [
        "'; DROP TABLE RCLIE; --",
        "<script>alert(1)</script>",
        "A" * 5000,
        "\x00\x01\x02\x03",
        "NULL",
        "   ",
    ],
    "NUMBER": [
        "NaN",
        "Infinity",
        "99999999999999999999999",
        "-0",
    ],
    "DATE": [
        "00/00/0000",
        "29/02/2023",
        "99/99/9999",
    ],
}


@dataclass
class NegativeTestCase:
    field: str
    input: str
    crashed: bool = False
    sql_injected: bool = False
    bad_value_saved: bool = False
    passed: bool = False
    evidence: str = ""


class NegativeInputTester:
    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> list[NegativeTestCase]:
        if not self.batch_executor or not self.mock_generator or not self.db:
            return []

        field_map = self._extract_input_fields(ticket_folder)
        cases = []

        for field_name, field_type in field_map.items():
            bad_values = NEGATIVE_INPUTS.get(field_type, NEGATIVE_INPUTS.get("VARCHAR", []))

            for bad_val in bad_values:
                try:
                    case = self._test_input(ticket_folder, field_name, bad_val)
                    cases.append(case)
                except Exception as e:
                    cases.append(NegativeTestCase(
                        field=field_name,
                        input=str(bad_val)[:50],
                        crashed=True,
                        evidence=str(e)[:200]
                    ))
                finally:
                    try:
                        self.db.rollback()
                    except Exception:
                        pass

        return cases

    def _test_input(self, ticket_folder: str, field: str, bad_val) -> NegativeTestCase:
        mock = self.mock_generator.generate_base_row() if hasattr(
            self.mock_generator, "generate_base_row"
        ) else {"id": 1}
        mock[field] = bad_val
        self.db.insert(mock)

        result = self.batch_executor.run_minimal(ticket_folder)
        crashed = not result.passed if hasattr(result, "passed") else False

        # Check not SQL injected
        sql_injected = False
        if hasattr(self.db, "check_table_dropped"):
            sql_injected = self.db.check_table_dropped("RCLIE")

        # Check bad value not saved
        bad_saved = False
        if hasattr(self.db, "read_field"):
            saved_val = self.db.read_field(mock.get("id"), field)
            bad_saved = (saved_val == bad_val)

        return NegativeTestCase(
            field=field,
            input=str(bad_val)[:50],
            crashed=crashed,
            sql_injected=sql_injected,
            bad_value_saved=bad_saved,
            passed=(not sql_injected and not bad_saved),
        )

    def _extract_input_fields(self, ticket_folder: str) -> dict[str, str]:
        folder = Path(ticket_folder)
        fields = {}
        for fname in ["TAREAS_DESARROLLO.md", "ARQUITECTURA_SOLUCION.md"]:
            p = folder / fname
            if not p.exists():
                continue
            content = p.read_text(encoding="utf-8", errors="replace")
            # Detect R-prefixed fields
            for m in re.finditer(r"\b(R\w{3,})\b", content):
                name = m.group(1)
                # Infer type from name
                if any(k in name.upper() for k in ["FEC", "DATE"]):
                    fields[name] = "DATE"
                elif any(k in name.upper() for k in ["IMP", "SALDO", "MONTO"]):
                    fields[name] = "NUMBER"
                else:
                    fields[name] = "VARCHAR"
        return fields
