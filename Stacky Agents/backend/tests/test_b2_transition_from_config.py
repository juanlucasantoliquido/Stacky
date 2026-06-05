"""
Tests de B2 — resolución de transition_state desde la config del empleado
(services.agent_completion_internal._resolve_transition_state_from_config, plan 2026-06-02).

Verifica el mapeo (project, agent) → filename → transition_state:
  - por filename persistido en la execution (camino preferido),
  - fallback por agent_type inferido del filename,
  - None cuando no hay config o el flag está apagado.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def _resolver():
    from services.agent_completion_internal import _resolve_transition_state_from_config
    return _resolve_transition_state_from_config


def test_resolves_by_filename(monkeypatch):
    import project_manager as pm

    monkeypatch.setattr(
        pm, "get_agent_workflow_config",
        lambda project, filename: {"transition_state": "To Do"} if filename == "DevX.agent.md" else {},
    )
    result = _resolver()(
        project_name="X", agent_type="developer",
        agent_filename="DevX.agent.md", execution_id=1,
    )
    assert result == "To Do"


def test_fallback_by_agent_type(monkeypatch):
    import project_manager as pm

    # Sin filename en la execution → buscamos por tipo inferido del filename.
    monkeypatch.setattr(pm, "get_agent_workflow_config", lambda *a, **k: {})
    monkeypatch.setattr(
        pm, "get_project_config",
        lambda project: {
            "agent_workflow_configs": {
                "TechnicalAnalyst.agent.md": {"transition_state": "To Do"},
                "DevPacifico.agent.md": {"transition_state": "Code Review"},
            }
        },
    )
    result = _resolver()(
        project_name="X", agent_type="developer",
        agent_filename=None, execution_id=2,
    )
    assert result == "Code Review"  # filename "Dev..." → developer


def test_none_when_no_config(monkeypatch):
    import project_manager as pm

    monkeypatch.setattr(pm, "get_agent_workflow_config", lambda *a, **k: {})
    monkeypatch.setattr(pm, "get_project_config", lambda project: {"agent_workflow_configs": {}})
    assert _resolver()(
        project_name="X", agent_type="developer", agent_filename="DevX.agent.md", execution_id=3,
    ) is None


def test_flag_off_disables(monkeypatch):
    import project_manager as pm

    monkeypatch.setenv("STACKY_APPLY_TRANSITION_FROM_CONFIG", "off")
    monkeypatch.setattr(pm, "get_agent_workflow_config", lambda *a, **k: {"transition_state": "To Do"})
    assert _resolver()(
        project_name="X", agent_type="developer", agent_filename="DevX.agent.md", execution_id=4,
    ) is None


def test_none_without_project(monkeypatch):
    assert _resolver()(
        project_name=None, agent_type="developer", agent_filename="DevX.agent.md", execution_id=5,
    ) is None
