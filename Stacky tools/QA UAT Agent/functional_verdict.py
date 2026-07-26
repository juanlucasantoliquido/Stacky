"""functional_verdict.py — Veredicto FUNCIONAL (Plan 240 F6 + Plan 241 F2).

REGLA DURA ANTI-FALSO-VERDE: un run sin NINGUN criterio funcional verificado NO
puede ser PASS. Devuelve MIXED con reason NO_FUNCTIONAL_ASSERTION.

Plan 241 F2 — LEY DE DISCRIMINACION: un criterio con status "verified" pero SIN
discriminacion probada NO cuenta como verificado: pasa a not_verifiable. Gateado
por STACKY_QA_UAT_STRICT_DISCRIMINATION_ENABLED (default ON).

(C6) El fallo del TEST no se disfraza de fallo del DESARROLLO: un
DISCRIMINATION_FAILED significa "esta asercion no sabe fallar" — es un bug del
ARNES. Cae a not_verifiable (=> MIXED, nunca FAIL) y se emite aparte en
`test_quality_issues`, que es el backlog accionable para mejorar el catalogo
(F1) y la forja de datos (F3).
"""
from __future__ import annotations

import copy
import os

# Espeja verdict_normalizer.VERDICT_SET
_VERDICTS = ("PASS", "FAIL", "BLOCKED", "MIXED", "SKIPPED")

_STATUS_VERIFIED = "verified"
_STATUS_VIOLATED = "violated"
_STATUS_NOT_VERIFIABLE = "not_verifiable"

_STRICT_FLAG = "STACKY_QA_UAT_STRICT_DISCRIMINATION_ENABLED"


def strict_discrimination_enabled() -> bool:
    """Flag del arnes, default ON. El default laxo ES el bug que el Plan 241 mata."""
    raw = os.environ.get(_STRICT_FLAG)
    if raw is None:
        return True
    return str(raw).strip().lower() not in ("0", "false", "no", "off", "")


def _apply_discrimination_rule(criteria_results, strict: bool):
    """Plan 241 F2 — degrada los `verified` sin discriminacion probada.

    NO muta la lista del caller: trabaja sobre una copia profunda.
    Devuelve (criterios_ajustados, incidencias_de_calidad_del_test).
    """
    clean: list = []
    quality_issues: list = []
    if not isinstance(criteria_results, (list, tuple)):
        return clean, quality_issues
    for raw in criteria_results:
        if not isinstance(raw, dict):
            continue
        c = copy.deepcopy(raw)
        disc = c.get("discrimination") or {}
        if not isinstance(disc, dict):
            disc = {}
        if disc.get("code") == "DISCRIMINATION_FAILED":
            quality_issues.append({
                "criterio_id": c.get("id") or c.get("criterio_id"),
                "kind": c.get("kind"),
                "code": "DISCRIMINATION_FAILED",
                "detail": disc.get("detail", ""),
                "fix_sugerido": (
                    "La asercion pasa igual contra el estado pre-fix: usa un oraculo "
                    "exacto (attribute_equals sobre el atributo del DOM) o forja un "
                    "dato que cruce el umbral (test_data_forge)."
                ),
            })
        if strict and str(c.get("status") or "").strip().lower() == _STATUS_VERIFIED \
                and not disc.get("proven"):
            c["status"] = _STATUS_NOT_VERIFIABLE
            c["downgrade_reason"] = disc.get("code") or "NO_DISCRIMINATION"
        clean.append(c)
    return clean, quality_issues


def _counts(criteria_results) -> tuple[int, int, int, list]:
    verified = violated = not_verifiable = 0
    clean: list = []
    if isinstance(criteria_results, (list, tuple)):
        for c in criteria_results:
            if not isinstance(c, dict):
                continue
            clean.append(c)
            st = str(c.get("status") or "").strip().lower()
            if st == _STATUS_VERIFIED:
                verified += 1
            elif st == _STATUS_VIOLATED:
                violated += 1
            elif st == _STATUS_NOT_VERIFIABLE:
                not_verifiable += 1
    return verified, violated, not_verifiable, clean


def build_functional_verdict(criteria_results, technical, strict=None) -> dict:
    """Combina criterios funcionales con el veredicto tecnico. NUNCA lanza.

    Precedencia EXACTA (la primera que aplica gana):
      1. tecnico BLOCKED                 -> BLOCKED (entorno; no se juzga lo funcional)
      2. algun criterio violated         -> FAIL  / ACCEPTANCE_VIOLATED / APP
      3. tecnico FAIL                    -> FAIL  / TECHNICAL_FAILURE
      4. verified == 0                   -> MIXED / NO_FUNCTIONAL_ASSERTION
      5. algun not_verifiable            -> MIXED / PARTIAL_COVERAGE
      6. resto                           -> PASS  / ACCEPTANCE_MET

    strict: None => lee la flag del arnes (default ON). Plan 241 F2.
    """
    if strict is None:
        strict = strict_discrimination_enabled()
    adjusted, quality_issues = _apply_discrimination_rule(criteria_results, bool(strict))
    verified, violated, not_verifiable, clean = _counts(adjusted)
    tech = technical if isinstance(technical, dict) else {}
    tech_verdict = str(tech.get("verdict") or "").strip().upper()
    tech_category = tech.get("category")

    def _out(verdict, reason, category, functional_pass):
        return {
            "verdict": verdict, "reason": reason, "functional_pass": functional_pass,
            "category": category, "verified": verified, "violated": violated,
            "not_verifiable": not_verifiable, "criteria": clean,
            # (C6) El backlog del ARNES, separado del veredicto del DESARROLLO.
            "test_quality_issues": quality_issues,
            "strict_discrimination": bool(strict),
        }

    if tech_verdict == "BLOCKED":
        return _out("BLOCKED", "ENVIRONMENT_BLOCKED", tech_category or "ENV", False)
    if violated > 0:
        return _out("FAIL", "ACCEPTANCE_VIOLATED", "APP", False)
    if tech_verdict == "FAIL":
        return _out("FAIL", "TECHNICAL_FAILURE", tech_category, False)
    if verified == 0:
        # KPI-1: aunque lo tecnico sea PASS, sin una sola asercion funcional
        # verificada NO se declara PASS.
        return _out("MIXED", "NO_FUNCTIONAL_ASSERTION", tech_category, False)
    if not_verifiable > 0:
        return _out("MIXED", "PARTIAL_COVERAGE", tech_category, False)
    return _out("PASS", "ACCEPTANCE_MET", None, True)
