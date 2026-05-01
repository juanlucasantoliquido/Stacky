"""
boundary_value_generator.py — Boundary Value Test Generator.

Generates edge-case test data based on column types (max length, zero, overflow, etc.)

Uso:
    from boundary_value_generator import BoundaryValueGenerator
    gen = BoundaryValueGenerator()
    cases = gen.generate_cases(table_schema, "RIMPORTE")
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("stacky.boundary")


@dataclass
class BoundaryTestCase:
    input_value: Any
    boundary_type: str  # "empty", "max", "overflow", "negative", "zero", "edge_date"
    expected_behavior: str  # "accept", "reject", "truncate"
    column: str = ""


BOUNDARY_RULES = {
    "varchar": {
        "fn": lambda n: [("", "empty"), ("A" * n, "max"), ("A" * (n + 1), "overflow")],
    },
    "nvarchar": {
        "fn": lambda n: [("", "empty"), ("A" * n, "max"), ("A" * (n + 1), "overflow")],
    },
    "char": {
        "fn": lambda n: [("A", "valid"), (" ", "space"), ("", "empty"), ("A" * (n + 1), "overflow")],
    },
    "decimal": {
        "fn": lambda n: [(0, "zero"), (-0.01, "negative"), (99999999.99, "max_practical"), (10 ** n, "overflow")],
    },
    "int": {
        "fn": lambda n: [(0, "zero"), (-1, "negative"), (2147483647, "max_int")],
    },
    "bigint": {
        "fn": lambda n: [(0, "zero"), (-1, "negative")],
    },
    "date": {
        "fn": lambda n: [
            ("2000-02-29", "leap_year"),
            ("9999-12-31", "max_date"),
            ("1900-01-01", "min_date"),
        ],
    },
    "datetime": {
        "fn": lambda n: [
            ("2000-02-29 23:59:59", "leap_year"),
            ("9999-12-31 23:59:59", "max_datetime"),
            ("1900-01-01 00:00:00", "min_datetime"),
        ],
    },
    "bit": {
        "fn": lambda n: [(0, "false"), (1, "true"), (2, "overflow")],
    },
}


class BoundaryValueGenerator:
    def __init__(self, schema_injector=None, mock_generator=None):
        self.schema_injector = schema_injector
        self.mock_generator = mock_generator

    def generate_cases(
        self, table_schema: dict, modified_column: str
    ) -> list[BoundaryTestCase]:
        col_info = table_schema.get(modified_column, {})
        col_type = col_info.get("type", "varchar").lower()
        max_len = col_info.get("max_length", 50)

        cases = []
        boundary_values = self._get_boundary_values(col_type, max_len)

        for value, boundary_type in boundary_values:
            expected = self._predict_behavior(value, col_type, max_len, col_info)
            cases.append(BoundaryTestCase(
                input_value=value,
                boundary_type=boundary_type,
                expected_behavior=expected,
                column=modified_column,
            ))

        return cases

    def generate_all_boundaries(self, table_schema: dict) -> dict[str, list[BoundaryTestCase]]:
        all_cases = {}
        for col_name in table_schema:
            cases = self.generate_cases(table_schema, col_name)
            if cases:
                all_cases[col_name] = cases
        return all_cases

    def _get_boundary_values(self, col_type: str, max_len: int) -> list[tuple]:
        base_type = re.sub(r"\(.*\)", "", col_type).strip().lower()

        rule = BOUNDARY_RULES.get(base_type)
        if rule:
            try:
                return rule["fn"](max_len)
            except Exception:
                return rule["fn"](50)

        return [("", "empty")]

    def _predict_behavior(self, value: Any, col_type: str,
                          max_len: int, col_info: dict) -> str:
        is_nullable = col_info.get("is_nullable", True)

        if value == "" or value is None:
            return "reject" if not is_nullable else "accept"

        if isinstance(value, str) and len(value) > max_len:
            return "truncate"

        if isinstance(value, (int, float)) and value < 0:
            unsigned = col_info.get("unsigned", False)
            return "reject" if unsigned else "accept"

        return "accept"
