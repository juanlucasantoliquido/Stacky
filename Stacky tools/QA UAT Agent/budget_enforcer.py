"""
budget_enforcer.py — Budget enforcement for QA UAT pipeline runs.

Estimates the cost of a run before execution and blocks or warns if the
configured monthly budget threshold is exceeded.

Environment variables:
    QA_UAT_BUDGET_MONTHLY_USD   float   Monthly budget in USD (default: 200)
    QA_UAT_BUDGET_WARN_THRESHOLD float  Warn fraction 0-1 (default: 0.80)
    QA_UAT_BUDGET_BLOCK_THRESHOLD float Block fraction 0-1 (default: 0.95)
    QA_UAT_BUDGET_PERIOD        str     "monthly" (only supported value for now)

Cost model:
    Each lane has a base_cost_usd + per_scenario_cost_usd * scenario_count.
    Cumulative used_usd is persisted in data/budget_ledger.json.

Usage:
    from budget_enforcer import check_budget

    result = check_budget(
        lane="smoke-uat",
        ticket_id=122,
        scenario_count=4,
        model_tier="standard",
    )
    if not result.allowed:
        print(result.reason)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("stacky.qa_uat.budget_enforcer")

_TOOL_ROOT = Path(__file__).parent
_LEDGER_PATH = _TOOL_ROOT / "data" / "budget_ledger.json"

# ── Lane cost table ───────────────────────────────────────────────────────────

# (base_usd, per_scenario_usd)
_LANE_COSTS: dict[str, tuple[float, float]] = {
    "preflight":          (0.001, 0.000),
    "compile-only":       (0.005, 0.001),
    "smoke-uat":          (0.050, 0.020),
    "full-uat":           (0.100, 0.050),
    "forensic-rerun":     (0.200, 0.100),
    "nightly-regression": (0.150, 0.030),
}

# model_tier multipliers
_TIER_MULTIPLIER: dict[str, float] = {
    "standard":    1.0,
    "forensic":    1.5,
    "triage_only": 0.5,
}

# Lanes that are always allowed unless extreme abuse (> 100 runs/day)
_ALWAYS_ALLOW_LANES = frozenset(["preflight", "compile-only"])

# Daily run abuse threshold for cheap lanes
_CHEAP_LANE_DAILY_LIMIT = 100


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class BudgetCheckResult:
    allowed: bool
    lane: str
    estimated_cost_usd: float
    budget_remaining_usd: float
    budget_total_usd: float
    used_usd: float
    decision: str          # "allow" | "warn" | "block"
    reason: str | None


# ── Ledger helpers ────────────────────────────────────────────────────────────

def _load_ledger() -> dict:
    """Load the budget ledger from disk. Returns empty ledger if missing."""
    if not _LEDGER_PATH.exists():
        return {"period": _current_period(), "used_usd": 0.0, "runs": []}
    try:
        with _LEDGER_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        # Reset ledger if period has changed
        if data.get("period") != _current_period():
            _logger.info("Budget period rolled over — resetting ledger")
            return {"period": _current_period(), "used_usd": 0.0, "runs": []}
        return data
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Could not load budget ledger: %s — starting fresh", exc)
        return {"period": _current_period(), "used_usd": 0.0, "runs": []}


def _save_ledger(ledger: dict) -> None:
    """Persist the budget ledger to disk."""
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER_PATH.open("w", encoding="utf-8") as fh:
            json.dump(ledger, fh, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Could not persist budget ledger: %s", exc)


def _current_period() -> str:
    """Return current billing period key (e.g. '2026-05')."""
    now = datetime.now(tz=timezone.utc)
    period = os.getenv("QA_UAT_BUDGET_PERIOD", "monthly")
    if period == "monthly":
        return now.strftime("%Y-%m")
    return now.strftime("%Y-%m-%d")  # daily fallback


def _count_cheap_lane_runs_today(ledger: dict, lane: str) -> int:
    """Count how many times a cheap lane has run today."""
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return sum(
        1 for r in ledger.get("runs", [])
        if r.get("lane") == lane and r.get("date", "").startswith(today)
    )


# ── Main function ─────────────────────────────────────────────────────────────

def check_budget(
    lane: str,
    ticket_id: int,
    scenario_count: int,
    model_tier: str = "standard",
    exec_logger=None,
    _record_to_ledger: bool = False,
) -> BudgetCheckResult:
    """
    Estimate cost and check against configured budget thresholds.

    Does NOT deduct from the ledger unless _record_to_ledger=True (called by
    the pipeline after a run completes, not before).

    Args:
        lane:             One of the 6 supported lane names.
        ticket_id:        Work item ID (for ledger tracing).
        scenario_count:   Number of scenarios in this run.
        model_tier:       "standard" | "forensic" | "triage_only"
        exec_logger:      Optional ExecutionLogger to emit budget_check event.
        _record_to_ledger: Internal — set True to persist cost after run.

    Returns:
        BudgetCheckResult with allowed, decision, reason, and budget figures.
    """
    # Env-var config
    budget_total = float(os.getenv("QA_UAT_BUDGET_MONTHLY_USD", "200"))
    warn_threshold = float(os.getenv("QA_UAT_BUDGET_WARN_THRESHOLD", "0.80"))
    block_threshold = float(os.getenv("QA_UAT_BUDGET_BLOCK_THRESHOLD", "0.95"))

    # Cost estimation
    base, per_scenario = _LANE_COSTS.get(lane, (0.10, 0.05))
    tier_mult = _TIER_MULTIPLIER.get(model_tier, 1.0)
    estimated_cost = round((base + per_scenario * max(0, scenario_count)) * tier_mult, 4)

    # Load ledger
    ledger = _load_ledger()
    used_usd = round(float(ledger.get("used_usd", 0.0)), 4)
    remaining = round(budget_total - used_usd, 4)
    used_fraction = used_usd / budget_total if budget_total > 0 else 0.0

    # ── Decision logic ────────────────────────────────────────────────────────

    # Cheap lanes: always allow unless abuse
    if lane in _ALWAYS_ALLOW_LANES:
        daily_count = _count_cheap_lane_runs_today(ledger, lane)
        if daily_count >= _CHEAP_LANE_DAILY_LIMIT:
            decision = "block"
            reason = f"cheap_lane_abuse_{lane}_{daily_count}_runs_today"
            allowed = False
        else:
            decision = "allow"
            reason = None
            allowed = True

    # Expensive lanes — block threshold
    elif used_fraction >= block_threshold and lane in ("full-uat", "nightly-regression"):
        decision = "block"
        reason = f"budget_at_{int(used_fraction * 100)}_percent_block_threshold_{int(block_threshold * 100)}"
        allowed = False

    # forensic-rerun near limit: require explicit reason (handled by caller)
    elif lane == "forensic-rerun" and used_fraction >= 0.90:
        decision = "warn"
        reason = f"forensic_rerun_budget_at_{int(used_fraction * 100)}_percent_requires_reason"
        allowed = True  # warn, not block — operator must provide reason

    # Generic block threshold
    elif used_fraction >= block_threshold:
        decision = "block"
        reason = f"budget_at_{int(used_fraction * 100)}_percent_block_threshold_{int(block_threshold * 100)}"
        allowed = False

    # Warn threshold
    elif used_fraction >= warn_threshold:
        decision = "warn"
        reason = f"budget_at_{int(used_fraction * 100)}_percent"
        allowed = True

    else:
        decision = "allow"
        reason = None
        allowed = True

    result = BudgetCheckResult(
        allowed=allowed,
        lane=lane,
        estimated_cost_usd=estimated_cost,
        budget_remaining_usd=remaining,
        budget_total_usd=budget_total,
        used_usd=used_usd,
        decision=decision,
        reason=reason,
    )

    # Optionally record the run to the ledger (after completion, not before)
    if _record_to_ledger and allowed:
        ledger["used_usd"] = round(used_usd + estimated_cost, 4)
        ledger.setdefault("runs", []).append({
            "ticket_id": ticket_id,
            "lane": lane,
            "estimated_cost_usd": estimated_cost,
            "model_tier": model_tier,
            "scenario_count": scenario_count,
            "date": datetime.now(tz=timezone.utc).isoformat(),
        })
        _save_ledger(ledger)

    # Emit event
    event: dict = {
        "event": "budget_check",
        "lane": lane,
        "estimated_cost_usd": estimated_cost,
        "budget_remaining_usd": remaining,
        "budget_total_usd": budget_total,
        "used_usd": used_usd,
        "decision": decision,
        "reason": reason,
    }
    if exec_logger is not None:
        try:
            exec_logger.event("budget_check", event)
        except Exception:  # noqa: BLE001
            pass

    if decision == "block":
        _logger.warning(
            "Budget check BLOCKED lane=%s ticket=%s reason=%s remaining=%.2f",
            lane, ticket_id, reason, remaining,
        )
    elif decision == "warn":
        _logger.warning(
            "Budget check WARN lane=%s ticket=%s reason=%s remaining=%.2f",
            lane, ticket_id, reason, remaining,
        )
    else:
        _logger.debug(
            "Budget check OK lane=%s ticket=%s estimated=%.4f remaining=%.2f",
            lane, ticket_id, estimated_cost, remaining,
        )

    return result


def record_run_cost(
    lane: str,
    ticket_id: int,
    scenario_count: int,
    model_tier: str = "standard",
) -> None:
    """
    Deduct the estimated run cost from the budget ledger after a completed run.

    Call this AFTER a run completes, not before.
    """
    check_budget(
        lane=lane,
        ticket_id=ticket_id,
        scenario_count=scenario_count,
        model_tier=model_tier,
        exec_logger=None,
        _record_to_ledger=True,
    )
