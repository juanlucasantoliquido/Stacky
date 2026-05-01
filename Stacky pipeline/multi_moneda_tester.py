"""
multi_moneda_tester.py — Multi-Moneda Test.

Tests financial calculations across PEN, USD, EUR currencies for rounding
and exchange rate correctness.

Uso:
    from multi_moneda_tester import MultiMonedaTester
    tester = MultiMonedaTester(config)
    cases = tester.run(ticket_folder, config)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.multi_moneda")

MONEDAS = [
    {"cod": "PEN", "tipo_cambio": 1.0, "decimales": 2},
    {"cod": "USD", "tipo_cambio": 3.75, "decimales": 2},
    {"cod": "EUR", "tipo_cambio": 4.10, "decimales": 2},
]


@dataclass
class MonedaTestCase:
    moneda: str
    expected: float
    actual: float
    passed: bool


class MultiMonedaTester:
    TOLERANCE = 0.01  # 1 centavo

    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None,
                 expected_gen=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.expected_gen = expected_gen
        self.db = db

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> list[MonedaTestCase]:
        if not self._involves_importes(ticket_folder):
            return []

        if not self.batch_executor or not self.db:
            return []

        cases = []
        for moneda in MONEDAS:
            try:
                case = self._test_moneda(ticket_folder, moneda)
                cases.append(case)
            except Exception as e:
                cases.append(MonedaTestCase(
                    moneda=moneda["cod"],
                    expected=0.0,
                    actual=0.0,
                    passed=False,
                ))
                logger.error("[MultiMoneda] Error for %s: %s", moneda["cod"], e)
            finally:
                if self.db:
                    try:
                        self.db.rollback()
                    except Exception:
                        pass

        return cases

    def _test_moneda(self, ticket_folder: str, moneda: dict) -> MonedaTestCase:
        mock = None
        if self.mock_generator and hasattr(self.mock_generator, "generate_with_moneda"):
            mock = self.mock_generator.generate_with_moneda(
                moneda["cod"],
                amount=100.00,
                tipo_cambio=moneda["tipo_cambio"]
            )
        else:
            mock = {"RCOD_MONEDA": moneda["cod"], "RIMPORTE": 100.00}

        if self.db:
            self.db.insert(mock)

        self.batch_executor.run_minimal(ticket_folder)

        # Calculate expected
        expected_amt = 100.00 * moneda["tipo_cambio"]
        if self.expected_gen and hasattr(self.expected_gen, "calculate_amount"):
            expected_amt = self.expected_gen.calculate_amount(mock, moneda)

        # Read actual
        actual_amt = 0.0
        if self.db and hasattr(self.db, "read_result"):
            result_row = self.db.read_result(mock.get("id"))
            actual_amt = result_row.get("RIMPORTE", 0.0) if result_row else 0.0

        return MonedaTestCase(
            moneda=moneda["cod"],
            expected=round(expected_amt, moneda["decimales"]),
            actual=round(actual_amt, moneda["decimales"]) if actual_amt else 0.0,
            passed=(abs(actual_amt - expected_amt) <= self.TOLERANCE) if actual_amt else False,
        )

    def _involves_importes(self, ticket_folder: str) -> bool:
        folder = Path(ticket_folder)
        for fname in ["TAREAS_DESARROLLO.md", "ARQUITECTURA_SOLUCION.md"]:
            p = folder / fname
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="replace").lower()
                if any(k in content for k in [
                    "importe", "monto", "moneda", "tipo_cambio",
                    "decimal", "currency", "rpagos"
                ]):
                    return True
        return False
