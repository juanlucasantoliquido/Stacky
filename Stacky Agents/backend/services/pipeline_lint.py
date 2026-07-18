"""services/pipeline_lint.py — Plan 186. Lint determinista de pipelines ADO/GitLab.

PURO: sin red, sin disco, sin config. Recibe texto y devuelve LintReport.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

ENGINE_VERSION = "186.1"

SEV_ERROR = "error"
SEV_WARNING = "warning"
SEV_INFO = "info"

# C9 — por encima de este tamaño de YAML no se adjuntan new_yaml de fixes (payload acotado)
MAX_YAML_BYTES_FOR_FIXES = 200_000


@dataclass(frozen=True)
class LintFix:
    description: str        # es-AR, 1 línea, imperativo ("Renombrar el stage duplicado a ...")
    new_yaml: str           # YAML COMPLETO corregido (cirugía de líneas, nunca re-dump)


@dataclass(frozen=True)
class LintFinding:
    code: str               # "PL001".."PL014"
    severity: str           # SEV_ERROR | SEV_WARNING | SEV_INFO
    message: str            # es-AR llano, sin jerga
    line: int | None = None  # 1-based sobre el YAML fuente; None = global
    node: str | None = None  # "stage:Build" | "job:test" | "var:MY_TOKEN" | None
    fix: LintFix | None = None


@dataclass(frozen=True)
class LintReport:
    ok: bool                        # True ⇔ counts["error"] == 0
    findings: tuple  # tuple[LintFinding, ...]
    counts: dict                    # {"error": n, "warning": n, "info": n}
    engine_version: str
    duration_ms: float
    fixes_omitted: bool = False     # C9 — True si el YAML superó MAX_YAML_BYTES_FOR_FIXES

    def to_dict(self) -> dict:
        return asdict(self)


def lint_yaml(yaml_text: str, provider: str,
              known_variables: list | None = None) -> LintReport:
    """provider: "ado" | "gitlab". known_variables: nombres de la caja fuerte 94
    (los inyecta el ENDPOINT si la UI los mandó; el servicio NO llama a la red).
    F0: devuelve reporte vacío ok=True. F1-F2 agregan reglas."""
    t0 = time.perf_counter()
    findings: list = []
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        counts[f.severity] += 1
    return LintReport(
        ok=counts["error"] == 0,
        findings=tuple(findings),
        counts=counts,
        engine_version=ENGINE_VERSION,
        duration_ms=(time.perf_counter() - t0) * 1000.0,
    )
