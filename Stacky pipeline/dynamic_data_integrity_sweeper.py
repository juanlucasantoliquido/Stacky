"""
dynamic_data_integrity_sweeper.py — Post-execution data integrity checks.

Runs FK, NOT NULL, range, and date checks on affected tables after batch execution.

Uso:
    from dynamic_data_integrity_sweeper import DynamicDataIntegritySweeper
    sweeper = DynamicDataIntegritySweeper()
    cases = sweeper.sweep(ticket_folder, conn)
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.data_integrity")

CHECKS_FILE = Path(__file__).parent / "data" / "integrity_checks.json"

DEFAULT_CHECKS = {
    "RPAGOS": [
        ("FK_CLIENTE", "SELECT COUNT(*) FROM RPAGOS P WHERE NOT EXISTS (SELECT 1 FROM RCLIE C WHERE C.RCOD_CLIE = P.RCOD_CLIE)"),
        ("NO_NEG_IMPORTE", "SELECT COUNT(*) FROM RPAGOS WHERE RIMPORTE < 0"),
        ("FECHA_HOY", "SELECT COUNT(*) FROM RPAGOS WHERE CAST(RFEC_PAGO AS DATE) != CAST(GETDATE() AS DATE) AND RFEC_PAGO IS NOT NULL"),
    ],
    "RDEUDA": [
        ("NO_NULL_SALDO", "SELECT COUNT(*) FROM RDEUDA WHERE RSALDO IS NULL"),
        ("FK_MONEDA", "SELECT COUNT(*) FROM RDEUDA WHERE RCOD_MONEDA NOT IN ('PEN','USD','EUR')"),
    ],
}


@dataclass
class IntegrityTestCase:
    table: str
    check: str
    passed: bool
    violation_count: int = 0


class DynamicDataIntegritySweeper:
    def __init__(self, checks: Optional[dict] = None):
        self._checks = checks or self._load_checks()

    def sweep(self, ticket_folder: str, conn) -> list[IntegrityTestCase]:
        affected_tables = self._extract_affected_tables(ticket_folder)
        cases = []

        for table in affected_tables:
            table_upper = table.upper()
            checks = self._checks.get(table_upper, [])
            for check_name, query in checks:
                try:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    row = cursor.fetchone()
                    count = row[0] if row else 0
                    cases.append(IntegrityTestCase(
                        table=table_upper,
                        check=check_name,
                        passed=(count == 0),
                        violation_count=count,
                    ))
                    if count > 0:
                        logger.warning("[Integrity] %s.%s: %d violations",
                                        table_upper, check_name, count)
                except Exception as e:
                    logger.error("[Integrity] Failed %s.%s: %s",
                                  table_upper, check_name, e)
                    cases.append(IntegrityTestCase(
                        table=table_upper, check=check_name,
                        passed=False, violation_count=-1,
                    ))

        return cases

    def _extract_affected_tables(self, ticket_folder: str) -> list[str]:
        folder = Path(ticket_folder)
        tables = set()
        for fname in ["TAREAS_DESARROLLO.md", "ARQUITECTURA_SOLUCION.md"]:
            p = folder / fname
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r"\b(R[A-Z]{3,}[A-Z0-9_]*)\b", content):
                    tables.add(m.group(1))
        return list(tables)

    def _load_checks(self) -> dict:
        if CHECKS_FILE.exists():
            try:
                data = json.loads(CHECKS_FILE.read_text(encoding="utf-8"))
                # Convert from JSON format to tuple list
                result = {}
                for table, checks in data.items():
                    result[table] = [(c["name"], c["query"]) for c in checks]
                return result
            except Exception:
                pass
        return dict(DEFAULT_CHECKS)
