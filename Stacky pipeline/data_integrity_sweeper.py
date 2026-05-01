"""
data_integrity_sweeper.py — E-08: Data Integrity Sweep.

Post-ejecución: verifica FK, NOT NULL y rangos en tablas afectadas.
Trabaja con SQL Server (T-SQL).

Uso:
    from data_integrity_sweeper import DataIntegritySweeper
    sweeper = DataIntegritySweeper()
    cases = sweeper.sweep(ticket_folder, conn)
"""

import logging
import re
from pathlib import Path
from evidence_collector import TestCase

logger = logging.getLogger("stacky.data_integrity")

# Checks de integridad por tabla (SQL Server / T-SQL)
INTEGRITY_CHECKS = {
    "RPAGOS": [
        ("FK_CLIENTE", "SELECT COUNT(*) FROM RPAGOS P WHERE NOT EXISTS (SELECT 1 FROM RCLIE C WHERE C.RCOD_CLIE = P.RCOD_CLIE)"),
        ("NO_NEG_IMPORTE", "SELECT COUNT(*) FROM RPAGOS WHERE RIMPORTE < 0"),
        ("FECHA_HOY", "SELECT COUNT(*) FROM RPAGOS WHERE CAST(RFEC_PAGO AS DATE) != CAST(GETDATE() AS DATE) AND RFEC_PAGO IS NOT NULL"),
    ],
    "RDEUDA": [
        ("NO_NULL_SALDO", "SELECT COUNT(*) FROM RDEUDA WHERE RSALDO IS NULL"),
        ("FK_MONEDA", "SELECT COUNT(*) FROM RDEUDA WHERE RCOD_MONEDA NOT IN ('PEN','USD','EUR')"),
    ],
    "ROBLG": [
        ("FK_CLIENTE", "SELECT COUNT(*) FROM ROBLG O WHERE NOT EXISTS (SELECT 1 FROM RCLIE C WHERE C.RCOD_CLIE = O.RCOD_CLIE)"),
        ("NO_NULL_ESTADO", "SELECT COUNT(*) FROM ROBLG WHERE RCOD_ESTADO IS NULL"),
    ],
    "RCLIE": [
        ("NO_NULL_NOMBRE", "SELECT COUNT(*) FROM RCLIE WHERE RNOMBRE IS NULL"),
        ("NO_NULL_ESTADO", "SELECT COUNT(*) FROM RCLIE WHERE RCOD_ESTADO IS NULL"),
    ],
    "RDIRE": [
        ("FK_CLIENTE", "SELECT COUNT(*) FROM RDIRE D WHERE NOT EXISTS (SELECT 1 FROM RCLIE C WHERE C.RCOD_CLIE = D.RCOD_CLIE)"),
    ],
    "RTELE": [
        ("FK_CLIENTE", "SELECT COUNT(*) FROM RTELE T WHERE NOT EXISTS (SELECT 1 FROM RCLIE C WHERE C.RCOD_CLIE = T.RCOD_CLIE)"),
    ],
    "RGARANTIAS": [
        ("FK_OBLIGACION", "SELECT COUNT(*) FROM RGARANTIAS G WHERE NOT EXISTS (SELECT 1 FROM ROBLG O WHERE O.RNRO_OBLG = G.RNRO_OBLG)"),
    ],
}


class DataIntegritySweeper:
    """Verifica integridad de datos post-ejecución en SQL Server."""

    def __init__(self, custom_checks: dict = None):
        self._checks = {**INTEGRITY_CHECKS}
        if custom_checks:
            self._checks.update(custom_checks)

    def sweep(self, ticket_folder: str, conn) -> list[TestCase]:
        affected = self._extract_affected_tables(ticket_folder)
        cases = []

        for table in affected:
            table_upper = table.upper()
            checks = self._checks.get(table_upper, [])
            for check_name, query in checks:
                try:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    count = cursor.fetchone()[0]
                    cases.append(TestCase(
                        name=f"[{table_upper}] {check_name}",
                        passed=(count == 0),
                        evidence=f"Violaciones encontradas: {count}" if count > 0 else "OK",
                        category="data_integrity",
                    ))
                except Exception as e:
                    cases.append(TestCase(
                        name=f"[{table_upper}] {check_name}",
                        passed=False,
                        evidence=f"Error ejecutando check: {e}",
                        category="data_integrity",
                    ))
                    logger.warning("[Integrity] Error en check %s.%s: %s", table_upper, check_name, e)

        if not cases:
            logger.info("[Integrity] No se encontraron tablas afectadas para verificar")
        else:
            passed = sum(1 for c in cases if c.passed)
            logger.info("[Integrity] Sweep completo: %d/%d checks pasaron", passed, len(cases))

        return cases

    def _extract_affected_tables(self, ticket_folder: str) -> list[str]:
        tables = set()
        table_pattern = re.compile(
            r'\b(RCLIE|RDIRE|RTELE|RMAILS|RGARANTIAS|ROBLG|RDEUDA|RPAGOS|IN_\w+)\b',
            re.IGNORECASE
        )
        for md_file in ["ARQUITECTURA_SOLUCION.md", "TAREAS_DESARROLLO.md", "DEV_COMPLETADO.md"]:
            fpath = Path(ticket_folder) / md_file
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8", errors="replace")
                tables.update(m.upper() for m in table_pattern.findall(content))
        return sorted(tables)
