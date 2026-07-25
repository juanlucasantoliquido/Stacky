"""functional_verdict.py — Veredicto FUNCIONAL (Plan 240 F6).

REGLA DURA ANTI-FALSO-VERDE: un run sin NINGUN criterio funcional verificado NO puede
ser PASS. Devuelve MIXED con reason NO_FUNCTIONAL_ASSERTION.
"""
from __future__ import annotations

# Espeja verdict_normalizer.VERDICT_SET
_VERDICTS = ("PASS", "FAIL", "BLOCKED", "MIXED", "SKIPPED")

_STATUS_VERIFIED = "verified"
_STATUS_VIOLATED = "violated"
_STATUS_NOT_VERIFIABLE = "not_verifiable"


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


def build_functional_verdict(criteria_results, technical) -> dict:
    """Combina criterios funcionales con el veredicto tecnico. NUNCA lanza.

    Precedencia EXACTA (la primera que aplica gana):
      1. tecnico BLOCKED                 -> BLOCKED (entorno; no se juzga lo funcional)
      2. algun criterio violated         -> FAIL  / ACCEPTANCE_VIOLATED / APP
      3. tecnico FAIL                    -> FAIL  / TECHNICAL_FAILURE
      4. verified == 0                   -> MIXED / NO_FUNCTIONAL_ASSERTION
      5. algun not_verifiable            -> MIXED / PARTIAL_COVERAGE
      6. resto                           -> PASS  / ACCEPTANCE_MET
    """
    verified, violated, not_verifiable, clean = _counts(criteria_results)
    tech = technical if isinstance(technical, dict) else {}
    tech_verdict = str(tech.get("verdict") or "").strip().upper()
    tech_category = tech.get("category")

    def _out(verdict, reason, category, functional_pass):
        return {
            "verdict": verdict, "reason": reason, "functional_pass": functional_pass,
            "category": category, "verified": verified, "violated": violated,
            "not_verifiable": not_verifiable, "criteria": clean,
        }

    if tech_verdict == "BLOCKED":
        return _out("BLOCKED", "ENVIRONMENT_BLOCKED", tech_category or "ENV", False)
    if violated > 0:
        return _out("FAIL", "ACCEPTANCE_VIOLATED", "APP", False)
    if tech_verdict == "FAIL":
        return _out("FAIL", "TECHNICAL_FAILURE", tech_category, False)
    if verified == 0:
        # KPI-5: aunque lo tecnico sea PASS, sin una sola asercion funcional
        # verificada NO se declara PASS.
        return _out("MIXED", "NO_FUNCTIONAL_ASSERTION", tech_category, False)
    if not_verifiable > 0:
        return _out("MIXED", "PARTIAL_COVERAGE", tech_category, False)
    return _out("PASS", "ACCEPTANCE_MET", None, True)
