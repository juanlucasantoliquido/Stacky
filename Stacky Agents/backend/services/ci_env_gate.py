"""ci_env_gate.py — Plan 260 F4/F5.

F4: veredicto de disparo (evaluate_readiness) — PURO: sin red, sin I/O, sin
datetime.now. La UNICA llamada de red del gate (resolve contra el proveedor,
con presupuesto de latencia) vive en api/ci.py (_evaluar_readiness), no acá.

F5: gate de secretos en los caminos que escriben YAML (evaluar_gate_secretos)
+ el traductor de vocabulario de proveedor entre los dos subsistemas del repo
(§4.4): la matriz de entornos habla "azure_devops"/"gitlab"; el auditor y el
linter hablan "ado"/"gitlab".
"""
from __future__ import annotations

from dataclasses import dataclass

VERDICTS = ("ok", "bloquea", "advierte", "degradado")
SOURCES_READINESS = ("calculado", "preview_reusado")     # valores CERRADOS

GATE_BUDGET_S = 1.5   # presupuesto DURO de espera REAL al proveedor (KPI-7)


@dataclass(frozen=True)
class Readiness:
    verdict: str
    pending_count: int          # celdas 'falta'  (evidencia POSITIVA de faltante)
    unknown_count: int          # celdas 'manual' (el proveedor no puede saberlo)
    pending_fingerprint: str
    missing: tuple               # tuple[(name, environment), ...] — SOLO nombres, jamas valores
    reasons: tuple
    resolved: bool                # True SOLO si se consulto al proveedor de verdad
    source: str = "calculado"     # uno de SOURCES_READINESS
    elapsed_ms: int = 0           # ms REALES que el gate espero por el proveedor


def evaluate_readiness(matrix, *, resolved: bool,
                       source: str = "calculado", elapsed_ms: int = 0) -> Readiness:
    """PURA. Orden de evaluación LITERAL, no negociable:

    1. `resolved is False` -> degradado (nunca bloquear por ignorancia).
    2. pending_count > 0   -> bloquea (evidencia POSITIVA de faltante).
    3. unknown_count > 0   -> advierte.
    4. si no               -> ok.
    """
    missing = tuple((c.requirement, c.environment) for c in matrix.cells if c.state == "falta")
    unknown_count = sum(1 for c in matrix.cells if c.state == "manual")

    if not resolved:
        verdict = "degradado"
    elif matrix.pending_count > 0:
        verdict = "bloquea"
    elif unknown_count > 0:
        verdict = "advierte"
    else:
        verdict = "ok"

    reasons = tuple(sorted({c.note for c in matrix.cells if c.note}))
    return Readiness(
        verdict=verdict,
        pending_count=matrix.pending_count,
        unknown_count=unknown_count,
        pending_fingerprint=matrix.pending_fingerprint,
        missing=missing,
        reasons=reasons,
        resolved=resolved,
        source=source,
        elapsed_ms=elapsed_ms,
    )


def to_rules_provider(p: str) -> str:
    """pipeline_environments ('azure_devops'|'gitlab') -> vocabulario de
    reglas del auditor/linter ('ado'|'gitlab'). Nunca en línea en un endpoint."""
    return "ado" if p in ("azure_devops", "ado") else "gitlab"


# ── F5 — ningún camino escribe un YAML con un secreto literal ───────────────
# Motor: services.cicd_audit_core.audit_yaml  (SEC* + OPT*)
SECRET_BLOCKING_AUDIT = ("SEC001",)

# Motor: services.pipeline_lint.lint_yaml  (PL001..PL014)
# OJO: son SEV_WARNING. Se filtra POR CODIGO, jamas por severidad: filtrar por
# severity=="error" las descarta a las tres y el gate queda inerte (bug del v1).
# PL013 NO bloquea a propósito: dice "el secreto no está en la caja fuerte",
# que es justo lo que este plan resuelve, y degrada a unknown sin known_variables.
SECRET_BLOCKING_LINT = ("PL012", "PL014")


def evaluar_gate_secretos(yaml_text: str, *, provider: str) -> tuple:
    """-> (duros, auditado). PURO respecto de red; llama a los DOS motores.

    provider viene en vocabulario de reglas ('ado'|'gitlab') — ver to_rules_provider.
    `auditado` es False cuando el auditor NO analizó el documento (YAML > 512 KB
    o no parseable -> AUD000; o no es un dict); en ese caso NO se commitea,
    porque un gate que no vio nada no es un gate verde.
    """
    import yaml as _yaml

    from services.cicd_audit_core import audit_yaml
    from services.pipeline_lint import lint_yaml

    rep = audit_yaml(yaml_text, provider=provider)
    _no_analizado = any(f.code == "AUD000" for f in rep.findings)
    try:
        _es_dict = isinstance(_yaml.safe_load(yaml_text), dict)
    except Exception:
        _es_dict = False
    auditado = (not _no_analizado) and _es_dict
    if not auditado:
        return (), False

    duros = [(f.code, f.location, f.message) for f in rep.findings
             if f.code in SECRET_BLOCKING_AUDIT]

    lint_rep = lint_yaml(yaml_text, provider)
    duros.extend((f.code, f.node or "(documento)", f.message) for f in lint_rep.findings
                if f.code in SECRET_BLOCKING_LINT)

    return tuple(duros), True
