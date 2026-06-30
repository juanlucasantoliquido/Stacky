"""Plan 56 F3 — evaluate_epic_gate extendido con regression_goldens.

Tests PRIMERO (TDD). Funciones puras: sin disco, sin red.
"""
from __future__ import annotations

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _looks_like_epic(html: str) -> bool:
    """Stub mínimo: True si html tiene <h2>."""
    import re
    return bool(re.search(r"<h2", html, re.IGNORECASE))


def _make_baseline_kwargs(html: str) -> dict:
    """Parámetros mínimos para evaluate_epic_gate sin regresión."""
    return dict(
        clean_html=html,
        structural_warnings=[],
        process_catalog=[],
        catalog_blocking_enabled=False,
        looks_like_epic_fn=_looks_like_epic,
    )


HTML_OK = "<h1>Épica</h1><h2>RF-01 Descripción</h2><p>Contenido limpio.</p>"
HTML_BAD = "<p>Solo narración, sin estructura RF.</p>"


# ── Test F3.1 — NO-OP sin goldens ────────────────────────────────────────────

def test_gate_noop_without_goldens():
    """Sin regression_goldens → veredicto idéntico al baseline (sin campo extra)."""
    from harness.epic_gate import evaluate_epic_gate, GateDecision

    v_base = evaluate_epic_gate(**_make_baseline_kwargs(HTML_OK))
    v_new = evaluate_epic_gate(
        **_make_baseline_kwargs(HTML_OK),
        regression_goldens=None,
        regression_blocking_enabled=False,
    )
    assert v_base.decision == v_new.decision
    assert v_base.blocking == v_new.blocking
    # regression_defects existe pero está vacío
    assert v_new.regression_defects == []


# ── Test F3.2 — warning mode: defectos reportados pero no bloquean ────────────

def test_gate_reports_regression_warning_not_blocking():
    """Golden negativo reaparece + blocking_enabled=False → defecto en regression_defects, no bloquea."""
    from harness.epic_gate import evaluate_epic_gate
    from harness.regression_goldens import Golden

    # Golden negativo: "narración" no debe aparecer
    goldens = [Golden(
        kind="negative",
        check="absent_substring",
        value="solo narración",
        project=None,
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )]
    html = "<h1>E</h1><h2>RF-01</h2><p>Solo narración sin criterios.</p>"

    v = evaluate_epic_gate(
        **_make_baseline_kwargs(html),
        regression_goldens=goldens,
        regression_blocking_enabled=False,
    )
    assert len(v.regression_defects) > 0
    # No bloquea: blocking False (ningún defecto estructural NEEDS_REVIEW en este HTML)
    assert v.blocking is False


# ── Test F3.3 — blocking mode ────────────────────────────────────────────────

def test_gate_blocks_when_blocking_enabled():
    """Mismo defecto + blocking_enabled=True → blocking=True, NEEDS_REVIEW."""
    from harness.epic_gate import evaluate_epic_gate, GateDecision
    from harness.regression_goldens import Golden

    goldens = [Golden(
        kind="negative",
        check="absent_substring",
        value="solo narración",
        project=None,
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )]
    html = "<h1>E</h1><h2>RF-01</h2><p>Solo narración sin criterios.</p>"

    v = evaluate_epic_gate(
        **_make_baseline_kwargs(html),
        regression_goldens=goldens,
        regression_blocking_enabled=True,
    )
    assert len(v.regression_defects) > 0
    assert v.blocking is True
    assert v.decision.value == "needs_review"


# ── Test F3.4 — sin regresión ────────────────────────────────────────────────

def test_gate_pass_when_no_regression():
    """HTML limpio respecto a goldens → regression_defects vacío."""
    from harness.epic_gate import evaluate_epic_gate
    from harness.regression_goldens import Golden

    goldens = [Golden(
        kind="negative",
        check="absent_substring",
        value="defecto inexistente en este html",
        project=None,
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )]

    v = evaluate_epic_gate(
        **_make_baseline_kwargs(HTML_OK),
        regression_goldens=goldens,
        regression_blocking_enabled=True,
    )
    assert v.regression_defects == []
    # Sin regresión y HTML ok → no bloquea por regresión
    assert v.blocking is False
