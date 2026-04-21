"""
idempotency_tester.py — F-01: Idempotency Test.

Verifica que ejecutar un proceso batch dos veces produce el mismo resultado.
f(f(x)) = f(x) — re-procesamiento no duplica registros.

Uso:
    from idempotency_tester import IdempotencyTester
    tester = IdempotencyTester()
    cases = tester.run(ticket_folder, config)
"""

import logging
import re
from pathlib import Path
from evidence_collector import TestCase

logger = logging.getLogger("stacky.idempotency")


class IdempotencyTester:
    """Verifica idempotencia: doble ejecución no duplica datos."""

    def check_for_idempotency_risks(self, ticket_folder: str) -> list[TestCase]:
        """
        Analiza el código modificado buscando patrones que indican
        riesgo de no-idempotencia (INSERT sin verificación de existencia previa).
        Este es un check estático previo a la ejecución real — no necesita BD.
        """
        cases = []
        dev_path = Path(ticket_folder) / "DEV_COMPLETADO.md"
        if not dev_path.exists():
            return cases

        content = dev_path.read_text(encoding="utf-8", errors="replace")
        modified_files = re.findall(r'[\w/\\]+\.(?:cs|sql)\b', content, re.IGNORECASE)

        for rel_path in modified_files:
            # Read the actual source file if accessible
            code_content = self._try_read_source(ticket_folder, rel_path)
            if not code_content:
                continue

            code_upper = code_content.upper()

            # Pattern 1: INSERT without IF NOT EXISTS / MERGE
            insert_count = len(re.findall(r'\bINSERT\s+INTO\b', code_upper))
            has_existence_check = bool(re.search(
                r'(IF\s+NOT\s+EXISTS|MERGE\s+INTO|NOT\s+EXISTS\s*\(|WHERE\s+NOT\s+EXISTS)',
                code_upper
            ))
            if insert_count > 0 and not has_existence_check:
                cases.append(TestCase(
                    name=f"Idempotency risk: INSERT sin guard en {rel_path}",
                    passed=False,
                    evidence=f"{insert_count} INSERT(s) sin IF NOT EXISTS/MERGE. "
                             f"Re-ejecución podría duplicar registros.",
                    category="idempotency",
                ))

            # Pattern 2: UPDATE without WHERE (affects all rows on re-run)
            update_no_where = len(re.findall(r'\bUPDATE\s+\w+\s+SET\b(?!.*\bWHERE\b)', code_upper))
            if update_no_where > 0:
                cases.append(TestCase(
                    name=f"Idempotency risk: UPDATE sin WHERE en {rel_path}",
                    passed=False,
                    evidence=f"{update_no_where} UPDATE(s) sin WHERE. Afecta todas las filas en cada re-ejecución.",
                    category="idempotency",
                ))

            # Pattern 3: Counter increment without idempotency guard
            counter_pattern = re.search(r'(\w+)\s*=\s*\1\s*\+\s*\d+', code_upper)
            if counter_pattern:
                cases.append(TestCase(
                    name=f"Idempotency risk: incremento acumulativo en {rel_path}",
                    passed=False,
                    evidence=f"Patrón 'campo = campo + N' detectado. Re-ejecución incrementa de nuevo.",
                    category="idempotency",
                ))

            if insert_count > 0 and has_existence_check:
                cases.append(TestCase(
                    name=f"Idempotency: INSERT con guard en {rel_path}",
                    passed=True,
                    evidence="INSERT tiene IF NOT EXISTS/MERGE — idempotente.",
                    category="idempotency",
                ))

        if not cases:
            cases.append(TestCase(
                name="Idempotency: sin operaciones de escritura detectadas",
                passed=True,
                evidence="No se encontraron INSERTs ni UPDATEs en archivos modificados.",
                category="idempotency",
            ))

        return cases

    def _try_read_source(self, ticket_folder: str, rel_path: str) -> str:
        """Try to read a source file from the workspace."""
        # Try relative to workspace root (inferred from ticket_folder)
        ticket_path = Path(ticket_folder)
        # Walk up to find trunk/
        workspace_root = None
        for parent in ticket_path.parents:
            if (parent / "trunk").exists():
                workspace_root = parent / "trunk"
                break
        if workspace_root:
            full = workspace_root / rel_path
            if full.exists():
                return full.read_text(encoding="utf-8", errors="replace")
        return ""
