"""Plan 77 F0 — Mapper puro agent_type → fase del Issue.

Verifica que el mapeo sea determinista, case-insensitive, y que toda fase
devuelta tenga un marker en _ISSUE_PHASE_MARKERS (garantía de coherencia).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def _get_mapper():
    from api.tickets import agent_type_to_issue_phase
    return agent_type_to_issue_phase


def _get_markers():
    from api.tickets import _ISSUE_PHASE_MARKERS
    return _ISSUE_PHASE_MARKERS


# ---------------------------------------------------------------------------
# Casos de mapeo
# ---------------------------------------------------------------------------

def test_functional_maps_to_funcional():
    assert _get_mapper()("functional") == "funcional"


def test_technical_maps_to_tecnico():
    assert _get_mapper()("technical") == "tecnico"


def test_developer_maps_to_implementacion():
    assert _get_mapper()("developer") == "implementacion"


def test_business_maps_to_none():
    """business crea el WI (one-shot), no es una fase de comentario."""
    assert _get_mapper()("business") is None


def test_unknown_maps_to_none():
    m = _get_mapper()
    assert m("qa") is None
    assert m("debug") is None
    assert m("") is None
    assert m(None) is None
    assert m("pr_review") is None
    assert m("custom") is None


def test_case_insensitive():
    m = _get_mapper()
    assert m("FUNCTIONAL") == "funcional"
    assert m("TECHNICAL") == "tecnico"
    assert m("Developer") == "implementacion"
    assert m("  functional  ") == "funcional"


def test_every_phase_value_has_a_marker():
    """Para cada valor devuelto por el mapper, debe existir marker en _ISSUE_PHASE_MARKERS."""
    m = _get_mapper()
    markers = _get_markers()
    for agent_type in ("functional", "technical", "developer"):
        phase = m(agent_type)
        assert phase is not None, f"{agent_type} debería mapear a una fase"
        assert phase in markers, (
            f"fase '{phase}' (de agent_type='{agent_type}') no tiene marker en _ISSUE_PHASE_MARKERS"
        )
