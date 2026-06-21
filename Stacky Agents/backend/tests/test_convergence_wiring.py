"""Plan 58 F2/F3/F4 — Tests del wiring del bucle de convergencia.

No instancia el runner completo. Prueba las helpers puras y la lógica de decisión
de rama (should_use_convergence_loop) que es testeable sin el runner.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from harness.convergence import (
    ConvergenceResult,
    STOP_CONVERGED,
    STOP_DISABLED,
    build_convergence_payload,
    should_use_convergence_loop,
)
from harness.epic_gate import GateDecision, GateVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_convergence_result(
    converged=True,
    iterations=1,
    final_decision="pass",
    stop_reason=STOP_CONVERGED,
    defects_first=None,
    defects_last=None,
    global_budget_spent=1,
) -> ConvergenceResult:
    return ConvergenceResult(
        converged=converged,
        iterations=iterations,
        final_decision=final_decision,
        stop_reason=stop_reason,
        defects_first=defects_first or [],
        defects_last=defects_last or [],
        global_budget_spent=global_budget_spent,
    )


# ---------------------------------------------------------------------------
# F2 — Forma del payload
# ---------------------------------------------------------------------------

def test_payload_shape_converged():
    """El payload tiene exactamente las 8 keys esperadas."""
    conv = _make_convergence_result()
    payload = build_convergence_payload(conv)
    expected_keys = {
        "attempted", "converged", "iterations",
        "final_decision", "stop_reason",
        "defects_first", "defects_last",
        "global_budget_spent",
    }
    assert set(payload.keys()) == expected_keys


def test_payload_attempted_false_when_zero_iterations():
    """attempted=False cuando iterations=0."""
    conv = _make_convergence_result(iterations=0, global_budget_spent=0)
    payload = build_convergence_payload(conv)
    assert payload["attempted"] is False


def test_payload_attempted_true_when_iterations_gt_zero():
    """attempted=True cuando iterations>0."""
    conv = _make_convergence_result(iterations=2, global_budget_spent=2)
    payload = build_convergence_payload(conv)
    assert payload["attempted"] is True


# ---------------------------------------------------------------------------
# F3 — No-regresión flag OFF
# ---------------------------------------------------------------------------

def test_flag_off_uses_legacy_path():
    """Con convergence_enabled=False → should_use_convergence_loop=False."""
    assert should_use_convergence_loop(
        convergence_enabled=False,
        epic_repair_enabled=True,
    ) is False


def test_legacy_single_shot_unchanged_when_flag_off():
    """Con ambos parámetros: OFF+True → False; OFF+False → False."""
    assert should_use_convergence_loop(
        convergence_enabled=False,
        epic_repair_enabled=False,
    ) is False


def test_flag_on_with_repair_on_uses_loop():
    """Con ambos ON → should_use_convergence_loop=True."""
    assert should_use_convergence_loop(
        convergence_enabled=True,
        epic_repair_enabled=True,
    ) is True


def test_flag_on_but_repair_off_no_loop():
    """convergence ON pero repair OFF → False (sin gate no hay convergencia útil)."""
    assert should_use_convergence_loop(
        convergence_enabled=True,
        epic_repair_enabled=False,
    ) is False


# ---------------------------------------------------------------------------
# F4 — Forma del dict de telemetría (metadata["epic_convergence"])
# ---------------------------------------------------------------------------

def test_convergence_metadata_block_shape():
    """El payload de build_convergence_payload tiene las 6 keys de telemetría de F4."""
    conv = _make_convergence_result(
        converged=True,
        iterations=2,
        final_decision="pass",
        stop_reason=STOP_CONVERGED,
        global_budget_spent=2,
    )
    payload = build_convergence_payload(conv)
    # Las 6 claves que se sellan en metadata["epic_convergence"]
    assert "converged" in payload
    assert "iterations" in payload
    assert "final_decision" in payload
    assert "stop_reason" in payload
    assert "global_budget_spent" in payload
    # Y el campo attempted (que también existe en el payload completo)
    assert "attempted" in payload


def test_convergence_metadata_values():
    """Los valores del payload son correctos."""
    conv = _make_convergence_result(
        converged=False,
        iterations=0,
        final_decision="repair",
        stop_reason="budget_reached_global",
        global_budget_spent=0,
    )
    payload = build_convergence_payload(conv)
    assert payload["converged"] is False
    assert payload["iterations"] == 0
    assert payload["final_decision"] == "repair"
    assert payload["stop_reason"] == "budget_reached_global"
    assert payload["global_budget_spent"] == 0
    assert payload["attempted"] is False
