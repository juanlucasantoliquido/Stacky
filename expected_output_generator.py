"""
expected_output_generator.py — Expected Output Generator.

Reads business rules from TAREAS_DESARROLLO.md and applies them to mock data
to generate the test oracle (expected output).

Uso:
    from expected_output_generator import ExpectedOutputGenerator
    gen = ExpectedOutputGenerator()
    expected = gen.calculate(mock_data, ticket_folder)
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger("stacky.expected_output")


@dataclass
class BusinessRule:
    description: str
    condition: str  # simplified condition expression
    action: str     # what should happen
    field: str = ""

    def apply(self, row: dict) -> dict:
        """Apply rule to a data row. Returns modified copy."""
        result = dict(row)
        try:
            if self.condition and self.field:
                # Simple rule evaluation
                if self._matches_condition(row):
                    result[self.field] = self.action
        except Exception:
            pass
        return result

    def _matches_condition(self, row: dict) -> bool:
        if "=" in self.condition:
            parts = self.condition.split("=", 1)
            field_name = parts[0].strip()
            value = parts[1].strip().strip("'\"")
            return str(row.get(field_name, "")) == value
        return True


@dataclass
class ExpectedOutput:
    rows: list[dict] = field(default_factory=list)
    rules_applied: list[str] = field(default_factory=list)


class ExpectedOutputGenerator:
    """
    Reads business rules from ticket artifacts and translates them into
    transformations applicable to mock data.
    """

    RULE_PATTERNS = [
        # "Si CAMPO = 'VALOR', entonces RESULTADO debe ser 'X'"
        re.compile(
            r"[Ss]i\s+(\w+)\s*=\s*['\"]?(\w+)['\"]?\s*,?\s*"
            r"(?:entonces|→)\s+(\w+)\s+debe\s+ser\s+['\"]?(\w+)['\"]?"
        ),
        # "CAMPO no puede ser negativo/NULL"
        re.compile(r"(\w+)\s+no\s+puede\s+ser\s+(negativo|NULL|nulo|vacío)", re.IGNORECASE),
        # "El campo CAMPO debe ser la fecha de proceso"
        re.compile(r"[Ee]l\s+campo\s+(\w+)\s+debe\s+ser\s+(.+?)[\.\n]"),
    ]

    def calculate(self, mock_data: list[dict], ticket_folder: str) -> ExpectedOutput:
        rules = self._extract_business_rules(ticket_folder)
        expected_rows = []

        for row in mock_data:
            transformed = dict(row)
            for rule in rules:
                transformed = rule.apply(transformed)
            expected_rows.append(transformed)

        return ExpectedOutput(
            rows=expected_rows,
            rules_applied=[r.description for r in rules],
        )

    def _extract_business_rules(self, ticket_folder: str) -> list[BusinessRule]:
        folder = Path(ticket_folder)
        rules = []

        for fname in ["TAREAS_DESARROLLO.md", "NOTAS_IMPLEMENTACION.md"]:
            p = folder / fname
            if not p.exists():
                continue
            content = p.read_text(encoding="utf-8", errors="replace")
            rules.extend(self._parse_rules(content))

        return rules

    def _parse_rules(self, content: str) -> list[BusinessRule]:
        rules = []

        # Pattern 1: Si CAMPO = VALOR, entonces RESULTADO = X
        for m in self.RULE_PATTERNS[0].finditer(content):
            rules.append(BusinessRule(
                description=m.group(0),
                condition=f"{m.group(1)}={m.group(2)}",
                action=m.group(4),
                field=m.group(3),
            ))

        # Pattern 2: CAMPO no puede ser negativo/NULL
        for m in self.RULE_PATTERNS[1].finditer(content):
            constraint = m.group(2).lower()
            rules.append(BusinessRule(
                description=m.group(0),
                condition="",
                action=f"not_{constraint}",
                field=m.group(1),
            ))

        return rules
