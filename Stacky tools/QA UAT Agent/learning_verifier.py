"""
learning_verifier.py — Sprint 6.3: Verifiable LearningStore applicability checker.

PURPOSE
-------
A learning marked as `applied=True` (or status="approved") MUST have at least
one of:
  1. test_coverage  — a test that explicitly exercises the learning
  2. feature_flag   — a feature flag that activates it
  3. runtime_event  — a learning_applied event in execution.jsonl
  4. schema_change  — a versioned change in a schema or contract

If none is present, the learning is "unverified" and a recommendation is
provided to the operator.

DESIGN
------
- No side-effects: read-only analysis.
- Does not require the LearningStore SQLite (accepts dicts for testability).
- Emits `learning_applied` events to execution.jsonl when applicability is
  confirmed at runtime.

VERSION
-------
1.0 — Sprint 6
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.learning_verifier")

# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class LearningVerificationResult:
    learning_id: str
    title: str
    verified: bool
    evidence_type: str   # "test" | "feature_flag" | "runtime_event" | "schema_change" | "none"
    evidence_ref: Optional[str]
    recommendation: Optional[str]  # if verified=False, what to do


@dataclass
class LearningApplicationEvent:
    learning_id: str
    category: str
    title: str
    applied_to_stage: str
    input_hash: str
    effect: dict


# ── Main verification function ─────────────────────────────────────────────────

def verify_learning_applicability(learning: dict) -> LearningVerificationResult:
    """
    Verify that a learning has at least one form of verifiable applicability.

    Parameters
    ----------
    learning : dict
        A learning candidate dict with keys:
          learning_id, title, category, status,
          test_coverage (optional), feature_flag (optional),
          runtime_events (optional), schema_change (optional),
          evidence (optional JSON string or dict)

    Returns
    -------
    LearningVerificationResult
    """
    lid = learning.get("learning_id", "unknown")
    title = learning.get("title", "")

    # ── Evidence type 1: test_coverage ────────────────────────────────────────
    test_cov = learning.get("test_coverage")
    if test_cov and _is_truthy_ref(test_cov):
        return LearningVerificationResult(
            learning_id=lid,
            title=title,
            verified=True,
            evidence_type="test",
            evidence_ref=str(test_cov),
            recommendation=None,
        )

    # ── Evidence type 2: feature_flag ────────────────────────────────────────
    ff = learning.get("feature_flag")
    if ff and _is_truthy_ref(ff):
        return LearningVerificationResult(
            learning_id=lid,
            title=title,
            verified=True,
            evidence_type="feature_flag",
            evidence_ref=str(ff),
            recommendation=None,
        )

    # ── Evidence type 3: runtime_event ───────────────────────────────────────
    # Check if evidence dict or runtime_events list contains a learning_applied entry
    runtime_events = learning.get("runtime_events") or []
    if isinstance(runtime_events, str):
        try:
            runtime_events = json.loads(runtime_events)
        except (json.JSONDecodeError, TypeError):
            runtime_events = []

    # Also parse evidence JSON if it contains applied_events
    evidence_raw = learning.get("evidence") or "{}"
    if isinstance(evidence_raw, str):
        try:
            evidence_raw = json.loads(evidence_raw)
        except (json.JSONDecodeError, TypeError):
            evidence_raw = {}

    applied_events = (
        (evidence_raw.get("applied_events") or []) +
        [e for e in runtime_events if e.get("event") == "learning_applied"]
    )

    if applied_events:
        ref_ev = applied_events[0]
        ref_str = (
            f"learning_applied event: run_id={ref_ev.get('run_id', 'unknown')} "
            f"stage={ref_ev.get('applied_to_stage', 'unknown')}"
        )
        return LearningVerificationResult(
            learning_id=lid,
            title=title,
            verified=True,
            evidence_type="runtime_event",
            evidence_ref=ref_str,
            recommendation=None,
        )

    # ── Evidence type 4: schema_change ────────────────────────────────────────
    schema_change = learning.get("schema_change")
    if schema_change and _is_truthy_ref(schema_change):
        return LearningVerificationResult(
            learning_id=lid,
            title=title,
            verified=True,
            evidence_type="schema_change",
            evidence_ref=str(schema_change),
            recommendation=None,
        )

    # ── Not verified ──────────────────────────────────────────────────────────
    recommendation = _build_recommendation(learning)
    return LearningVerificationResult(
        learning_id=lid,
        title=title,
        verified=False,
        evidence_type="none",
        evidence_ref=None,
        recommendation=recommendation,
    )


def _is_truthy_ref(value) -> bool:
    """Return True if value is a non-empty truthy reference."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return bool(value)


def _build_recommendation(learning: dict) -> str:
    """Build a recommendation for an unverified learning."""
    category = learning.get("category", "")
    title = learning.get("title", "")[:60]
    lid = learning.get("learning_id", "unknown")

    if category == "selector_fix":
        return (
            f"Add a unit test in test_sprint6_triage.py that exercises the selector fix "
            f"for learning {lid!r} ({title!r}), or set test_coverage=<test_name>."
        )
    if category == "timeout_fix":
        return (
            f"Set feature_flag to the env var controlling the timeout "
            f"(e.g. QA_UAT_ACTION_TIMEOUT_MS) for learning {lid!r}."
        )
    if category in ("flow_fix", "other"):
        return (
            f"Run the pipeline with this fix active and confirm learning_applied "
            f"event appears in execution.jsonl for learning {lid!r} ({title!r})."
        )
    return (
        f"Provide at least one of: test_coverage, feature_flag, runtime_event, or "
        f"schema_change for learning {lid!r} to make it verifiably applied."
    )


# ── Runtime event builder ─────────────────────────────────────────────────────

def build_learning_applied_event(
    learning_id: str,
    category: str,
    title: str,
    applied_to_stage: str,
    input_hash: str,
    effect_before: str,
    effect_after: str,
) -> dict:
    """
    Build a learning_applied event dict for emission to execution.jsonl.

    The event is ONLY emitted when the learning demonstrably changed the output
    (effect_before != effect_after).
    """
    return {
        "event": "learning_applied",
        "learning_id": learning_id,
        "category": category,
        "title": title,
        "applied_to_stage": applied_to_stage,
        "input_hash": input_hash,
        "effect": {
            "before": effect_before,
            "after": effect_after,
        },
    }


def emit_learning_applied(
    exec_logger,
    learning_id: str,
    category: str,
    title: str,
    applied_to_stage: str,
    input_hash: str,
    effect_before: str,
    effect_after: str,
) -> None:
    """
    Emit a learning_applied event to execution.jsonl via the exec_logger.
    Only emits if effect_before != effect_after (i.e., learning actually changed outcome).
    """
    if effect_before == effect_after:
        logger.debug(
            "learning_verifier: learning %s had no effect (before==after) — not emitting",
            learning_id,
        )
        return
    try:
        payload = build_learning_applied_event(
            learning_id=learning_id,
            category=category,
            title=title,
            applied_to_stage=applied_to_stage,
            input_hash=input_hash,
            effect_before=effect_before,
            effect_after=effect_after,
        )
        exec_logger.event("learning_applied", payload)
    except Exception as exc:  # noqa: BLE001
        logger.debug("learning_verifier: could not emit learning_applied: %s", exc)


# ── Batch verifier ────────────────────────────────────────────────────────────

def verify_all_learnings(learnings: list) -> list:
    """
    Verify a list of learning candidate dicts.
    Returns list of LearningVerificationResult dicts (serializable).
    """
    results = []
    for learning in learnings:
        r = verify_learning_applicability(learning)
        results.append({
            "learning_id": r.learning_id,
            "title": r.title,
            "verified": r.verified,
            "evidence_type": r.evidence_type,
            "evidence_ref": r.evidence_ref,
            "recommendation": r.recommendation,
        })
    return results
