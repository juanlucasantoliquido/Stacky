"""Plan 79 — F1: resolver puro de estados (núcleo determinista + vocabulario congelado)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.task_states import (  # noqa: E402
    _APPLICABLE_KEYS,
    applicable_states,
    resolve_task_state_plan,
)


def test_resolves_both_states():
    profile = {"tracker_state_machine": {"developer": {"in_progress": "Active", "next_state_ok": "Done"}}}
    plan = resolve_task_state_plan(profile, "developer")
    assert plan == ("Active", "Done", "config")


def test_missing_agent_type():
    plan = resolve_task_state_plan({"tracker_state_machine": {}}, None)
    assert plan == (None, None, "no_agent_type")


def test_machine_absent():
    plan = resolve_task_state_plan({"tracker_state_machine": {}}, "developer")
    assert plan == (None, None, "absent")


def test_empty_strings_become_none():
    profile = {"tracker_state_machine": {"developer": {"in_progress": "  ", "next_state_ok": ""}}}
    plan = resolve_task_state_plan(profile, "developer")
    assert plan == (None, None, "absent")


def test_applicable_states_excludes_blocked():
    profile = {
        "tracker_state_machine": {
            "developer": {"in_progress": "Active", "next_state_ok": "Done", "blocked_state": "Blocked"}
        }
    }
    plan = resolve_task_state_plan(profile, "developer")
    states = applicable_states(plan)
    assert "Blocked" not in states
    assert states == {"Active", "Done"}


def test_pure_never_raises():
    assert resolve_task_state_plan(None, "developer") == (None, None, "absent")
    assert resolve_task_state_plan(123, "developer") == (None, None, "absent")
    assert resolve_task_state_plan({"tracker_state_machine": "x"}, "developer") == (None, None, "absent")


def test_applicable_vocabulary_frozen():
    assert _APPLICABLE_KEYS == frozenset({"in_progress", "next_state_ok"})
