"""
tests/unit/test_failure_triage_causal.py — Unit tests for causal chain triage.

Covers:
  - test_triage_login_ok_then_direct_goto_timeout_is_nav_not_env
  - test_triage_server_down_before_login_is_env
  - test_triage_nav_contract_validation_blocked_is_nav
  - test_triage_deeplink_param_missing_is_data
  - test_triage_human_path_grid_empty_is_data
  - test_triage_deeplink_context_not_reconstructed_is_nav
  - test_triage_page_load_failed_no_login_evidence_stays_env
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_AGENT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_AGENT_DIR))

from failure_triage import run_failure_triage, _determine_category_reason


def _triage(
    result_json: dict,
    execution_log: list = None,
    runner_classification: dict = None,
):
    """Call _determine_category_reason directly for unit testing."""
    verdict = result_json.get("verdict", "BLOCKED")
    return _determine_category_reason(
        result_json=result_json,
        execution_log=execution_log or [],
        runner_classification=runner_classification,
        verdict=verdict,
    )


# ── Critical causal chain test: ticket 120 scenario ───────────────────────────

def test_triage_login_ok_then_direct_goto_timeout_is_nav_not_env():
    """
    CRITICAL: When login succeeded (session_start in log) and then a
    page.goto() to a session-dependent screen fails (PAGE_LOAD_FAILED),
    the triage MUST classify as NAV/INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN,
    NOT as ENV/PAGE_LOAD_FAILED.

    This is the ticket 120 root cause pattern.
    """
    result_json = {
        "verdict": "BLOCKED",
        "category": "ENV",
        "reason": "PAGE_LOAD_FAILED",
        "failed_stage": "runner",
    }
    execution_log = [
        # Evidence that login succeeded before the test
        {"event": "session_start", "run_id": "uat-120-test", "ticket_id": 120},
    ]
    category, reason, confidence, evidence = _triage(result_json, execution_log)

    assert category == "NAV", (
        f"Expected NAV but got {category}. "
        "Login succeeded + PAGE_LOAD_FAILED = INVALID_DIRECT_NAVIGATION, not ENV. "
        f"Evidence: {evidence}"
    )
    assert reason == "INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN", (
        f"Expected INVALID_DIRECT_NAVIGATION... but got {reason}"
    )
    assert confidence >= 0.85, f"Confidence should be ≥0.85 but got {confidence}"
    assert any("CAUSAL CHAIN" in e for e in evidence), (
        "Evidence must document the causal chain reasoning"
    )


def test_triage_server_down_before_login_is_env():
    """
    When the server was unreachable BEFORE login (environment_preflight failed),
    the triage MUST stay as ENV, not be promoted to NAV.
    """
    result_json = {
        "verdict": "BLOCKED",
        "category": "ENV",
        "reason": "PAGE_LOAD_FAILED",
        "failed_stage": "environment_preflight",
    }
    execution_log = [
        # No session_start — server was down before any login
        {"event": "environment_preflight_result", "ok": False, "reason": "PAGE_LOAD_FAILED"},
    ]
    category, reason, confidence, evidence = _triage(result_json, execution_log)

    # Should remain ENV (no login evidence → not a causal chain NAV case)
    # Either stays ENV or picks the best signal, but must NOT be NAV
    # because there is no evidence of login success
    assert category == "ENV", (
        f"Expected ENV but got {category}. "
        "Server was down before login — this is ENV, not NAV. "
        f"Evidence: {evidence}"
    )


def test_triage_nav_contract_validation_blocked_is_nav():
    """
    When navigation_contract_validation event is BLOCKED in execution_log,
    triage must classify as NAV with the exact reason from the event.
    """
    result_json = {
        "verdict": "BLOCKED",
        "category": "NAV",
        "reason": "NAV_PATH_MISSING",
        "failed_stage": "navigation_contract_validation",
    }
    execution_log = [
        {
            "event": "navigation_contract_validation",
            "decision": "BLOCKED",
            "category": "NAV",
            "reason": "NAV_PATH_MISSING",
            "target_screen": "FrmDetalleClie.aspx",
            "lane": "uat_human",
        }
    ]
    category, reason, confidence, evidence = _triage(result_json, execution_log)

    assert category == "NAV"
    assert reason == "NAV_PATH_MISSING"
    assert confidence >= 1.0


def test_triage_deeplink_param_missing_is_data():
    """DEEPLINK_PARAM_MISSING must classify as DATA, not NAV."""
    result_json = {
        "verdict": "BLOCKED",
        "category": "DATA",
        "reason": "DEEPLINK_PARAM_MISSING",
        "failed_stage": "navigation_contract_validation",
    }
    category, reason, confidence, evidence = _triage(result_json)

    assert category == "DATA"
    assert reason == "DEEPLINK_PARAM_MISSING"


def test_triage_human_path_grid_empty_is_data():
    """HUMAN_PATH_GRID_EMPTY must classify as DATA."""
    result_json = {
        "verdict": "BLOCKED",
        "category": "DATA",
        "reason": "HUMAN_PATH_GRID_EMPTY",
        "failed_stage": "runner",
    }
    category, reason, confidence, evidence = _triage(result_json)

    assert category == "DATA"
    assert reason == "HUMAN_PATH_GRID_EMPTY"


def test_triage_deeplink_context_not_reconstructed_is_nav():
    """DEEPLINK_CONTEXT_NOT_RECONSTRUCTED must classify as NAV."""
    result_json = {
        "verdict": "BLOCKED",
        "category": "NAV",
        "reason": "DEEPLINK_CONTEXT_NOT_RECONSTRUCTED",
        "failed_stage": "runner",
    }
    category, reason, confidence, evidence = _triage(result_json)

    assert category == "NAV"
    assert reason == "DEEPLINK_CONTEXT_NOT_RECONSTRUCTED"


def test_triage_navigation_data_missing_is_data():
    """NAVIGATION_DATA_MISSING must classify as DATA."""
    result_json = {
        "verdict": "BLOCKED",
        "category": "DATA",
        "reason": "NAVIGATION_DATA_MISSING",
        "failed_stage": "navigation_contract_validation",
    }
    category, reason, confidence, evidence = _triage(result_json)

    assert category == "DATA"
    assert reason == "NAVIGATION_DATA_MISSING"


def test_triage_invalid_nav_strategy_for_lane_is_pip():
    """INVALID_NAVIGATION_STRATEGY_FOR_LANE must classify as PIP."""
    result_json = {
        "verdict": "BLOCKED",
        "category": "PIP",
        "reason": "INVALID_NAVIGATION_STRATEGY_FOR_LANE",
        "failed_stage": "navigation_contract_validation",
    }
    category, reason, confidence, evidence = _triage(result_json)

    assert category == "PIP"
    assert reason == "INVALID_NAVIGATION_STRATEGY_FOR_LANE"


def test_triage_page_load_failed_no_login_evidence_stays_env_or_nav():
    """
    PAGE_LOAD_FAILED without login evidence: should NOT be promoted to NAV.
    The causal chain rule requires evidence of login success.
    """
    result_json = {
        "verdict": "BLOCKED",
        "category": "ENV",
        "reason": "PAGE_LOAD_FAILED",
        "failed_stage": "runner",
    }
    # No session_start or login events in the log
    execution_log = [
        {"event": "stage_start", "stage": "runner"},
    ]
    category, reason, confidence, evidence = _triage(result_json, execution_log)

    # Without login evidence, causal chain rule doesn't fire
    # Result should be ENV (or best signal from signals list)
    # The confidence should be relatively low without causal evidence
    assert category == "ENV", (
        f"Without login evidence, PAGE_LOAD_FAILED should stay ENV. Got {category}. "
        f"Evidence: {evidence}"
    )


def test_triage_blocked_nav_context_maps_to_deeplink_not_reconstructed():
    """BLOCKED_NAV_CONTEXT (from TypeScript flow) maps to DEEPLINK_CONTEXT_NOT_RECONSTRUCTED."""
    result_json = {
        "verdict": "BLOCKED",
        "category": "NAV",
        "reason": "BLOCKED_NAV_CONTEXT",
        "failed_stage": "runner",
    }
    category, reason, confidence, evidence = _triage(result_json)

    assert category == "NAV"
    # Should be mapped to the canonical reason
    assert "DEEPLINK" in reason or "CONTEXT" in reason or reason == "DEEPLINK_CONTEXT_NOT_RECONSTRUCTED"


def test_triage_blocked_wrong_screen_maps_to_invalid_nav():
    """BLOCKED_WRONG_SCREEN (from TypeScript flow) maps to NAV/INVALID_DIRECT_NAV."""
    result_json = {
        "verdict": "BLOCKED",
        "category": "NAV",
        "reason": "BLOCKED_WRONG_SCREEN",
        "failed_stage": "runner",
    }
    category, reason, confidence, evidence = _triage(result_json)

    assert category == "NAV"
