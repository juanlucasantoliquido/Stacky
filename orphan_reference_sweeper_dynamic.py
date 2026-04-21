"""
orphan_reference_sweeper_dynamic.py — Dynamic Orphan & Dangling Reference Sweeper.

Checks for orphaned records in child tables where FK may be NOCHECK or absent.

Uso:
    from orphan_reference_sweeper_dynamic import OrphanReferenceSweeper
    sweeper = OrphanReferenceSweeper()
    cases = sweeper.sweep(ticket_folder, conn)
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.orphan_refs")

REF_MAP_FILE = Path(__file__).parent / "data" / "reference_integrity_map.json"

DEFAULT_REFERENCE_MAP = {
    "RDIRE": {"parent": "RCLIE", "fk_field": "RCOD_CLIE", "pk_field": "RCOD_CLIE"},
    "RTELE": {"parent": "RCLIE", "fk_field": "RCOD_CLIE", "pk_field": "RCOD_CLIE"},
    "ROBLG": {"parent": "RCLIE", "fk_field": "RCOD_CLIE", "pk_field": "RCOD_CLIE"},
    "RPAGOS": {"parent": "ROBLG", "fk_field": "RNRO_OBLG", "pk_field": "RNRO_OBLG"},
    "RGARANTIAS": {"parent": "ROBLG", "fk_field": "RNRO_OBLG", "pk_field": "RNRO_OBLG"},
}


@dataclass
class OrphanTestCase:
    table: str
    parent_table: str
    orphan_count: int = 0
    passed: bool = False
    evidence: str = ""


class OrphanReferenceSweeper:
    def __init__(self, ref_map: Optional[dict] = None):
        self._ref_map = ref_map or self._load_ref_map()

    def sweep(self, ticket_folder: str, conn) -> list[OrphanTestCase]:
        affected = self._extract_affected_tables(ticket_folder)
        cases = []

        for table in affected:
            table_upper = table.upper()
            ref = self._ref_map.get(table_upper)
            if not ref:
                continue

            try:
                cursor = conn.cursor()
                query = (
                    f"SELECT COUNT(*) FROM {table_upper} C "
                    f"WHERE NOT EXISTS ("
                    f"SELECT 1 FROM {ref['parent']} P "
                    f"WHERE P.{ref['pk_field']} = C.{ref['fk_field']}"
                    f")"
                )
                cursor.execute(query)
                row = cursor.fetchone()
                orphan_count = row[0] if row else 0

                cases.append(OrphanTestCase(
                    table=table_upper,
                    parent_table=ref["parent"],
                    orphan_count=orphan_count,
                    passed=(orphan_count == 0),
                    evidence=(f"{orphan_count} orphan records in "
                              f"{table_upper}→{ref['parent']}")
                ))

                if orphan_count > 0:
                    logger.warning("[OrphanSweep] %d orphans: %s→%s",
                                    orphan_count, table_upper, ref["parent"])

            except Exception as e:
                cases.append(OrphanTestCase(
                    table=table_upper,
                    parent_table=ref.get("parent", "?"),
                    passed=False,
                    evidence=str(e)[:200]
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

    def _load_ref_map(self) -> dict:
        if REF_MAP_FILE.exists():
            try:
                return json.loads(REF_MAP_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return dict(DEFAULT_REFERENCE_MAP)
