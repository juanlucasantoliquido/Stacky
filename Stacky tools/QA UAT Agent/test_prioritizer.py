"""
test_prioritizer.py — Heuristic test prioritizer for QA UAT scenarios.

Orders UAT scenarios by expected value before sending to the runner, so that
the time-to-first-actionable-failure is minimized.

Scoring (interpretable, no ML):
    score = (
        0.30 * business_risk_score      # high=1.0, medium=0.6, low=0.3
        0.20 * recent_failure_score     # failed in last 30d = 1.0
        0.15 * changed_screen_score     # screen recently modified = 1.0
        0.10 * low_flake_bonus          # flake_rate < 0.05 = 1.0
        0.10 * fast_test_bonus          # estimated_seconds < 30 = 1.0
        0.10 * historical_bug_density   # % runs ending in APP/FAIL
        0.05 * manual_priority          # P0=1.0, P1=0.6, P2=0.3
    )

Usage:
    from test_prioritizer import prioritize_scenarios

    result = prioritize_scenarios(
        scenarios=compiled_scenarios,
        history=previous_run_events,
        changed_screens=["FrmDetalleClie.aspx"],
        time_budget_seconds=720,
    )
    for ps in result.selected:
        print(ps.scenario_id, ps.score, ps.reasons)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

_logger = logging.getLogger("stacky.qa_uat.test_prioritizer")

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class PrioritizedScenario:
    scenario_id: str
    score: float                   # 0.0 - 1.0
    estimated_seconds: int
    reasons: list[str]             # human-readable score contributions
    original_scenario: dict


@dataclass
class PrioritizationResult:
    selected: list[PrioritizedScenario]
    excluded: list[dict]
    time_budget_seconds: int
    estimated_total_seconds: int


# ── Scoring constants ─────────────────────────────────────────────────────────

_W_BUSINESS_RISK    = 0.30
_W_RECENT_FAILURE   = 0.20
_W_CHANGED_SCREEN   = 0.15
_W_LOW_FLAKE        = 0.10
_W_FAST_TEST        = 0.10
_W_HIST_BUG_DENSITY = 0.10
_W_MANUAL_PRIORITY  = 0.05

_BUSINESS_RISK_MAP  = {"high": 1.0, "medium": 0.6, "low": 0.3, "critical": 1.0}
_PRIORITY_MAP       = {"P0": 1.0, "P1": 0.6, "P2": 0.3, "P3": 0.1}
_FLAKE_THRESHOLD    = 0.05      # flake_rate below this → bonus
_FAST_THRESHOLD_S   = 30        # estimated_seconds below this → bonus
_RECENT_DAYS        = 30        # window for "recent failure"
_DEFAULT_SECONDS    = 60        # assumed duration when not specified

# Failure verdicts that count toward bug density
_FAIL_VERDICTS = frozenset(["FAIL", "APP", "BLOCKED"])


# ── History indexing ──────────────────────────────────────────────────────────

def _build_history_index(history: list[dict]) -> dict[str, dict]:
    """
    Build a per-scenario index from flat execution history events.

    Expected event shape (from execution.jsonl runner_summary scenario_results):
        {"scenario_id": "RF-008-CA-01", "status": "PASS|FAIL|BLOCKED", "timestamp": "...Z"}

    Returns {scenario_id: {"total": N, "failures": N, "last_fail_ts": str | None, "flake_count": N}}
    """
    index: dict[str, dict] = {}

    for event in (history or []):
        sid = event.get("scenario_id") or event.get("id")
        if not sid:
            continue
        if sid not in index:
            index[sid] = {"total": 0, "failures": 0, "last_fail_ts": None, "flake_count": 0}

        index[sid]["total"] += 1
        status = (event.get("status") or event.get("verdict") or "").upper()

        if status in _FAIL_VERDICTS:
            index[sid]["failures"] += 1
            ts = event.get("timestamp") or event.get("completed_at")
            if ts:
                index[sid]["last_fail_ts"] = ts

        # Count flakes: same scenario_id appears multiple times with mixed results
        # A simplified heuristic: if scenario has both pass and fail runs, count as flaky
        if status == "PASS" and index[sid]["failures"] > 0:
            index[sid]["flake_count"] += 1

    return index


# ── Score computation ─────────────────────────────────────────────────────────

def _compute_score(
    scenario: dict,
    history_idx: dict,
    changed_screens: list[str],
) -> tuple[float, int, list[str]]:
    """
    Compute priority score for a single scenario.

    Returns (score, estimated_seconds, reasons).
    score is clamped to [0.0, 1.0].
    """
    sid = scenario.get("scenario_id") or scenario.get("id") or "unknown"
    reasons: list[str] = []
    score = 0.0

    # 1. Business risk
    risk_raw = (scenario.get("business_risk") or scenario.get("risk") or "medium").lower()
    risk_score = _BUSINESS_RISK_MAP.get(risk_raw, 0.6)
    score += _W_BUSINESS_RISK * risk_score
    reasons.append(f"business_risk={risk_raw}({risk_score:.1f})")

    # 2. Recent failure
    hist = history_idx.get(sid, {})
    recent_fail = 0.0
    last_fail_ts = hist.get("last_fail_ts")
    if last_fail_ts:
        try:
            last_fail_dt = datetime.fromisoformat(last_fail_ts.replace("Z", "+00:00"))
            days_ago = (datetime.now(tz=timezone.utc) - last_fail_dt).days
            if days_ago <= _RECENT_DAYS:
                recent_fail = max(0.0, 1.0 - days_ago / _RECENT_DAYS)
                reasons.append(f"recent_failure={days_ago}d_ago(score={recent_fail:.2f})")
        except (ValueError, TypeError):
            pass
    score += _W_RECENT_FAILURE * recent_fail

    # 3. Changed screen
    screen = scenario.get("screen") or scenario.get("pantalla") or ""
    changed_score = 1.0 if screen in (changed_screens or []) else 0.0
    if changed_score:
        reasons.append(f"screen_recently_changed={screen}")
    score += _W_CHANGED_SCREEN * changed_score

    # 4. Low flake bonus
    total = hist.get("total", 0)
    flake_count = hist.get("flake_count", 0)
    flake_rate = (flake_count / total) if total > 0 else 0.0
    low_flake = 1.0 if flake_rate < _FLAKE_THRESHOLD else 0.0
    score += _W_LOW_FLAKE * low_flake
    if low_flake:
        reasons.append(f"low_flake_rate={flake_rate:.3f}")
    else:
        reasons.append(f"high_flake_rate={flake_rate:.3f}(penalty)")

    # 5. Fast test bonus
    est_seconds = int(scenario.get("estimated_seconds") or scenario.get("estimated_duration_s") or _DEFAULT_SECONDS)
    fast_bonus = 1.0 if est_seconds < _FAST_THRESHOLD_S else 0.0
    score += _W_FAST_TEST * fast_bonus
    if fast_bonus:
        reasons.append(f"fast_test={est_seconds}s")

    # 6. Historical bug density
    failures = hist.get("failures", 0)
    bug_density = (failures / total) if total > 0 else 0.0
    score += _W_HIST_BUG_DENSITY * bug_density
    if bug_density > 0:
        reasons.append(f"hist_bug_density={bug_density:.2f}({failures}/{total})")

    # 7. Manual priority
    prio_raw = (scenario.get("priority") or scenario.get("prioridad") or "P1").upper()
    prio_score = _PRIORITY_MAP.get(prio_raw, 0.3)
    score += _W_MANUAL_PRIORITY * prio_score
    reasons.append(f"manual_priority={prio_raw}({prio_score:.1f})")

    # Clamp to [0.0, 1.0]
    score = max(0.0, min(1.0, round(score, 4)))

    return score, est_seconds, reasons


# ── Main function ─────────────────────────────────────────────────────────────

def prioritize_scenarios(
    scenarios: list[dict],
    history: list[dict] | None = None,
    changed_screens: list[str] | None = None,
    time_budget_seconds: int = 720,
    exec_logger=None,
) -> PrioritizationResult:
    """
    Order scenarios by priority score and select within time_budget_seconds.

    Args:
        scenarios:            List of compiled scenario dicts.
        history:              Flat list of previous run events (from execution.jsonl).
        changed_screens:      Screens modified recently (from deployment diff).
        time_budget_seconds:  Max total estimated seconds; scenarios that exceed
                              the budget are moved to excluded.
        exec_logger:          Optional ExecutionLogger for the priority event.

    Returns:
        PrioritizationResult with selected (ordered high→low) and excluded lists.
    """
    if not scenarios:
        result = PrioritizationResult(
            selected=[], excluded=[],
            time_budget_seconds=time_budget_seconds,
            estimated_total_seconds=0,
        )
        _emit_event(exec_logger, result, top_scenario=None, top_score=0.0)
        return result

    history_idx = _build_history_index(history or [])
    changed = list(changed_screens or [])

    # Score all candidates
    scored: list[PrioritizedScenario] = []
    for scenario in scenarios:
        score, est_secs, reasons = _compute_score(scenario, history_idx, changed)
        sid = scenario.get("scenario_id") or scenario.get("id") or "unknown"
        scored.append(PrioritizedScenario(
            scenario_id=sid,
            score=score,
            estimated_seconds=max(1, est_secs),
            reasons=reasons,
            original_scenario=scenario,
        ))

    # Sort descending by score
    scored.sort(key=lambda ps: ps.score, reverse=True)

    # Apply time budget
    selected: list[PrioritizedScenario] = []
    excluded: list[dict] = []
    accumulated = 0

    for ps in scored:
        if accumulated + ps.estimated_seconds <= time_budget_seconds:
            selected.append(ps)
            accumulated += ps.estimated_seconds
        else:
            excluded.append(ps.original_scenario)

    top_scenario = selected[0].scenario_id if selected else None
    top_score = selected[0].score if selected else 0.0

    result = PrioritizationResult(
        selected=selected,
        excluded=excluded,
        time_budget_seconds=time_budget_seconds,
        estimated_total_seconds=accumulated,
    )

    _logger.info(
        "Prioritization: total=%d selected=%d excluded=%d "
        "top=%s(%.2f) budget=%ds estimated=%ds",
        len(scenarios), len(selected), len(excluded),
        top_scenario, top_score, time_budget_seconds, accumulated,
    )

    _emit_event(exec_logger, result, top_scenario, top_score)
    return result


def _emit_event(exec_logger, result: PrioritizationResult, top_scenario, top_score) -> None:
    """Emit test_prioritization_result event to execution.jsonl."""
    if exec_logger is None:
        return
    event = {
        "event": "test_prioritization_result",
        "total_candidates": len(result.selected) + len(result.excluded),
        "selected": len(result.selected),
        "excluded": len(result.excluded),
        "time_budget_seconds": result.time_budget_seconds,
        "estimated_total_seconds": result.estimated_total_seconds,
        "top_scenario": top_scenario,
        "top_score": top_score,
    }
    try:
        exec_logger.event("test_prioritization_result", event)
    except Exception:  # noqa: BLE001
        pass
