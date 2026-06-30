"""Plan 41 F2 — Ranking de supuestos + derivación de preguntas (determinista)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.intent_preflight import (  # noqa: E402
    IntentAssumption,
    IntentBrief,
    rank_and_flag,
)


def _brief(assumptions, open_questions=None):
    return IntentBrief(
        objective="o", deliverables=[], assumptions=assumptions,
        open_questions=open_questions or [], areas=[], confidence=0.5,
    )


def test_assumptions_sorted_high_first():
    b = _brief([
        IntentAssumption("low one", "low", False),
        IntentAssumption("high one", "high", False),
        IntentAssumption("med one", "medium", False),
    ])
    out = rank_and_flag(b)
    assert out.assumptions[0].impact == "high"
    assert out.assumptions[-1].impact == "low"


def test_high_impact_needs_confirmation_becomes_question():
    b = _brief([IntentAssumption("el batch es FacturacionNocturna", "high", True)])
    out = rank_and_flag(b)
    assert any("FacturacionNocturna" in q for q in out.open_questions)


def test_low_impact_does_not_become_question():
    b = _brief([IntentAssumption("detalle menor", "low", True)])
    out = rank_and_flag(b)
    assert out.open_questions == []


def test_no_duplicate_questions():
    q = "¿Confirmás que: el batch es X?"
    b = _brief([IntentAssumption("el batch es X", "high", True)], open_questions=[q])
    out = rank_and_flag(b)
    assert out.open_questions.count(q) == 1


def test_all_clear_yields_no_questions():
    b = _brief([IntentAssumption("ok", "medium", False)])
    out = rank_and_flag(b)
    assert out.open_questions == []
