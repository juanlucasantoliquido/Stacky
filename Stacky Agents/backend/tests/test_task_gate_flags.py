"""Plan 61 F0 — Tests de los lectores de flags y su registro en FLAG_REGISTRY.

4 casos: default OFF, habilitado por env, ambos flags en registry con attrs correctos.
"""
from __future__ import annotations

import os


def test_task_gate_enabled_by_default(monkeypatch):
    """Sin env var, _task_gate_enabled() == True (promovido 2026-07-15:
    clasificación determinista de defectos, no depende de catálogo)."""
    monkeypatch.delenv("STACKY_TASK_GATE_ENABLED", raising=False)
    # Reimportar para asegurar el lector usa os.getenv en call time
    from api.tickets import _task_gate_enabled
    assert _task_gate_enabled() is True


def test_task_gate_blocking_enabled_by_default(monkeypatch):
    """Sin env var, _task_gate_blocking() == True (promovido 2026-07-15)."""
    monkeypatch.delenv("STACKY_TASK_GATE_BLOCKING", raising=False)
    from api.tickets import _task_gate_blocking
    assert _task_gate_blocking() is True


def test_task_gate_disabled_reads_env(monkeypatch):
    """Con STACKY_TASK_GATE_ENABLED=false, _task_gate_enabled() == False."""
    monkeypatch.setenv("STACKY_TASK_GATE_ENABLED", "false")
    from api.tickets import _task_gate_enabled
    assert _task_gate_enabled() is False


def test_flags_registered_in_registry():
    """Ambos flags del plan 61 están en FLAG_REGISTRY (visibilidad UI garantizada)."""
    from services.harness_flags import FLAG_REGISTRY
    keys = {f.key for f in FLAG_REGISTRY}
    assert "STACKY_TASK_GATE_ENABLED" in keys
    assert "STACKY_TASK_GATE_BLOCKING" in keys
