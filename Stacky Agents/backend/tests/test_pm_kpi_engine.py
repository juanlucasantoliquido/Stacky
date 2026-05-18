"""Tests del KPI engine determinístico de PM Intelligence Suite.

Sin ADO, sin red, sin DB. Pure unit tests con fixtures sintéticos.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.pm.pm_kpi_engine import (  # noqa: E402
    DEFAULT_STATE_MAP,
    StateMap,
    compute_aging_days,
    compute_blocked_time_days,
    compute_cycle_time_days,
    compute_lead_time_days,
    compute_reopen_count,
    compute_sprint_kpis,
)


NOW = datetime(2026, 5, 16, 12, 0, 0)


def _wi(ado_id: int, **overrides) -> dict:
    base = {
        "ado_id": ado_id,
        "title": f"WI-{ado_id}",
        "work_item_type": "User Story",
        "state": "In Progress",
        "assigned_to": "dev@empresa.com",
        "iteration_path": "Proj\\Sprint 42",
        "story_points": 3,
        "tags": [],
        "created_at": NOW - timedelta(days=5),
        "changed_at": NOW - timedelta(days=1),
        "closed_at": None,
    }
    base.update(overrides)
    return base


def _trans(state: str, days_ago: float) -> dict:
    return {"state": state, "entered_at": NOW - timedelta(days=days_ago), "changed_by": "dev"}


# ── aging ─────────────────────────────────────────────────────────────────────

def test_aging_days_for_open_item():
    wi = _wi(1, created_at=NOW - timedelta(days=10))
    assert compute_aging_days(wi, now=NOW) == pytest.approx(10.0, rel=1e-3)


def test_aging_days_for_closed_item_uses_closed_date():
    wi = _wi(1, state="Done", created_at=NOW - timedelta(days=10), closed_at=NOW - timedelta(days=3))
    # closed - created = 7 días
    assert compute_aging_days(wi, now=NOW) == pytest.approx(7.0, rel=1e-3)


def test_aging_days_none_when_no_created():
    wi = _wi(1, created_at=None)
    assert compute_aging_days(wi, now=NOW) is None


# ── cycle time ─────────────────────────────────────────────────────────────────

def test_cycle_time_basic():
    transitions = [
        _trans("New", days_ago=10),
        _trans("In Progress", days_ago=8),
        _trans("Done", days_ago=2),
    ]
    # active → done: 8 - 2 = 6 días
    assert compute_cycle_time_days(transitions) == pytest.approx(6.0, rel=1e-3)


def test_cycle_time_none_if_not_closed():
    transitions = [_trans("New", 5), _trans("In Progress", 2)]
    assert compute_cycle_time_days(transitions) is None


def test_cycle_time_ignores_done_before_active():
    # caso raro: done sin pasar por active (cierre directo)
    transitions = [_trans("New", 5), _trans("Done", 1)]
    assert compute_cycle_time_days(transitions) is None


# ── lead time ──────────────────────────────────────────────────────────────────

def test_lead_time_basic():
    wi = _wi(1, state="Done", created_at=NOW - timedelta(days=10), closed_at=NOW - timedelta(days=2))
    assert compute_lead_time_days(wi) == pytest.approx(8.0, rel=1e-3)


def test_lead_time_none_when_open():
    wi = _wi(1, closed_at=None)
    assert compute_lead_time_days(wi) is None


# ── blocked time ───────────────────────────────────────────────────────────────

def test_blocked_time_single_block():
    transitions = [
        _trans("In Progress", 10),
        _trans("Blocked", 8),
        _trans("In Progress", 5),
        _trans("Done", 1),
    ]
    # Blocked desde día -8 a día -5 = 3 días
    assert compute_blocked_time_days(transitions, now=NOW) == pytest.approx(3.0, rel=1e-3)


def test_blocked_time_ongoing_block_counts_to_now():
    transitions = [
        _trans("In Progress", 5),
        _trans("Blocked", 2),
    ]
    # Sigue bloqueado: cuenta 2 días hasta ahora
    assert compute_blocked_time_days(transitions, now=NOW) == pytest.approx(2.0, rel=1e-3)


def test_blocked_time_zero_when_never_blocked():
    transitions = [_trans("In Progress", 5), _trans("Done", 1)]
    assert compute_blocked_time_days(transitions, now=NOW) == 0.0


def test_blocked_time_multiple_blocks_sum():
    transitions = [
        _trans("In Progress", 20),
        _trans("Blocked", 18),
        _trans("In Progress", 15),    # block 1: 3 días
        _trans("Blocked", 10),
        _trans("In Progress", 8),     # block 2: 2 días
        _trans("Done", 1),
    ]
    assert compute_blocked_time_days(transitions, now=NOW) == pytest.approx(5.0, rel=1e-3)


# ── reopen count ───────────────────────────────────────────────────────────────

def test_reopen_count_zero_for_normal_flow():
    transitions = [_trans("New", 5), _trans("In Progress", 3), _trans("Done", 1)]
    assert compute_reopen_count(transitions) == 0


def test_reopen_count_one_reopen():
    transitions = [
        _trans("In Progress", 10),
        _trans("Done", 7),
        _trans("In Progress", 5),
        _trans("Done", 1),
    ]
    assert compute_reopen_count(transitions) == 1


def test_reopen_count_two_reopens():
    transitions = [
        _trans("In Progress", 20),
        _trans("Done", 15),
        _trans("In Progress", 12),    # reopen 1
        _trans("Done", 8),
        _trans("Blocked", 5),         # reopen 2 (done → blocked también cuenta)
        _trans("Done", 1),
    ]
    assert compute_reopen_count(transitions) == 2


# ── sprint KPIs ────────────────────────────────────────────────────────────────

def test_sprint_completion_rate_uses_story_points_when_available():
    sprint = {"id": "s42", "name": "Sprint 42", "end_date": NOW + timedelta(days=3)}
    items = [
        _wi(1, state="Done", story_points=5),
        _wi(2, state="In Progress", story_points=3),
        _wi(3, state="Done", story_points=2),
    ]
    kpis = compute_sprint_kpis(sprint=sprint, work_items=items, now=NOW)
    assert kpis.committed_story_points == 10
    assert kpis.completed_story_points == 7
    assert kpis.completion_rate_pct == 70.0


def test_sprint_completion_rate_falls_back_to_items_without_points():
    sprint = {"id": "s42", "name": "Sprint 42", "end_date": NOW + timedelta(days=3)}
    items = [
        _wi(1, state="Done", story_points=None),
        _wi(2, state="Done", story_points=None),
        _wi(3, state="In Progress", story_points=None),
        _wi(4, state="In Progress", story_points=None),
    ]
    kpis = compute_sprint_kpis(sprint=sprint, work_items=items, now=NOW)
    assert kpis.completion_rate_pct == 50.0
    assert kpis.items_without_estimation == 4


def test_sprint_bug_rate():
    sprint = {"id": "s42", "name": "Sprint 42", "end_date": NOW + timedelta(days=3)}
    items = [
        _wi(1, work_item_type="User Story"),
        _wi(2, work_item_type="Bug"),
        _wi(3, work_item_type="Bug"),
        _wi(4, work_item_type="Task"),
    ]
    kpis = compute_sprint_kpis(sprint=sprint, work_items=items, now=NOW)
    assert kpis.bug_count == 2
    assert kpis.bug_rate_pct == 50.0


def test_sprint_data_quality_warning_when_many_items_lack_points():
    sprint = {"id": "s42", "name": "Sprint 42", "end_date": NOW + timedelta(days=3)}
    items = [
        _wi(1, story_points=None),
        _wi(2, story_points=None),
        _wi(3, story_points=5),
    ]
    kpis = compute_sprint_kpis(sprint=sprint, work_items=items, now=NOW)
    warnings = [w["warning_type"] for w in kpis.data_quality_warnings]
    assert "missing_story_points" in warnings


def test_sprint_days_remaining():
    sprint = {"id": "s42", "name": "Sprint 42", "end_date": NOW + timedelta(days=4)}
    kpis = compute_sprint_kpis(sprint=sprint, work_items=[_wi(1)], now=NOW)
    assert kpis.days_remaining == 4


def test_sprint_empty_emits_warning():
    sprint = {"id": "s42", "name": "Sprint 42", "end_date": NOW + timedelta(days=3)}
    kpis = compute_sprint_kpis(sprint=sprint, work_items=[], now=NOW)
    assert kpis.total_items == 0
    warnings = [w["warning_type"] for w in kpis.data_quality_warnings]
    assert "empty_sprint" in warnings


def test_sprint_uses_transitions_for_cycle_time_avg():
    sprint = {"id": "s42", "name": "Sprint 42", "end_date": NOW + timedelta(days=3)}
    items = [
        _wi(1, state="Done"),
        _wi(2, state="Done"),
    ]
    transitions_by_id = {
        1: [_trans("In Progress", 10), _trans("Done", 4)],   # 6 días
        2: [_trans("In Progress", 8), _trans("Done", 4)],    # 4 días
    }
    kpis = compute_sprint_kpis(
        sprint=sprint,
        work_items=items,
        transitions_by_ado_id=transitions_by_id,
        now=NOW,
    )
    assert kpis.avg_cycle_time_days == pytest.approx(5.0, rel=1e-3)


# ── StateMap customization ─────────────────────────────────────────────────────

def test_custom_state_map_recognizes_project_specific_states():
    custom = StateMap(
        active=frozenset({"en curso"}),
        done=frozenset({"terminado"}),
        blocked=frozenset({"trabado"}),
        new=frozenset({"nuevo"}),
    )
    transitions = [
        _trans("Nuevo", 10),
        _trans("En curso", 8),
        _trans("Trabado", 5),
        _trans("En curso", 3),
        _trans("Terminado", 1),
    ]
    assert compute_cycle_time_days(transitions, state_map=custom) == pytest.approx(7.0, rel=1e-3)
    assert compute_blocked_time_days(transitions, state_map=custom, now=NOW) == pytest.approx(2.0, rel=1e-3)
