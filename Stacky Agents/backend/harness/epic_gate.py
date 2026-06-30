"""Plan 51 — Gates correctivos deterministas de épica.

Funciones PURAS sobre el HTML ya extraído de la épica. Sin LLM, sin red, sin
reloj, sin locale, sin datos personales. Determinismo total. Reusa los
detectores del plan 50 (importados lazy desde api.tickets) y agrega la
CLASIFICACIÓN de severidad que decide pasar/reparar/degradar, y el diff contra
el catálogo.

Las 3 runtimes importan este módulo idéntico. El WIRING del pase correctivo
inline es Claude-CLI-only (ver claude_code_cli_runner.py); Codex/Copilot
degradan a needs_review (ver Plan 51 §3 guardarraíl 7).
"""
from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple


class GateDecision(str, Enum):
    PASS = "pass"                    # épica verde: publicar sin tocar
    REPAIR = "repair"                # defecto reparable: pedir UN pase correctivo
    NEEDS_REVIEW = "needs_review"    # defecto no reparable inline o catálogo inventado


class GateVerdict(NamedTuple):
    decision: GateDecision
    structural_defects: list   # códigos string deterministas, sorted
    catalog_unknown: list      # nombres de procesos inventados, sorted
    blocking: bool             # True si NO debe autopublicar tal cual
    regression_defects: list = []  # Plan 56 F3: defectos de regresión detectados


# ── F1 — clasificador puro de severidad ──────────────────────────────────────
# Mapea el TEXTO del warning del plan 50 (_structural_epic_warnings) → código
# canónico estable.
_DEFECT_PATTERNS = (
    (re.compile(r"números RF duplicados", re.I), "rf_duplicated"),
    (re.compile(r"secuencia RF no consecutiva", re.I), "rf_non_consecutive"),
    (re.compile(r"headings vacíos", re.I), "empty_heading"),
    (re.compile(r"bloques RF sin contenido", re.I), "rf_empty_body"),
)
# REPAIR = defectos de FORMA que un re-emit del agente arregla barato.
# NEEDS_REVIEW = defectos que sugieren CONTENIDO faltante o numeración mal pensada.
_REPAIRABLE = frozenset({"not_epic", "rf_duplicated", "empty_heading"})


def classify_structural_severity(structural_warnings: list | None) -> dict:
    """PURA. Mapea warnings del plan 50 → {code: severity}. Orden estable (sorted).
    Nunca lanza; ante warning desconocido lo ignora (no opina)."""
    codes: set[str] = set()
    for w in structural_warnings or []:
        for pat, code in _DEFECT_PATTERNS:
            if pat.search(str(w)):
                codes.add(code)
                break
    return {
        c: ("repair" if c in _REPAIRABLE else "needs_review")
        for c in sorted(codes)
    }


# ── F2 — linter puro de procesos inventados ──────────────────────────────────
def golden_catalog_diff(html, process_catalog) -> list:
    """PURA. sorted(list) de procesos/módulos citados en `html` que NO están en
    `process_catalog`. Sin catálogo o sin HTML → [] (NO-OP). NUNCA inventa
    reemplazos. Reusa la extracción de api.tickets para no divergir."""
    from api.tickets import catalog_unknown_processes
    return catalog_unknown_processes(html, process_catalog)


# ── F3 — veredicto único ──────────────────────────────────────────────────────
def evaluate_epic_gate(
    *,
    clean_html,
    structural_warnings,        # de _epic_grounding_warnings / _structural_epic_warnings
    process_catalog,            # del client_profile (puede ser None/[])
    catalog_blocking_enabled,   # flag STACKY_EPIC_CATALOG_GATE_ENABLED resuelto por el caller
    looks_like_epic_fn,         # inyectado: api.tickets._looks_like_epic (evita import circular)
    regression_goldens=None,          # Plan 56 F3: list[Golden] | None (default NO-OP)
    regression_blocking_enabled=False, # Plan 56 F3: flag STACKY_REGRESSION_GATE_BLOCKING
) -> GateVerdict:
    """PURA. Ensambla F1+F2+regresión en un veredicto. Nunca lanza.

    Reglas (deterministas, en orden):
      1. not looks_like_epic(clean_html) -> defecto 'not_epic' (repair).
      2. severidades = classify_structural_severity(structural_warnings).
      3. catalog_unknown = golden_catalog_diff(clean_html, process_catalog).
      4. regression_defects = evaluate_regression(clean_html, goldens) si goldens no None.
      5. blocking = hay alguna severidad 'needs_review'
                    OR (catalog_blocking_enabled AND catalog_unknown no vacío)
                    OR (regression_blocking_enabled AND hay regression_defects).
      6. decision: blocking -> NEEDS_REVIEW; elif hay 'repair' -> REPAIR; else PASS.

    Con regression_goldens=None → comportamiento idéntico al previo (NO-OP, backward-compatible).
    """
    defects = dict(classify_structural_severity(structural_warnings))
    if not looks_like_epic_fn(clean_html):
        defects["not_epic"] = "repair"
    catalog_unknown = golden_catalog_diff(clean_html, process_catalog)
    has_block_sev = any(v == "needs_review" for v in defects.values())

    # Plan 56 F3 — gate de regresión (NO-OP si regression_goldens es None)
    regression_defects: list = []
    if regression_goldens:
        from harness.regression_goldens import evaluate_regression
        regression_defects = evaluate_regression(
            clean_html=clean_html,
            goldens=regression_goldens,
            process_catalog=process_catalog,
        )
    has_regression = bool(regression_defects)

    blocking = (
        has_block_sev
        or (bool(catalog_blocking_enabled) and bool(catalog_unknown))
        or (bool(regression_blocking_enabled) and has_regression)
    )
    if blocking:
        decision = GateDecision.NEEDS_REVIEW
    elif any(v == "repair" for v in defects.values()):
        decision = GateDecision.REPAIR
    else:
        decision = GateDecision.PASS
    return GateVerdict(
        decision=decision,
        structural_defects=sorted(defects.keys()),
        catalog_unknown=catalog_unknown,
        blocking=blocking,
        regression_defects=regression_defects,
    )
