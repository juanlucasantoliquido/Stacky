"""Plan 79 — F8: _safe_transition (idempotencia + única escritura de estado)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.task_states import _extract_current_state, _safe_transition  # noqa: E402


def test_extract_state_gitlab_shape():
    assert _extract_current_state({"state": "Done"}) == "Done"


def test_extract_state_ado_shape():
    assert _extract_current_state({"fields": {"System.State": "Active"}}) == "Active"


def test_extract_state_none_when_absent():
    assert _extract_current_state({}) is None
    assert _extract_current_state({"fields": {}}) is None
    assert _extract_current_state(None) is None
    assert _extract_current_state(123) is None


def test_skips_when_already_in_target_gitlab():
    provider = MagicMock()
    provider.get_item.return_value = {"state": "Done"}
    result = _safe_transition(provider, "123", "Done", phase="final")
    assert result["skipped"] is True
    assert result["reason"] == "already_in_state"
    provider.update_item_state.assert_not_called()


def test_skips_when_already_in_target_ado():
    provider = MagicMock()
    provider.get_item.return_value = {"fields": {"System.State": "Done"}}
    result = _safe_transition(provider, "123", "Done", phase="final")
    assert result["skipped"] is True
    assert result["reason"] == "already_in_state"
    provider.update_item_state.assert_not_called()


def test_applies_when_state_differs():
    provider = MagicMock()
    provider.get_item.return_value = {"state": "Active"}
    result = _safe_transition(provider, "123", "Done", phase="final")
    provider.update_item_state.assert_called_once_with("123", "Done")
    assert result["ok"] is True


def test_get_item_failure_still_transitions():
    provider = MagicMock()
    provider.get_item.side_effect = Exception("boom")
    result = _safe_transition(provider, "123", "Done", phase="start")
    provider.update_item_state.assert_called_once_with("123", "Done")
    assert result["ok"] is True


def test_provider_none_uses_legacy():
    legacy_client = MagicMock()
    legacy_fn = MagicMock(return_value=legacy_client)
    result = _safe_transition(None, "123", "Done", phase="final", legacy_client_fn=legacy_fn)
    legacy_client.update_work_item_state.assert_called_once_with(123, "Done")
    assert result["ok"] is True


def test_never_raises_on_update_failure():
    provider = MagicMock()
    provider.get_item.return_value = {}
    provider.update_item_state.side_effect = Exception("fail")
    result = _safe_transition(provider, "123", "Done", phase="final")
    assert result["ok"] is False
    assert "error" in result


def test_case_insensitive_idempotence():
    provider = MagicMock()
    provider.get_item.return_value = {"state": "done"}
    result = _safe_transition(provider, "123", "Done", phase="final")
    assert result["skipped"] is True
    assert result["reason"] == "already_in_state"
    provider.update_item_state.assert_not_called()
