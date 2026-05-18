"""Tests del risk engine determinístico de PM Intelligence Suite."""
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

from services.pm.pm_kpi_engine import compute_sprint_kpis  # noqa: E402
from services.pm.pm_risk_engine import (  # noqa: E402
    DEFAULT_RISK_CONFIG,
    RiskConfig,
    detect_risks,
)


NOW = datetime(2026, 5, 16, 12, 0, 0)
PROJECT = "TestProject"


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
    return {"state": state, "entered_at": NOW - timedelta(days=days_ago), "changed_by": "x"}


def _sprint(start_days_ago: float = 10, remaining_days: int = 3) -> dict:
    return {
        "id": "s42",
        "name": "Sprint 42",
        "path": "Proj\\Sprint 42",
        "start_date": NOW - timedelta(days=start_days_ago),
        "end_date": NOW + timedelta(days=remaining_days),
    }


def _detect(items, *, sprint=None, transitions=None, config=None):
    sprint = sprint or _sprint()
    items = list(items)
    kpis = compute_sprint_kpis(
        sprint=sprint,
        work_items=items,
        transitions_by_ado_id=transitions or {},
        now=NOW,
    )
    return detect_risks(
        project=PROJECT,
        sprint=sprint,
        work_items=items,
        kpis=kpis,
        transitions_by_ado_id=transitions or {},
        config=config or DEFAULT_RISK_CONFIG,
        now=NOW,
    )


# ── delay_velocity_deficit ─────────────────────────────────────────────────────

def test_delay_not_triggered_with_many_days_remaining():
    sprint = _sprint(remaining_days=10)
    items = [_wi(1, state="In Progress", story_points=5)]
    risks = _detect(items, sprint=sprint)
    rules = {r.rule for r in risks}
    assert "delay_velocity_deficit" not in rules


def test_delay_triggered_when_sprint_ending_and_low_completion():
    sprint = _sprint(remaining_days=1)
    items = [
        _wi(1, state="In Progress", story_points=5),
        _wi(2, state="In Progress", story_points=5),
        _wi(3, state="Done", story_points=2),  # 2/12 = ~17% completion
    ]
    risks = _detect(items, sprint=sprint)
    delays = [r for r in risks if r.rule == "delay_velocity_deficit"]
    assert len(delays) == 1
    assert delays[0].category == "DELAY"
    assert delays[0].severity == "HIGH"  # déficit > 25pp


def test_delay_no_trigger_when_completion_high():
    sprint = _sprint(remaining_days=1)
    items = [
        _wi(1, state="Done", story_points=5),
        _wi(2, state="Done", story_points=5),
    ]
    risks = _detect(items, sprint=sprint)
    rules = {r.rule for r in risks}
    assert "delay_velocity_deficit" not in rules


# ── aging_blocked_item ────────────────────────────────────────────────────────

def test_blocked_aging_medium_severity():
    items = [_wi(1, state="Blocked", changed_at=NOW - timedelta(days=3))]
    transitions = {1: [_trans("In Progress", 5), _trans("Blocked", 3)]}
    risks = _detect(items, transitions=transitions)
    blocked = [r for r in risks if r.rule == "aging_blocked_item"]
    assert len(blocked) == 1
    assert blocked[0].severity == "MEDIUM"
    assert 1 in blocked[0].affected_items


def test_blocked_aging_high_severity():
    items = [_wi(1, state="Blocked", changed_at=NOW - timedelta(days=7))]
    transitions = {1: [_trans("In Progress", 10), _trans("Blocked", 7)]}
    risks = _detect(items, transitions=transitions)
    blocked = [r for r in risks if r.rule == "aging_blocked_item"]
    assert len(blocked) == 1
    assert blocked[0].severity == "HIGH"


def test_blocked_aging_separates_severities_into_two_risks():
    items = [
        _wi(1, state="Blocked"),
        _wi(2, state="Blocked"),
    ]
    transitions = {
        1: [_trans("In Progress", 5), _trans("Blocked", 3)],   # MEDIUM
        2: [_trans("In Progress", 10), _trans("Blocked", 6)],  # HIGH
    }
    risks = _detect(items, transitions=transitions)
    blocked = [r for r in risks if r.rule == "aging_blocked_item"]
    assert len(blocked) == 2
    severities = {r.severity for r in blocked}
    assert severities == {"MEDIUM", "HIGH"}


def test_blocked_aging_zero_when_no_blocked_items():
    items = [_wi(1, state="In Progress")]
    risks = _detect(items)
    assert not any(r.rule == "aging_blocked_item" for r in risks)


# ── high_aging_item ────────────────────────────────────────────────────────────

def test_high_aging_medium():
    items = [_wi(1, state="In Progress", created_at=NOW - timedelta(days=15))]
    risks = _detect(items)
    aging = [r for r in risks if r.rule == "high_aging_item"]
    assert len(aging) == 1
    assert aging[0].severity == "MEDIUM"


def test_high_aging_high():
    items = [_wi(1, state="In Progress", created_at=NOW - timedelta(days=35))]
    risks = _detect(items)
    aging = [r for r in risks if r.rule == "high_aging_item"]
    assert len(aging) == 1
    assert aging[0].severity == "HIGH"


def test_high_aging_skips_done_items():
    items = [_wi(1, state="Done", created_at=NOW - timedelta(days=60), closed_at=NOW - timedelta(days=2))]
    risks = _detect(items)
    assert not any(r.rule == "high_aging_item" for r in risks)


# ── scope_creep_detected ───────────────────────────────────────────────────────

def test_scope_creep_detected_when_items_created_after_start():
    sprint = _sprint(start_days_ago=10)
    items = [
        _wi(1, created_at=NOW - timedelta(days=11)),  # pre-sprint, ok
        _wi(2, created_at=NOW - timedelta(days=5)),   # post-start, creep
        _wi(3, created_at=NOW - timedelta(days=3)),   # post-start, creep
    ]
    risks = _detect(items, sprint=sprint)
    creep = [r for r in risks if r.rule == "scope_creep_detected"]
    assert len(creep) == 1
    assert set(creep[0].affected_items) == {2, 3}
    assert creep[0].severity == "MEDIUM"


def test_scope_creep_high_severity_when_many_items():
    sprint = _sprint(start_days_ago=10)
    items = [_wi(i, created_at=NOW - timedelta(days=2)) for i in range(1, 7)]  # 6 items
    risks = _detect(items, sprint=sprint)
    creep = [r for r in risks if r.rule == "scope_creep_detected"]
    assert len(creep) == 1
    assert creep[0].severity == "HIGH"


def test_scope_creep_respects_grace_period():
    sprint = _sprint(start_days_ago=10)
    items = [
        # Creado 12h después del start → dentro del grace de 24h, NO es creep
        _wi(1, created_at=sprint["start_date"] + timedelta(hours=12)),
    ]
    risks = _detect(items, sprint=sprint)
    assert not any(r.rule == "scope_creep_detected" for r in risks)


# ── data_quality_* ─────────────────────────────────────────────────────────────

def test_data_quality_missing_points_warn():
    items = [
        _wi(1, story_points=None),
        _wi(2, story_points=None),
        _wi(3, story_points=5),
        _wi(4, story_points=5),
    ]  # 50% sin puntos → HIGH (>= 50)
    risks = _detect(items)
    dq = [r for r in risks if r.rule == "data_quality_missing_points"]
    assert len(dq) == 1
    assert dq[0].severity == "HIGH"


def test_data_quality_missing_owner_medium():
    items = [
        _wi(1, assigned_to=None),
        _wi(2, assigned_to=None),
        _wi(3, assigned_to="dev@e.com"),
        _wi(4, assigned_to="dev@e.com"),
        _wi(5, assigned_to="dev@e.com"),
    ]  # 40% sin owner → HIGH (>= 30)
    risks = _detect(items)
    dq = [r for r in risks if r.rule == "data_quality_missing_owner"]
    assert len(dq) == 1
    assert dq[0].severity == "HIGH"


def test_data_quality_clean_sprint_no_warnings():
    items = [_wi(1, story_points=3, assigned_to="dev@e.com")]
    risks = _detect(items)
    assert not any(r.category == "DATA_QUALITY" for r in risks)


# ── risk_id determinism ────────────────────────────────────────────────────────

def test_risk_id_is_stable_across_runs():
    items = [_wi(1, state="In Progress", created_at=NOW - timedelta(days=20))]
    risks_run1 = _detect(items)
    risks_run2 = _detect(items)
    ids1 = sorted(r.risk_id for r in risks_run1)
    ids2 = sorted(r.risk_id for r in risks_run2)
    assert ids1 == ids2
    assert all(rid.startswith("RSK-") for rid in ids1)


# ── combined / no-risk scenarios ───────────────────────────────────────────────

def test_clean_sprint_returns_empty():
    sprint = _sprint(remaining_days=10)
    items = [
        _wi(1, story_points=3, state="In Progress", created_at=sprint["start_date"]),
        _wi(2, story_points=5, state="Done", created_at=sprint["start_date"], closed_at=NOW - timedelta(days=1)),
    ]
    risks = _detect(items, sprint=sprint)
    assert risks == []


def test_combined_scenario_emits_multiple_risks():
    sprint = _sprint(start_days_ago=15, remaining_days=1)
    items = [
        _wi(1, state="Blocked", changed_at=NOW - timedelta(days=4),
            created_at=NOW - timedelta(days=20), story_points=None),
        _wi(2, state="In Progress", created_at=NOW - timedelta(days=2),  # scope creep
            story_points=None, assigned_to=None),
    ]
    transitions = {1: [_trans("In Progress", 10), _trans("Blocked", 4)]}
    risks = _detect(items, sprint=sprint, transitions=transitions)
    rules = {r.rule for r in risks}
    # Esperamos al menos: blocked, high_aging, scope_creep, missing_points, missing_owner
    assert "aging_blocked_item" in rules
    assert "high_aging_item" in rules
    assert "scope_creep_detected" in rules
    assert "data_quality_missing_points" in rules
    assert "data_quality_missing_owner" in rules


# ── custom config override ─────────────────────────────────────────────────────

def test_custom_thresholds_change_detection():
    items = [_wi(1, state="Blocked", changed_at=NOW - timedelta(days=1))]
    transitions = {1: [_trans("In Progress", 3), _trans("Blocked", 1)]}
    # Con config default (warn=2): no dispara
    risks_default = _detect(items, transitions=transitions)
    assert not any(r.rule == "aging_blocked_item" for r in risks_default)
    # Con threshold más agresivo: dispara
    aggressive = RiskConfig(blocked_aging_days_warn=0.5, blocked_aging_days_high=2.0)
    risks_aggressive = _detect(items, transitions=transitions, config=aggressive)
    assert any(r.rule == "aging_blocked_item" for r in risks_aggressive)
