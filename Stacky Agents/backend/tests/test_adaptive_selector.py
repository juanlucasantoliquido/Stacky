"""Plan 53 — Tests del selector adaptativo de modelo/effort por confidence.

Cubre:
- F0: flag STACKY_ADAPTIVE_SELECTOR_ENABLED default OFF.
- F1: tabla ADAPTIVE_BANDS + select() pura (13 tests de tabla/bordes).
- F3: degradación por runtime (clamps existentes) + tests de matriz.
"""
from __future__ import annotations

import sys
import pathlib

# Asegurar que el backend esté en el path.
_BACKEND = pathlib.Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── F0: Flag default OFF ──────────────────────────────────────────────────────

def test_flag_default_on():
    """F0: STACKY_ADAPTIVE_SELECTOR_ENABLED existe y es True por default
    (promovido 2026-07-15: el override manual del operador siempre gana,
    ninguna de las 4 excepciones duras aplica)."""
    import os
    # Guardar y eliminar la env var para asegurar el default.
    original = os.environ.pop("STACKY_ADAPTIVE_SELECTOR_ENABLED", None)
    try:
        import importlib
        import config as _config_mod
        importlib.reload(_config_mod)
        from config import Config
        fresh = Config()
        assert fresh.STACKY_ADAPTIVE_SELECTOR_ENABLED is True, (
            "STACKY_ADAPTIVE_SELECTOR_ENABLED debe ser True por default"
        )
    finally:
        if original is not None:
            os.environ["STACKY_ADAPTIVE_SELECTOR_ENABLED"] = original


def test_module_imports_cleanly():
    """F0: import services.adaptive_selector no rompe."""
    import services.adaptive_selector  # noqa: F401


# ── F1: Tabla ADAPTIVE_BANDS + select() pura ─────────────────────────────────

def _select(confidence, base_model=None, base_effort="high"):
    from services.adaptive_selector import select
    return select(confidence, base_model=base_model, base_effort=base_effort)


def test_very_high_confidence_cheap():
    """confidence=0.92 → Sonnet/low (very_high_confidence)."""
    from services.adaptive_selector import _MODEL_SONNET
    sel = _select(0.92)
    assert sel.model == _MODEL_SONNET
    assert sel.effort == "low"
    assert "very_high_confidence" in sel.reason


def test_high_confidence():
    """confidence=0.75 → Sonnet/medium (high_confidence)."""
    from services.adaptive_selector import _MODEL_SONNET
    sel = _select(0.75)
    assert sel.model == _MODEL_SONNET
    assert sel.effort == "medium"
    assert "high_confidence" in sel.reason


def test_medium_confidence():
    """confidence=0.60 → Sonnet/high (medium_confidence)."""
    from services.adaptive_selector import _MODEL_SONNET
    sel = _select(0.60)
    assert sel.model == _MODEL_SONNET
    assert sel.effort == "high"
    assert "medium_confidence" in sel.reason


def test_low_confidence_escalates_opus():
    """confidence=0.40 → Opus/high (low_confidence)."""
    from services.adaptive_selector import _MODEL_OPUS
    sel = _select(0.40)
    assert sel.model == _MODEL_OPUS
    assert sel.effort == "high"
    assert "low_confidence" in sel.reason


def test_very_low_confidence_max():
    """confidence=0.10 → Opus/max (very_low_confidence)."""
    from services.adaptive_selector import _MODEL_OPUS
    sel = _select(0.10)
    assert sel.model == _MODEL_OPUS
    assert sel.effort == "max"
    assert "very_low_confidence" in sel.reason


def test_border_070_belongs_to_high_band():
    """0.70 es el umbral de high_confidence (>=0.70) → Sonnet/medium, no Sonnet/high."""
    from services.adaptive_selector import _MODEL_SONNET
    sel = _select(0.70)
    assert sel.model == _MODEL_SONNET
    assert sel.effort == "medium", f"0.70 debe caer en high_confidence (medium), got {sel.effort}"


def test_border_050_belongs_to_medium_band():
    """0.50 es el umbral de medium_confidence (>=0.50) → Sonnet/high, no Opus."""
    from services.adaptive_selector import _MODEL_SONNET
    sel = _select(0.50)
    assert sel.model == _MODEL_SONNET
    assert sel.effort == "high", f"0.50 debe caer en medium_confidence (Sonnet/high), got Opus?={sel.model}"


def test_none_confidence_keeps_base():
    """None → no_confidence_signal → base intacto."""
    sel = _select(None, base_model="custom-model", base_effort="high")
    assert sel.model == "custom-model"
    assert sel.effort == "high"
    assert sel.reason == "no_confidence_signal"


def test_out_of_range_high_clamped():
    """1.5 → clamp a 1.0 → very_high_confidence → Sonnet/low."""
    from services.adaptive_selector import _MODEL_SONNET
    sel = _select(1.5)
    assert sel.model == _MODEL_SONNET
    assert sel.effort == "low"


def test_out_of_range_low_clamped():
    """-0.3 → clamp a 0.0 → very_low_confidence → Opus/max."""
    from services.adaptive_selector import _MODEL_OPUS
    sel = _select(-0.3)
    assert sel.model == _MODEL_OPUS
    assert sel.effort == "max"


def test_non_numeric_keeps_base():
    """"abc" → no_confidence_signal → base intacto."""
    sel = _select("abc", base_model=None, base_effort="high")
    assert sel.model is None
    assert sel.effort == "high"
    assert sel.reason == "no_confidence_signal"


def test_opus_proposal_is_in_allowlist():
    """La banda Opus propone un modelo que está en _OPUS_ALLOWLIST."""
    from services import llm_router
    from services.adaptive_selector import _MODEL_OPUS
    # Baja confidence → Opus propuesto
    sel = _select(0.1)
    assert sel.model == _MODEL_OPUS
    assert sel.model in llm_router._OPUS_ALLOWLIST


def test_select_is_pure():
    """Llamar 2x con la misma entrada produce resultados iguales (sin estado)."""
    sel1 = _select(0.6, base_model="x", base_effort="medium")
    sel2 = _select(0.6, base_model="x", base_effort="medium")
    assert sel1 == sel2


# ── F3: Degradación por runtime — clamps existentes ──────────────────────────

def test_proposal_effort_clamped_for_sonnet():
    """Banda very_high propone Sonnet+low; clamp_effort_for_model("low","claude-sonnet-4-6") == "low" (soportado)."""
    from api.agents import _clamp_effort_for_model
    result = _clamp_effort_for_model("low", "claude-sonnet-4-6")
    assert result == "low", f"Sonnet soporta low; got {result}"


def test_proposal_max_effort_survives_opus():
    """Banda very_low propone Opus+max; clamp_effort_for_model("max","claude-opus-4-8") → "max" (Opus soporta todo)."""
    from api.agents import _clamp_effort_for_model
    result = _clamp_effort_for_model("max", "claude-opus-4-8")
    assert result == "max", f"Opus soporta max; got {result}"


def test_non_claude_model_passes_clamp_untouched():
    """Modelos no-Claude pasan clamp_model sin tocar (llm_router.py:53)."""
    from services.llm_router import clamp_model
    result = clamp_model("gpt-x", allow_opus=True)
    assert result == "gpt-x", f"Modelo no-Claude debe pasar intacto; got {result}"


def test_clamped_confidence_high_100_selects_highest_band():
    """confidence=1.5 → clamp 1.0 → very_high_confidence → Sonnet/low (C8)."""
    from services.adaptive_selector import _MODEL_SONNET
    sel = _select(1.5)
    assert sel.model == _MODEL_SONNET
    assert sel.effort == "low"
    assert "very_high_confidence" in sel.reason


def test_clamped_confidence_low_00_selects_lowest_band():
    """confidence=-0.5 → clamp 0.0 → very_low_confidence → Opus/max (C8)."""
    from services.adaptive_selector import _MODEL_OPUS
    sel = _select(-0.5)
    assert sel.model == _MODEL_OPUS
    assert sel.effort == "max"
    assert "very_low_confidence" in sel.reason


def test_border_085_belongs_to_very_high_band():
    """0.85 es el umbral de very_high_confidence (>=0.85) → Sonnet/low."""
    from services.adaptive_selector import _MODEL_SONNET
    sel = _select(0.85)
    assert sel.model == _MODEL_SONNET
    assert sel.effort == "low"


def test_border_030_belongs_to_low_confidence_band():
    """0.30 es el umbral de low_confidence (>=0.30) → Opus/high (no Opus/max)."""
    from services.adaptive_selector import _MODEL_OPUS
    sel = _select(0.30)
    assert sel.model == _MODEL_OPUS
    assert sel.effort == "high"


def test_just_below_030_is_very_low():
    """0.29 < 0.30 → very_low_confidence → Opus/max."""
    from services.adaptive_selector import _MODEL_OPUS
    sel = _select(0.29)
    assert sel.model == _MODEL_OPUS
    assert sel.effort == "max"
