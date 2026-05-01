"""
orphan_reference_sweeper.py — F-15: Orphan & Dangling Reference Sweeper.

Post-ejecución: detecta registros huérfanos en tablas hijas
(RDIRE sin RCLIE, ROBLG con cliente eliminado) — independientemente
de si las FK están habilitadas o en NOCHECK en SQL Server.

Uso:
    from orphan_reference_sweeper import OrphanReferenceSweeper
    sweeper = OrphanReferenceSweeper()
    cases = sweeper.sweep(ticket_folder, conn)
"""

import logging
import re
from pathlib import Path
from evidence_collector import TestCase

logger = logging.getLogger("stacky.orphan_sweep")

# Map: child_table → {parent_table, fk_field, pk_field}
# Independent of actual FK constraints in SQL Server
REFERENCE_MAP = {
    "RDIRE":      {"parent": "RCLIE",  "fk": "RCOD_CLIE", "pk": "RCOD_CLIE"},
    "RTELE":      {"parent": "RCLIE",  "fk": "RCOD_CLIE", "pk": "RCOD_CLIE"},
    "RMAILS":     {"parent": "RCLIE",  "fk": "RCOD_CLIE", "pk": "RCOD_CLIE"},
    "ROBLG":      {"parent": "RCLIE",  "fk": "RCOD_CLIE", "pk": "RCOD_CLIE"},
    "RPAGOS":     {"parent": "ROBLG",  "fk": "RNRO_OBLG", "pk": "RNRO_OBLG"},
    "RGARANTIAS": {"parent": "ROBLG",  "fk": "RNRO_OBLG", "pk": "RNRO_OBLG"},
    "RDEUDA":     {"parent": "ROBLG",  "fk": "RNRO_OBLG", "pk": "RNRO_OBLG"},
}


class OrphanReferenceSweeper:
    """Detects orphan records regardless of FK constraint status."""

    def __init__(self, custom_refs: dict = None):
        self._refs = {**REFERENCE_MAP}
        if custom_refs:
            self._refs.update(custom_refs)

    def sweep(self, ticket_folder: str, conn) -> list[TestCase]:
        affected = self._extract_affected_tables(ticket_folder)
        cases = []

        for table in affected:
            table_upper = table.upper()
            ref = self._refs.get(table_upper)
            if not ref:
                continue

            query = (
                f"SELECT COUNT(*) FROM {table_upper} C "
                f"WHERE NOT EXISTS ("
                f"SELECT 1 FROM {ref['parent']} P "
                f"WHERE P.{ref['pk']} = C.{ref['fk']}"
                f")"
            )
            try:
                cursor = conn.cursor()
                cursor.execute(query)
                orphan_count = cursor.fetchone()[0]
                cases.append(TestCase(
                    name=f"Orphan check: {table_upper} → {ref['parent']}",
                    passed=(orphan_count == 0),
                    evidence=(
                        f"{orphan_count} registros huérfanos en {table_upper} "
                        f"(sin padre en {ref['parent']}.{ref['pk']})"
                        if orphan_count > 0 else "OK — sin huérfanos"
                    ),
                    category="orphan_reference",
                ))
            except Exception as e:
                cases.append(TestCase(
                    name=f"Orphan check: {table_upper} → {ref['parent']}",
                    passed=False,
                    evidence=f"Error: {e}",
                    category="orphan_reference",
                ))
                logger.warning("[Orphan] Error en check %s→%s: %s", table_upper, ref['parent'], e)

        if not cases:
            logger.info("[Orphan] No se encontraron tablas hijas afectadas")

        passed = sum(1 for c in cases if c.passed)
        logger.info("[Orphan] Sweep completo: %d/%d checks pasaron", passed, len(cases))
        return cases

    def sweep_all_known_refs(self, conn) -> list[TestCase]:
        """Run orphan checks on ALL known reference pairs (full sweep)."""
        cases = []
        for table, ref in self._refs.items():
            query = (
                f"SELECT COUNT(*) FROM {table} C "
                f"WHERE NOT EXISTS ("
                f"SELECT 1 FROM {ref['parent']} P "
                f"WHERE P.{ref['pk']} = C.{ref['fk']}"
                f")"
            )
            try:
                cursor = conn.cursor()
                cursor.execute(query)
                orphan_count = cursor.fetchone()[0]
                cases.append(TestCase(
                    name=f"Orphan check: {table} → {ref['parent']}",
                    passed=(orphan_count == 0),
                    evidence=f"{orphan_count} huérfanos" if orphan_count > 0 else "OK",
                    category="orphan_reference",
                ))
            except Exception as e:
                cases.append(TestCase(
                    name=f"Orphan check: {table} → {ref['parent']}",
                    passed=False,
                    evidence=f"Error: {e}",
                    category="orphan_reference",
                ))
        return cases

    def _extract_affected_tables(self, ticket_folder: str) -> list[str]:
        tables = set()
        table_pattern = re.compile(
            r'\b(RCLIE|RDIRE|RTELE|RMAILS|RGARANTIAS|ROBLG|RDEUDA|RPAGOS)\b',
            re.IGNORECASE
        )
        for md_file in ["ARQUITECTURA_SOLUCION.md", "TAREAS_DESARROLLO.md", "DEV_COMPLETADO.md"]:
            fpath = Path(ticket_folder) / md_file
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8", errors="replace")
                tables.update(m.upper() for m in table_pattern.findall(content))
        return sorted(tables)
