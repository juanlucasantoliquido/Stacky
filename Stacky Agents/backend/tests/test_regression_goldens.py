"""Plan 56 F0 — Modelo de golden + derivadores puros.

Tests PRIMERO (TDD). Funciones puras: sin disco, sin red, sin reloj.
"""
from __future__ import annotations

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_html_with_heading(heading: str) -> str:
    return f"<h1>Épica</h1><h2>{heading}</h2><p>Contenido.</p>"


# ── F0.1 derive_negative_golden ───────────────────────────────────────────────

def test_negative_from_note_deterministic():
    """Nota no vacía → golden negativo determinista; nota vacía → None."""
    from harness.regression_goldens import derive_negative_golden, Golden

    g = derive_negative_golden(
        rejection_note="El RF-01 no describe criterios de aceptación",
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    assert g is not None
    assert isinstance(g, Golden)
    assert g.kind == "negative"
    assert g.check == "absent_substring"
    # normalizado: lowercase + whitespace colapsado
    assert "rf-01" in g.value
    assert g.project == "p1"
    assert g.agent_type == "BusinessAgent"
    assert g.work_item_type == "Epic"

    # nota vacía → None
    assert derive_negative_golden(
        rejection_note="",
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    ) is None

    # nota solo espacios → None
    assert derive_negative_golden(
        rejection_note="   ",
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    ) is None


# ── F0.2 derive_positive_golden ──────────────────────────────────────────────

def test_positive_from_html_extracts_heading():
    """HTML con heading → golden positivo con check=present_heading."""
    from harness.regression_goldens import derive_positive_golden, Golden

    html = _make_html_with_heading("RF-01 Descripción")
    g = derive_positive_golden(
        clean_html=html,
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    assert g is not None
    assert isinstance(g, Golden)
    assert g.kind == "positive"
    assert g.check == "present_heading"
    assert g.confidence_band is None  # sin confidence → sin banda


def test_positive_with_high_confidence_adds_band():
    """confidence >= 0.75 → confidence_band='high'."""
    from harness.regression_goldens import derive_positive_golden

    html = _make_html_with_heading("RF-01 Criterios")
    g = derive_positive_golden(
        clean_html=html,
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
        confidence=0.80,
    )
    assert g is not None
    assert g.confidence_band == "high"

    # confidence < 0.75 → sin banda
    g2 = derive_positive_golden(
        clean_html=html,
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
        confidence=0.60,
    )
    assert g2 is not None
    assert g2.confidence_band is None


# ── F0.3-F0.5 evaluate_regression ────────────────────────────────────────────

def test_evaluate_detects_negative_reappeared():
    """golden negativo cuyo value aparece en el HTML → defecto regression_negative."""
    from harness.regression_goldens import Golden, evaluate_regression

    # Nota rechazada: "sin criterios de aceptación" → value normalizado
    golden = Golden(
        kind="negative",
        check="absent_substring",
        value="sin criterios de aceptación",
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    html = "<h1>E</h1><p>Este RF-01 fue emitido sin criterios de aceptación claros.</p>"
    defects = evaluate_regression(clean_html=html, goldens=[golden], process_catalog=[])
    assert any("regression_negative:" in d for d in defects)


def test_evaluate_detects_positive_missing():
    """golden positivo cuyo heading está ausente → defecto regression_positive_missing."""
    from harness.regression_goldens import Golden, evaluate_regression

    golden = Golden(
        kind="positive",
        check="present_heading",
        value="rf-01 descripción",
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    html = "<h1>Épica</h1><p>Sin ningún RF.</p>"
    defects = evaluate_regression(clean_html=html, goldens=[golden], process_catalog=[])
    assert any("regression_positive_missing:" in d for d in defects)


def test_evaluate_skips_conditional_golden_low_confidence():
    """golden con confidence_band='high' + current confidence=0.5 → skip (no defecto)."""
    from harness.regression_goldens import Golden, evaluate_regression

    golden = Golden(
        kind="positive",
        check="present_heading",
        value="rf-01 descripción",
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
        confidence_band="high",
    )
    html = "<h1>Épica</h1><p>Sin RF.</p>"
    # evaluate_regression necesita saber el confidence actual del epic; lo pasamos
    # via kwarg opcional (solo evalúa si actual >= banda)
    defects = evaluate_regression(
        clean_html=html,
        goldens=[golden],
        process_catalog=[],
        current_confidence=0.50,
    )
    assert defects == [], f"No debe haber defectos con confidence bajo: {defects}"
