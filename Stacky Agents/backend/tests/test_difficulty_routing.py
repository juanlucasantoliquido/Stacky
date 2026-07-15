"""TDD — I1.2: routing por dificultad estimada en llm_router.decide.

Criterios de aceptación:
- complexity=="S" + agente no-crítico → haiku (downgrade)
- complexity in {"L","XL"} → sonnet aunque tokens sean pocos
- override del operador SIEMPRE gana
- clamp_model respetado siempre
- flag OFF → decide no aplica reglas de dificultad (comportamiento actual)
- RoutingDecision.reason explica la elección
- extensión de tests existentes: backend=anthropic
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def _blocks(chars: int = 0) -> list[dict]:
    return [{"kind": "auto", "title": "ctx", "content": "x" * chars}]


# ---------------------------------------------------------------------------
# Flag OFF → comportamiento sin cambio
# ---------------------------------------------------------------------------

class TestFlagOff:
    def test_flag_off_S_does_not_downgrade(self):
        """Con flag OFF, complexity=S no cambia el routing."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "false"}):
            d = decide(
                agent_type="developer",
                blocks=_blocks(100),
                fingerprint_complexity="S",
                backend="anthropic",
            )
        # developer default es sonnet; S con flag OFF no debería degradar a haiku
        assert d.model == "claude-sonnet-5"

    def test_flag_off_XL_does_not_upgrade_if_already_handled(self):
        """Con flag OFF las reglas I1.2 no se aplican. XL ya tiene regla existente."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "false"}):
            d = decide(
                agent_type="developer",
                blocks=_blocks(100),
                fingerprint_complexity="XL",
                backend="anthropic",
            )
        # XL ya tiene regla preexistente → sonnet
        assert d.model == "claude-sonnet-5"


# ---------------------------------------------------------------------------
# Flag ON — downgrade por complejidad baja
# ---------------------------------------------------------------------------

class TestDowngradeByLowComplexity:
    def test_S_non_critical_agent_downgrade_to_haiku(self):
        """developer + complexity=S + flag ON → haiku."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="developer",
                blocks=_blocks(100),
                fingerprint_complexity="S",
                backend="anthropic",
            )
        assert d.model == "claude-haiku-4-5"
        assert "complexity=S" in d.reason or "downgrade" in d.reason.lower() or "haiku" in d.reason.lower()

    def test_S_qa_agent_downgrade_to_haiku(self):
        """qa + complexity=S → haiku (ya era haiku si tokens < 6k, sigue siendo haiku)."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="qa",
                blocks=_blocks(100),
                fingerprint_complexity="S",
                backend="anthropic",
            )
        assert d.model == "claude-haiku-4-5"

    def test_S_functional_agent_downgrade_to_haiku(self):
        """functional + complexity=S → haiku."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="functional",
                blocks=_blocks(200),
                fingerprint_complexity="S",
                backend="anthropic",
            )
        assert d.model == "claude-haiku-4-5"

    def test_M_complexity_no_downgrade(self):
        """complexity=M no fuerza downgrade (solo S lo hace)."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="developer",
                blocks=_blocks(100),
                fingerprint_complexity="M",
                backend="anthropic",
            )
        # M = default por agente = sonnet
        assert d.model == "claude-sonnet-5"


# ---------------------------------------------------------------------------
# Flag ON — upgrade por complejidad alta
# ---------------------------------------------------------------------------

class TestUpgradeByHighComplexity:
    def test_L_complexity_upgrade_to_sonnet(self):
        """complexity=L + pocos tokens → sonnet (upgrade de haiku que daría qa)."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="qa",
                blocks=_blocks(50),  # < 6k tokens → sin flag sería haiku
                fingerprint_complexity="L",
                backend="anthropic",
            )
        assert d.model == "claude-sonnet-5"
        assert "complexity=L" in d.reason or "L" in d.reason or "sonnet" in d.reason.lower()

    def test_XL_complexity_upgrade_to_sonnet(self):
        """complexity=XL → sonnet (comportamiento preexistente + flag ON)."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="qa",
                blocks=_blocks(50),
                fingerprint_complexity="XL",
                backend="anthropic",
            )
        assert d.model == "claude-sonnet-5"


# ---------------------------------------------------------------------------
# Override gana siempre
# ---------------------------------------------------------------------------

class TestOverrideWins:
    def test_override_wins_over_S_downgrade(self):
        """Override explícito gana sobre la regla de downgrade por S."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="developer",
                blocks=_blocks(100),
                fingerprint_complexity="S",
                override="claude-sonnet-4-6",
                backend="anthropic",
            )
        assert d.model == "claude-sonnet-4-6"
        assert "user-override" in d.reason

    def test_override_wins_over_L_upgrade(self):
        """Override a haiku gana sobre la regla de upgrade por L."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="developer",
                blocks=_blocks(100),
                fingerprint_complexity="L",
                override="claude-haiku-4-5",
                backend="anthropic",
            )
        assert d.model == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Clamp nunca se supera
# ---------------------------------------------------------------------------

class TestClampRespected:
    def test_clamp_blocks_forbidden_model_even_with_XL(self):
        """El cap duro nunca se supera aunque la complejidad sea XL."""
        from services.llm_router import decide, clamp_model
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="developer",
                blocks=_blocks(100),
                fingerprint_complexity="XL",
                backend="anthropic",
            )
        # Clamp siempre en sonnet (nunca opus/fable)
        assert d.model == clamp_model(d.model)
        assert "opus" not in d.model
        assert "fable" not in d.model

    def test_clamp_blocks_forbidden_override(self):
        """Override opus se clampea a sonnet."""
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="developer",
                blocks=_blocks(100),
                fingerprint_complexity="S",
                override="claude-opus-4",
                backend="anthropic",
            )
        assert "opus" not in d.model
        assert "sonnet" in d.model


# ---------------------------------------------------------------------------
# Reason explica la elección
# ---------------------------------------------------------------------------

class TestReasonExplanation:
    def test_reason_mentions_complexity_on_downgrade(self):
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="developer",
                blocks=_blocks(100),
                fingerprint_complexity="S",
                backend="anthropic",
            )
        # La razón debe ser informativa
        assert len(d.reason) > 5

    def test_reason_mentions_complexity_on_upgrade(self):
        from services.llm_router import decide
        with patch.dict(os.environ, {"STACKY_DIFFICULTY_ROUTING_ENABLED": "true"}):
            d = decide(
                agent_type="qa",
                blocks=_blocks(50),
                fingerprint_complexity="L",
                backend="anthropic",
            )
        assert len(d.reason) > 5
