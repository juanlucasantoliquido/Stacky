"""Plan 51 — Gates correctivos deterministas de épica (funciones puras).

F0 imports, F1 classify_structural_severity, F2 golden_catalog_diff (smoke),
F3 evaluate_epic_gate. Determinismo/idempotencia explícitos.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── F0 ────────────────────────────────────────────────────────────────────────
def test_imports_ok():
    from harness.epic_gate import (  # noqa: F401
        GateDecision, GateVerdict, classify_structural_severity,
        golden_catalog_diff, evaluate_epic_gate,
    )


# ── F1 — classify_structural_severity ─────────────────────────────────────────
def test_classify_empty_list():
    from harness.epic_gate import classify_structural_severity
    assert classify_structural_severity([]) == {}


def test_classify_none():
    from harness.epic_gate import classify_structural_severity
    assert classify_structural_severity(None) == {}


def test_classify_duplicates_is_repair():
    from harness.epic_gate import classify_structural_severity
    w = ["epic_structure: números RF duplicados: [2]"]
    assert classify_structural_severity(w) == {"rf_duplicated": "repair"}


def test_classify_gaps_is_needs_review():
    from harness.epic_gate import classify_structural_severity
    w = ["epic_structure: secuencia RF no consecutiva, faltan: [2]"]
    assert classify_structural_severity(w) == {"rf_non_consecutive": "needs_review"}


def test_classify_mixed_sorted():
    from harness.epic_gate import classify_structural_severity
    w = [
        "epic_structure: secuencia RF no consecutiva, faltan: [2]",
        "epic_structure: números RF duplicados: [3]",
    ]
    res = classify_structural_severity(w)
    assert res == {"rf_duplicated": "repair", "rf_non_consecutive": "needs_review"}
    assert list(res.keys()) == sorted(res.keys())


def test_classify_ignores_alien_warning():
    from harness.epic_gate import classify_structural_severity
    assert classify_structural_severity(["epic_grounding_low: 0.3"]) == {}


def test_classify_deterministic_regardless_of_order():
    from harness.epic_gate import classify_structural_severity
    a = ["epic_structure: números RF duplicados: [1]",
         "epic_structure: hay headings vacíos"]
    b = list(reversed(a))
    assert classify_structural_severity(a) == classify_structural_severity(b)


# ── F2 smoke (cobertura golden completa en test_golden_catalog_diff.py) ────────
def test_golden_catalog_diff_noop_without_catalog():
    from harness.epic_gate import golden_catalog_diff
    assert golden_catalog_diff("<p>proceso Foo</p>", []) == []
    assert golden_catalog_diff("", [{"name": "Foo"}]) == []


def test_golden_catalog_diff_finds_invented():
    from harness.epic_gate import golden_catalog_diff
    html = "<p>usa el proceso FacturacionFantasma</p>"
    catalog = [{"name": "RSCore"}]
    assert golden_catalog_diff(html, catalog) == ["FacturacionFantasma"]


# ── F3 — evaluate_epic_gate ────────────────────────────────────────────────────
def _looks(html):
    return bool(html) and "RF" in html and "<h1" in html


def test_evaluate_green_is_pass():
    from harness.epic_gate import evaluate_epic_gate, GateDecision
    v = evaluate_epic_gate(
        clean_html="<h1>E</h1><h2>RF-1</h2><p>x</p>",
        structural_warnings=[], process_catalog=None,
        catalog_blocking_enabled=False, looks_like_epic_fn=_looks,
    )
    assert v.decision == GateDecision.PASS
    assert v.blocking is False


def test_evaluate_duplicates_is_repair():
    from harness.epic_gate import evaluate_epic_gate, GateDecision
    v = evaluate_epic_gate(
        clean_html="<h1>E</h1><h2>RF-1</h2>",
        structural_warnings=["epic_structure: números RF duplicados: [1]"],
        process_catalog=None, catalog_blocking_enabled=False, looks_like_epic_fn=_looks,
    )
    assert v.decision == GateDecision.REPAIR
    assert v.blocking is False


def test_evaluate_gaps_is_needs_review():
    from harness.epic_gate import evaluate_epic_gate, GateDecision
    v = evaluate_epic_gate(
        clean_html="<h1>E</h1><h2>RF-3</h2>",
        structural_warnings=["epic_structure: secuencia RF no consecutiva, faltan: [1, 2]"],
        process_catalog=None, catalog_blocking_enabled=False, looks_like_epic_fn=_looks,
    )
    assert v.decision == GateDecision.NEEDS_REVIEW
    assert v.blocking is True


def test_evaluate_narration_is_repair_not_epic():
    from harness.epic_gate import evaluate_epic_gate, GateDecision
    v = evaluate_epic_gate(
        clean_html="solo narración",
        structural_warnings=[], process_catalog=None,
        catalog_blocking_enabled=False, looks_like_epic_fn=_looks,
    )
    assert v.decision == GateDecision.REPAIR
    assert "not_epic" in v.structural_defects


def test_evaluate_invented_process_blocks_when_enabled():
    from harness.epic_gate import evaluate_epic_gate, GateDecision
    v = evaluate_epic_gate(
        clean_html="<h1>E</h1><h2>RF-1</h2><p>proceso Fantasma</p>",
        structural_warnings=[], process_catalog=[{"name": "RSCore"}],
        catalog_blocking_enabled=True, looks_like_epic_fn=_looks,
    )
    assert v.decision == GateDecision.NEEDS_REVIEW
    assert v.blocking is True
    assert "Fantasma" in v.catalog_unknown


def test_evaluate_invented_process_no_block_when_disabled():
    from harness.epic_gate import evaluate_epic_gate, GateDecision
    v = evaluate_epic_gate(
        clean_html="<h1>E</h1><h2>RF-1</h2><p>proceso Fantasma</p>",
        structural_warnings=[], process_catalog=[{"name": "RSCore"}],
        catalog_blocking_enabled=False, looks_like_epic_fn=_looks,
    )
    assert v.blocking is False
    assert v.catalog_unknown == ["Fantasma"]  # se reporta, no bloquea


def test_evaluate_idempotent():
    from harness.epic_gate import evaluate_epic_gate
    kwargs = dict(
        clean_html="<h1>E</h1><h2>RF-1</h2>",
        structural_warnings=["epic_structure: números RF duplicados: [1]"],
        process_catalog=None, catalog_blocking_enabled=False, looks_like_epic_fn=_looks,
    )
    assert evaluate_epic_gate(**kwargs) == evaluate_epic_gate(**kwargs)


# ── F2 no-regresión del refactor: el string del warning queda idéntico ─────────
def test_catalog_grounding_warning_string_unchanged():
    from api.tickets import _catalog_grounding_warnings
    html = "<p>usa el proceso Fantasma</p>"
    catalog = [{"name": "RSCore"}]
    out = _catalog_grounding_warnings(html, catalog)
    assert out == ["catalog_grounding: procesos citados no presentes en el catálogo: ['Fantasma']"]
