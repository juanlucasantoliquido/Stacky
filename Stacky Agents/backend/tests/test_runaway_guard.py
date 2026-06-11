"""H5 — Tests del RunawayGuard.

Cubre los 4 casos de aceptación del plan:
1. Límites 0/0.0 → observe() nunca dispara.
2. Excede turnos → razón la primera vez; None la segunda (dispara una sola vez).
3. Excede costo → retorna razón.
4. Ambos límites, excede solo uno → dispara.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from harness.runaway_guard import RunLimits, RunawayGuard


# ── 1. Límites 0/0.0 → nunca dispara ─────────────────────────────────────────

def test_no_limits_never_fires():
    guard = RunawayGuard(RunLimits(max_turns=0, max_cost_usd=0.0))
    assert guard.observe(num_turns=1000) is None
    assert guard.observe(num_turns=9999, cost_usd=999.0) is None


def test_zero_turns_limit_ignores_turns():
    guard = RunawayGuard(RunLimits(max_turns=0, max_cost_usd=5.0))
    # turnos ignorados; costo todavía bajo el límite
    assert guard.observe(num_turns=9999, cost_usd=1.0) is None


def test_zero_cost_limit_ignores_cost():
    guard = RunawayGuard(RunLimits(max_turns=10, max_cost_usd=0.0))
    # costo ignorado; turnos todavía bajos
    assert guard.observe(num_turns=5, cost_usd=9999.0) is None


# ── 2. Excede turnos → razón la 1ª vez; None la 2ª ──────────────────────────

def test_exceeds_turns_returns_reason():
    guard = RunawayGuard(RunLimits(max_turns=5, max_cost_usd=0.0))
    assert guard.observe(num_turns=4) is None      # justo por debajo
    reason = guard.observe(num_turns=5)             # exactamente en el límite
    assert reason is not None
    assert "runaway" in reason
    assert "5" in reason


def test_exceeds_turns_fires_only_once():
    guard = RunawayGuard(RunLimits(max_turns=3, max_cost_usd=0.0))
    first = guard.observe(num_turns=3)
    assert first is not None, "primera llamada debe disparar"
    second = guard.observe(num_turns=10)
    assert second is None, "segunda llamada no debe disparar de nuevo"


def test_exceeds_turns_just_below_does_not_fire():
    guard = RunawayGuard(RunLimits(max_turns=10, max_cost_usd=0.0))
    assert guard.observe(num_turns=9) is None


# ── 3. Excede costo → retorna razón ──────────────────────────────────────────

def test_exceeds_cost_returns_reason():
    guard = RunawayGuard(RunLimits(max_turns=0, max_cost_usd=1.0))
    assert guard.observe(cost_usd=0.99) is None
    reason = guard.observe(cost_usd=1.0)
    assert reason is not None
    assert "runaway" in reason
    assert "1.0" in reason


def test_exceeds_cost_fires_only_once():
    guard = RunawayGuard(RunLimits(max_turns=0, max_cost_usd=0.5))
    first = guard.observe(cost_usd=0.5)
    assert first is not None
    assert guard.observe(cost_usd=99.9) is None


# ── 4. Ambos límites, excede solo uno ─────────────────────────────────────────

def test_both_limits_only_turns_exceeded():
    guard = RunawayGuard(RunLimits(max_turns=5, max_cost_usd=10.0))
    reason = guard.observe(num_turns=5, cost_usd=1.0)
    assert reason is not None
    assert "turno" in reason


def test_both_limits_only_cost_exceeded():
    guard = RunawayGuard(RunLimits(max_turns=100, max_cost_usd=2.0))
    reason = guard.observe(num_turns=10, cost_usd=2.0)
    assert reason is not None
    assert "costo" in reason


def test_both_limits_none_exceeded():
    guard = RunawayGuard(RunLimits(max_turns=10, max_cost_usd=5.0))
    assert guard.observe(num_turns=5, cost_usd=1.0) is None


# ── Casos borde ───────────────────────────────────────────────────────────────

def test_observe_with_none_args_never_fires_if_limits_set():
    """Si los valores son None (no disponibles), no debe disparar."""
    guard = RunawayGuard(RunLimits(max_turns=1, max_cost_usd=0.01))
    assert guard.observe(num_turns=None, cost_usd=None) is None


def test_turns_check_before_cost_check():
    """Si ambos se exceden, el mensaje habla de turnos (turno se chequea primero)."""
    guard = RunawayGuard(RunLimits(max_turns=2, max_cost_usd=0.5))
    reason = guard.observe(num_turns=2, cost_usd=0.5)
    assert reason is not None
    assert "turno" in reason
