"""
findings — Modelo común de hallazgos para todos los linters de Fase 2.

Un Finding es una violación detectada por un linter. Tiene siempre:
  - rule_id      : identificador estable (R1..R10, PAC-DALC-1, SCOPE, etc.).
  - severity     : BLOQUEANTE | ADVERTENCIA | SUGERENCIA.
  - file         : path relativo al repo.
  - line         : número de línea en el archivo nuevo (post-cambio).
  - snippet      : línea de código exacta o fragmento mínimo de evidencia.
  - fix_hint     : una línea con cómo arreglarlo.
  - anchor       : link al archivo de reglas (ej: 'core_rules.md#r4-sql-parametrizado').

Salida JSON: cada linter devuelve `[Finding.to_dict() for f in findings]`.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum


class Severity(str, Enum):
    BLOQUEANTE = "BLOQUEANTE"
    ADVERTENCIA = "ADVERTENCIA"
    SUGERENCIA = "SUGERENCIA"


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    file: str
    line: int
    snippet: str
    fix_hint: str = ""
    anchor: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # Severity es Enum — exportar como string
        d["severity"] = self.severity.value if isinstance(self.severity, Severity) else self.severity
        return d


def is_blocking(findings: list[Finding]) -> bool:
    """¿Hay al menos un BLOQUEANTE en la lista?"""
    return any(f.severity == Severity.BLOQUEANTE for f in findings)


def group_by_rule(findings: list[Finding]) -> dict[str, list[Finding]]:
    out: dict[str, list[Finding]] = {}
    for f in findings:
        out.setdefault(f.rule_id, []).append(f)
    return out
