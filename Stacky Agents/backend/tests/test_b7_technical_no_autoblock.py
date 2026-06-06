"""
Tests de contrato B7 — el Analista Técnico pregunta antes de bloquear
(plan 2026-06-02, diseño D7-1 prompt-first).

Asserts sobre los .agent.md canónicos: ante un bloqueante deben publicar una
CONSULTA pre-bloqueo y dejar el ticket en su estado de revisión, NUNCA
auto-transicionar a Blocked.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent  # backend/
DEPLOY = ROOT.parent / "DeployStackyAgents"

# Los .agent.md son assets canónicos versionados en backend/Stacky/agents; el
# release los publica en DeployStackyAgents/Stacky/agents. Probamos la primera
# ubicación que exista.
_LEGACY_CANDIDATES = [
    ROOT / "Stacky" / "agents" / "TechnicalAnalyst.agent.md",
    DEPLOY / "Stacky" / "agents" / "TechnicalAnalyst.agent.md",
]
_V2_CANDIDATES = [
    ROOT / "Stacky" / "agents" / "TechnicalAnalyst.v2.agent.md",
    DEPLOY / "Stacky" / "agents" / "TechnicalAnalyst.v2.agent.md",
]


def _first_existing(candidates: list[Path]) -> Path | None:
    return next((p for p in candidates if p.is_file()), None)


LEGACY = _first_existing(_LEGACY_CANDIDATES)
V2 = _first_existing(_V2_CANDIDATES)


def _read(p: Path | None) -> str:
    if p is None:
        pytest.skip("agente .agent.md no disponible en backend/Stacky/agents")
    return p.read_text(encoding="utf-8")


def test_legacy_uses_preblock_consultation():
    text = _read(LEGACY)
    # La nueva consulta pre-bloqueo está presente.
    assert "CONSULTA TÉCNICA (pre-bloqueo)" in text
    # Instrucción explícita de no auto-bloquear (invariante en ambas variantes legacy).
    assert "por tu cuenta" in text
    # La rama de bloqueante deja el ticket en Technical review (no Blocked).
    assert "Technical review" in text


def test_legacy_no_autonomous_blocked_banner():
    text = _read(LEGACY)
    # Ya no debe quedar el banner viejo "Estado asignado: BLOCKED" — ahora es consulta.
    assert "<strong>BLOCKED</strong></span>" not in text


def test_v2_targets_review_state_not_blocked():
    text = _read(V2)
    assert "CONSULTA TÉCNICA (pre-bloqueo)" in text
    # La rama de bloqueo apunta al estado de revisión (input_states[0]).
    assert "tracker_state_machine.technical.input_states[0]" in text
    # Instrucción dura: el agente nunca aplica blocked_state por su cuenta.
    assert "NUNCA aplica `blocked_state` por su cuenta" in text


def test_persona_instructs_ask_before_block():
    from agents.technical import TechnicalAgent  # type: ignore

    # Construcción mínima: la persona system_prompt no requiere args externos.
    try:
        prompt = TechnicalAgent().system_prompt()  # type: ignore[call-arg]
    except TypeError:
        # Si el constructor exige args, leemos el source como fallback.
        prompt = (ROOT / "agents" / "technical.py").read_text(encoding="utf-8")
    assert "NO bloquees el ticket" in prompt
    assert "decisión humana" in prompt
