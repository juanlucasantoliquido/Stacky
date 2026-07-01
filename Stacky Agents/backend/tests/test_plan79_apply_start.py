"""Plan 79 — F2: aplicar estado-en-progreso al iniciar la tarea (paridad 3 runtimes)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.task_states import apply_task_start_state  # noqa: E402


def _profile(in_progress="Active"):
    return {"tracker_state_machine": {"developer": {"in_progress": in_progress, "next_state_ok": "Done"}}}


def test_start_applies_in_progress_when_enabled():
    provider = MagicMock()
    provider.get_item.side_effect = Exception("no item")
    with patch("harness.task_states.deterministic_task_states_enabled", return_value=True), \
         patch("services.client_profile.load_effective_client_profile", return_value=_profile()):
        apply_task_start_state(project_name="demo", agent_type="developer", ado_id=42, provider=provider)
    provider.update_item_state.assert_called_once_with("42", "Active")


def test_start_noop_when_flag_off():
    provider = MagicMock()
    with patch("harness.task_states.deterministic_task_states_enabled", return_value=False):
        result = apply_task_start_state(project_name="demo", agent_type="developer", ado_id=42, provider=provider)
    provider.update_item_state.assert_not_called()
    assert result == {"skipped": True, "reason": "flag_off"}


def test_start_noop_without_in_progress():
    provider = MagicMock()
    profile = {"tracker_state_machine": {"developer": {"next_state_ok": "Done"}}}
    with patch("harness.task_states.deterministic_task_states_enabled", return_value=True), \
         patch("services.client_profile.load_effective_client_profile", return_value=profile):
        apply_task_start_state(project_name="demo", agent_type="developer", ado_id=42, provider=provider)
    provider.update_item_state.assert_not_called()


def test_start_provider_failure_does_not_break():
    provider = MagicMock()
    provider.get_item.side_effect = Exception("no item")
    provider.update_item_state.side_effect = Exception("boom")
    with patch("harness.task_states.deterministic_task_states_enabled", return_value=True), \
         patch("services.client_profile.load_effective_client_profile", return_value=_profile()):
        result = apply_task_start_state(project_name="demo", agent_type="developer", ado_id=42, provider=provider)
    assert result.get("ok") is False
    assert "error" in result


def test_start_parity_helper_is_runner_agnostic():
    """El mismo helper, llamado con los kwargs que cada runtime tendría a mano,
    se comporta idéntico: mismo provider mock recibe la misma llamada. Prueba
    la paridad a nivel de contrato sin levantar los 3 runners reales."""
    calls = []

    def _make_provider():
        p = MagicMock()
        p.get_item.side_effect = Exception("no item")
        p.update_item_state.side_effect = lambda item_id, state: calls.append((item_id, state))
        return p

    runtime_kwargs = [
        {"project_name": "demo", "agent_type": "developer", "ado_id": 42},   # Claude Code CLI
        {"project_name": "demo", "agent_type": "developer", "ado_id": 42},   # Codex CLI
        {"project_name": "demo", "agent_type": "developer", "ado_id": 42},   # GitHub Copilot (open_chat)
    ]
    with patch("harness.task_states.deterministic_task_states_enabled", return_value=True), \
         patch("services.client_profile.load_effective_client_profile", return_value=_profile()):
        for kwargs in runtime_kwargs:
            provider = _make_provider()
            apply_task_start_state(provider=provider, **kwargs)

    assert calls == [("42", "Active")] * 3
