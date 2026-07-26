"""epic_rollup.py — Veredicto de una epica por agregacion de sus hijas (Plan 241 F7).

POR QUE. Las epicas (61, 125) son *roll-ups*: no tienen pasos de reproduccion
propios, asi que el reader las devolvia BLOCKED/missing_technical_analysis. Pero
sus hijas SI los tienen (65 y 70 son hijas de 61, con parent=61 verificado) y ya
corren. El veredicto de la epica es la agregacion del de sus hijas.

100% DETERMINISTA => identico en los 3 runtimes. Solo lectura: NUNCA escribe ADO.
"""
from __future__ import annotations

_PASS = "PASS"
_FAIL = "FAIL"
_BLOCKED = "BLOCKED"
_MIXED = "MIXED"
_SKIPPED = "SKIPPED"

# Un veredicto que no es PASS ni FAIL cuenta como cobertura parcial.
_PARTIAL = frozenset({_BLOCKED, _MIXED, _SKIPPED, ""})


def _child_view(child) -> dict:
    c = child if isinstance(child, dict) else {}
    return {
        "ado_id": c.get("ado_id") or c.get("id"),
        "verdict": str(c.get("verdict") or "").strip().upper(),
        "verified": c.get("verified", 0),
        "reason": c.get("reason"),
        "run_id": c.get("run_id"),
    }


def rollup(epic_id: int, children_results: list) -> dict:
    """Agrega el veredicto de las hijas de una epica. NUNCA lanza.

    children_results: [{"ado_id": int, "verdict": str, "verified": int, ...}]

    Reglas EXACTAS (la primera que aplica gana):
      - sin hijas ejecutadas            -> SKIPPED / NO_EXECUTABLE_CHILDREN
      - alguna hija FAIL                -> FAIL    / CHILD_ACCEPTANCE_VIOLATED
      - alguna BLOCKED/MIXED/SKIPPED    -> MIXED   / PARTIAL_EPIC_COVERAGE
      - todas PASS                      -> PASS    / EPIC_ACCEPTANCE_MET

    Incluye SIEMPRE `children` con el detalle por hija: una epica en verde con una
    hija sin correr es un falso verde, y el campo lo hace visible.
    """
    try:
        raw = children_results if isinstance(children_results, (list, tuple)) else []
        children = [_child_view(c) for c in raw if isinstance(c, dict)]

        def _out(verdict, reason, category=None):
            return {
                "ok": True,
                "epic_id": epic_id,
                "verdict": verdict,
                "reason": reason,
                "category": category,
                "children": children,
                "children_total": len(children),
                "children_pass": sum(1 for c in children if c["verdict"] == _PASS),
                "children_fail": sum(1 for c in children if c["verdict"] == _FAIL),
                "verified_total": sum(int(c.get("verified") or 0) for c in children),
            }

        executed = [c for c in children if c["verdict"]]
        if not executed:
            return _out(_SKIPPED, "NO_EXECUTABLE_CHILDREN", "PIP")
        if any(c["verdict"] == _FAIL for c in executed):
            return _out(_FAIL, "CHILD_ACCEPTANCE_VIOLATED", "APP")
        if any(c["verdict"] in _PARTIAL for c in executed) or len(executed) != len(children):
            return _out(_MIXED, "PARTIAL_EPIC_COVERAGE", "APP")
        return _out(_PASS, "EPIC_ACCEPTANCE_MET")
    except Exception as exc:  # noqa: BLE001 — NUNCA lanza
        return {
            "ok": False, "epic_id": epic_id, "verdict": _BLOCKED,
            "reason": "EPIC_ROLLUP_ERROR", "category": "PIP", "children": [],
            "children_total": 0, "children_pass": 0, "children_fail": 0,
            "verified_total": 0, "detail": f"{type(exc).__name__}: {exc}",
        }


def epic_rollup_enabled() -> bool:
    """Flag del arnes STACKY_QA_UAT_EPIC_ROLLUP_ENABLED, default ON (solo lectura)."""
    import os
    raw = os.environ.get("STACKY_QA_UAT_EPIC_ROLLUP_ENABLED")
    if raw is None:
        return True
    return str(raw).strip().lower() not in ("0", "false", "no", "off", "")
