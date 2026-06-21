"""Plan 58 F1 — Tests de run_convergence_loop (función PURA, >=13 casos).

Usa GateVerdict reales (NamedTuple). NO mockea Claude.
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

from harness.epic_gate import GateDecision, GateVerdict
from harness.convergence import (
    ConvergenceResult,
    STOP_BUDGET_EXHAUSTED,
    STOP_BUDGET_REACHED_GLOBAL,
    STOP_CONVERGED,
    STOP_DISABLED,
    STOP_NEEDS_REVIEW,
    STOP_NO_PROGRESS,
    STOP_NO_RESUME,
    STOP_SEND_FAILED,
    _all_defects,
    run_convergence_loop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_verdict(decision: GateDecision, structural=None, regression=None) -> GateVerdict:
    return GateVerdict(
        decision=decision,
        structural_defects=structural or [],
        catalog_unknown=[],
        blocking=(decision != GateDecision.PASS),
        regression_defects=regression or [],
    )


def _queue_reextract(verdicts: list[GateVerdict]):
    """Closure que devuelve veredictos de la lista en orden."""
    it = iter(verdicts)
    def _fn():
        return next(it)
    return _fn


PASS_V = _make_verdict(GateDecision.PASS)
REPAIR_A = _make_verdict(GateDecision.REPAIR, structural=["rf_duplicated"])
REPAIR_B = _make_verdict(GateDecision.REPAIR, structural=["empty_heading"])
NR_V = _make_verdict(GateDecision.NEEDS_REVIEW)

_RUNTIME = "claude_code_cli"
_SEND_OK = lambda m: True  # noqa: E731


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------

def test_already_pass_no_iterations():
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=2,
        initial_verdict=PASS_V,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=lambda: PASS_V,
    )
    assert r.converged is True
    assert r.iterations == 0
    assert r.stop_reason == STOP_CONVERGED


def test_needs_review_terminal():
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=2,
        initial_verdict=NR_V,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=lambda: PASS_V,
    )
    assert r.converged is False
    assert r.iterations == 0
    assert r.stop_reason == STOP_NEEDS_REVIEW


def test_repair_then_pass_in_one():
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=2,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=_queue_reextract([PASS_V]),
    )
    assert r.converged is True
    assert r.iterations == 1
    assert r.stop_reason == STOP_CONVERGED


def test_repair_twice_then_pass():
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=2,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=_queue_reextract([REPAIR_B, PASS_V]),
    )
    assert r.converged is True
    assert r.iterations == 2
    assert r.stop_reason == STOP_CONVERGED


def test_budget_exhausted():
    """Siempre REPAIR con defectos distintos → agota el presupuesto."""
    verdicts = [
        _make_verdict(GateDecision.REPAIR, structural=[f"defect_{i}"])
        for i in range(10)
    ]
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=2,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=_queue_reextract(verdicts),
    )
    assert r.converged is False
    assert r.iterations == 2
    assert r.stop_reason == STOP_BUDGET_EXHAUSTED


def test_no_progress_aborts():
    """Mismo set de defectos tras el pase → STOP_NO_PROGRESS."""
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=3,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=_queue_reextract([REPAIR_A]),  # mismos defectos
    )
    assert r.converged is False
    assert r.iterations == 1
    assert r.stop_reason == STOP_NO_PROGRESS


def test_copilot_degrades_single():
    r = run_convergence_loop(
        enabled=True, runtime="github_copilot", max_iterations=2,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=lambda: PASS_V,
    )
    assert r.converged is False
    assert r.iterations == 0
    assert r.stop_reason == STOP_NO_RESUME


def test_send_fn_none():
    """send_fn=None → STOP_NO_RESUME (regla 4)."""
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=2,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=None,
        reextract_and_evaluate_fn=lambda: PASS_V,
    )
    assert r.converged is False
    assert r.iterations == 0
    assert r.stop_reason == STOP_NO_RESUME


def test_send_fn_returns_falsy():
    """send_fn devuelve False → STOP_SEND_FAILED."""
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=2,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=lambda m: False,
        reextract_and_evaluate_fn=lambda: PASS_V,
    )
    assert r.converged is False
    assert r.stop_reason == STOP_SEND_FAILED
    assert r.iterations == 0


def test_config_clamp_at_caller():
    """El clamp de config (<1 → 1) lo hace el CALLER (F2), no esta función.
    Con max_iterations=1 (ya clampeado), debe funcionar como single-shot."""
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=1,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=_queue_reextract([PASS_V]),
    )
    assert r.converged is True
    assert r.iterations == 1
    assert r.stop_reason == STOP_CONVERGED


def test_disabled_returns_disabled():
    r = run_convergence_loop(
        enabled=False, runtime=_RUNTIME, max_iterations=2,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=lambda: PASS_V,
    )
    assert r.iterations == 0
    assert r.stop_reason == STOP_DISABLED


def test_defects_first_and_last_recorded():
    """defects_first guarda el inicial; defects_last el final (incl. regression C3).
    Con budget agotado, el último veredicto (con regression) queda en defects_last."""
    repair_with_regression = _make_verdict(
        GateDecision.REPAIR,
        structural=["rf_duplicated"],
        regression=["reg_defect"],
    )
    # cap=1: envía 1 pase, el reextract devuelve repair_with_regression (distintos defectos
    # del inicial REPAIR_A porque hay reg_defect extra). Budget agotado → defects_last tiene reg_defect.
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=1,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=_queue_reextract([repair_with_regression]),
    )
    assert r.defects_first == ["rf_duplicated"]
    assert "reg_defect" in r.defects_last
    assert r.stop_reason == STOP_BUDGET_EXHAUSTED


def test_global_budget_reached():
    """max_iterations=0 con initial REPAIR → STOP_BUDGET_REACHED_GLOBAL, iterations=0 (C2)."""
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=0,
        initial_verdict=REPAIR_A,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=lambda: PASS_V,
    )
    assert r.converged is False
    assert r.iterations == 0
    assert r.global_budget_spent == 0
    assert r.stop_reason == STOP_BUDGET_REACHED_GLOBAL


def test_no_progress_uses_all_defects():
    """C3 — anti-loop usa structural+regression. Si solo structural cambia pero
    regression permanece igual Y structural permanece igual → NO_PROGRESS.
    Si el conjunto COMPLETO cambia → no se aborta (continúa)."""
    # Caso: initial tiene structural A. Siguiente tiene structural A + regression R.
    # El conjunto cambió (A) vs (A + R) → distinto → continúa, no NO_PROGRESS.
    initial = _make_verdict(GateDecision.REPAIR, structural=["rf_duplicated"])
    with_regression = _make_verdict(
        GateDecision.REPAIR,
        structural=["rf_duplicated"],
        regression=["reg_x"],
    )
    # El conjunto inicial es ["rf_duplicated"], el siguiente es ["rf_duplicated", "reg_x"]
    # → distinto → NO abortamos por no_progress; agotamos presupuesto.
    r = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=1,
        initial_verdict=initial,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=_queue_reextract([with_regression]),
    )
    # Con cap=1 agota presupuesto (el conjunto cambió, no hubo NO_PROGRESS)
    assert r.stop_reason == STOP_BUDGET_EXHAUSTED
    assert r.iterations == 1

    # Caso inverso: mismo conjunto structural+regression → NO_PROGRESS.
    same_both = _make_verdict(
        GateDecision.REPAIR,
        structural=["rf_duplicated"],
        regression=["reg_x"],
    )
    initial_both = _make_verdict(
        GateDecision.REPAIR,
        structural=["rf_duplicated"],
        regression=["reg_x"],
    )
    r2 = run_convergence_loop(
        enabled=True, runtime=_RUNTIME, max_iterations=3,
        initial_verdict=initial_both,
        build_repair_message=lambda v: "fix",
        send_fn=_SEND_OK,
        reextract_and_evaluate_fn=_queue_reextract([same_both]),
    )
    assert r2.stop_reason == STOP_NO_PROGRESS
    assert r2.iterations == 1
