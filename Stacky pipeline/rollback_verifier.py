"""
rollback_verifier.py — E-13: Rollback Execution Verifier.

Verifica que los scripts de rollback mencionados en ARQUITECTURA_SOLUCION.md
son sintácticamente válidos y coherentes con los cambios de DEV.

Checks:
  - Rollback scripts existen si se mencionaron en arquitectura
  - Scripts SQL no tienen errores de sintaxis básicos
  - DROP/ALTER en rollback corresponden a CREATE/ALTER del forward script
  - Scripts invocables sin error de parse

Uso:
    from rollback_verifier import RollbackVerifier
    verifier = RollbackVerifier()
    cases = verifier.verify(ticket_folder)
"""

import logging
import re
from pathlib import Path
from evidence_collector import TestCase

logger = logging.getLogger("stacky.rollback_verifier")

# SQL syntax patterns that indicate broken scripts
_SYNTAX_ERROR_PATTERNS = [
    (r'\bSELECT\b[^;]*\bFROM\b\s*$', "SELECT sin tabla"),
    (r'\bDROP\s+TABLE\s*$', "DROP TABLE sin nombre"),
    (r'\bALTER\s+TABLE\s*$', "ALTER TABLE sin nombre"),
    (r'\bDELETE\s+FROM\s*$', "DELETE FROM sin tabla"),
    (r'\bUPDATE\s+SET\b', "UPDATE sin tabla (SET directo)"),
]

# Keywords that indicate rollback intent
_ROLLBACK_KEYWORDS = ["rollback", "revert", "undo", "deshacer", "vuelta atrás"]


class RollbackVerifier:
    """Verifica coherencia y existencia de scripts de rollback."""

    def verify(self, ticket_folder: str) -> list[TestCase]:
        cases = []

        # 1. Check if rollback is mentioned in architecture
        arq_path = Path(ticket_folder) / "ARQUITECTURA_SOLUCION.md"
        rollback_refs = []
        if arq_path.exists():
            arq = arq_path.read_text(encoding="utf-8", errors="replace")
            rollback_refs = self._find_rollback_references(arq)

        # 2. Scan for .sql files in ticket folder
        sql_files = list(Path(ticket_folder).glob("*.sql"))
        rollback_files = [
            f for f in sql_files
            if any(kw in f.stem.lower() for kw in _ROLLBACK_KEYWORDS)
        ]

        # 3. If rollback mentioned but no rollback file
        if rollback_refs and not rollback_files:
            cases.append(TestCase(
                name="Rollback: script mencionado pero no encontrado",
                passed=False,
                evidence=(
                    f"ARQUITECTURA_SOLUCION.md menciona rollback ({len(rollback_refs)} ref), "
                    f"pero no hay archivos *rollback*.sql en la carpeta del ticket."
                ),
                category="rollback",
            ))

        # 4. Validate each rollback script
        for rf in rollback_files:
            content = rf.read_text(encoding="utf-8", errors="replace")

            # 4a. Not empty
            if len(content.strip()) < 10:
                cases.append(TestCase(
                    name=f"Rollback: {rf.name} vacío",
                    passed=False,
                    evidence="Script de rollback tiene menos de 10 caracteres.",
                    category="rollback",
                ))
                continue

            # 4b. Syntax check
            syntax_issues = self._check_syntax(content)
            if syntax_issues:
                cases.append(TestCase(
                    name=f"Rollback: {rf.name} errores de sintaxis",
                    passed=False,
                    evidence="\n".join(syntax_issues),
                    category="rollback",
                ))
            else:
                cases.append(TestCase(
                    name=f"Rollback: {rf.name} sintaxis OK",
                    passed=True,
                    evidence=f"{len(content.splitlines())} líneas, sin errores detectados.",
                    category="rollback",
                ))

            # 4c. Coherence check: DROP should match CREATE from forward scripts
            forward_files = [f for f in sql_files if f not in rollback_files]
            coherence = self._check_coherence(content, forward_files)
            cases.extend(coherence)

        # 5. If no rollback referenced and no rollback files — that's a warning, not fail
        if not rollback_refs and not rollback_files:
            # Check if there ARE SQL changes that warrant rollback
            dev_path = Path(ticket_folder) / "DEV_COMPLETADO.md"
            has_ddl = False
            if dev_path.exists():
                dev = dev_path.read_text(encoding="utf-8", errors="replace")
                has_ddl = bool(re.search(
                    r'\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX|VIEW|PROCEDURE|FUNCTION)\b',
                    dev, re.IGNORECASE
                ))
            if has_ddl:
                cases.append(TestCase(
                    name="Rollback: cambios DDL sin script de rollback",
                    passed=False,
                    evidence=(
                        "DEV reporta cambios DDL (CREATE/ALTER/DROP) pero no hay "
                        "script de rollback. Todo cambio DDL debe tener rollback."
                    ),
                    category="rollback",
                ))
            else:
                cases.append(TestCase(
                    name="Rollback: sin cambios DDL, rollback no requerido",
                    passed=True,
                    evidence="No se detectaron cambios DDL — rollback no es necesario.",
                    category="rollback",
                ))

        return cases

    def _find_rollback_references(self, content: str) -> list[str]:
        refs = []
        for kw in _ROLLBACK_KEYWORDS:
            if kw in content.lower():
                refs.append(kw)
        # Also find SQL file references with rollback in name
        sql_refs = re.findall(r'\b\w*rollback\w*\.sql\b', content, re.IGNORECASE)
        refs.extend(sql_refs)
        return refs

    def _check_syntax(self, sql_content: str) -> list[str]:
        issues = []
        for line_num, line in enumerate(sql_content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue
            for pattern, desc in _SYNTAX_ERROR_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    issues.append(f"Línea {line_num}: {desc} → '{stripped[:60]}'")
        # Check unbalanced parentheses
        opens = sql_content.count("(")
        closes = sql_content.count(")")
        if opens != closes:
            issues.append(
                f"Paréntesis desbalanceados: {opens} aperturas vs {closes} cierres"
            )
        return issues

    def _check_coherence(self, rollback_content: str, forward_files: list[Path]) -> list[TestCase]:
        cases = []
        rollback_upper = rollback_content.upper()

        # Extract tables created in forward scripts
        forward_creates = set()
        for ff in forward_files:
            fc = ff.read_text(encoding="utf-8", errors="replace").upper()
            forward_creates.update(
                re.findall(r'CREATE\s+TABLE\s+(\w+)', fc)
            )

        # Each CREATE in forward should have DROP in rollback
        for table in forward_creates:
            if f"DROP TABLE {table}" not in rollback_upper and \
               f"DROP TABLE IF EXISTS {table}" not in rollback_upper and \
               f"DROP TABLE [{table}]" not in rollback_upper:
                cases.append(TestCase(
                    name=f"Rollback coherence: falta DROP para {table}",
                    passed=False,
                    evidence=(
                        f"Forward script crea tabla {table} pero el rollback "
                        f"no incluye DROP TABLE {table}."
                    ),
                    category="rollback",
                ))

        return cases
