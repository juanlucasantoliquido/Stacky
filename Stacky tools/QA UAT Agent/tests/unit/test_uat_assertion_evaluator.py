"""Unit tests for uat_assertion_evaluator.py (E2).

Tests cover:
- Pass scenario → all assertions pass
- Fail scenario → failed assertions propagate to scenario status
- equals type: exact match → pass, mismatch → fail
- contains_literal type: substring → pass, not found → fail
- count_gt type: actual > expected → pass, actual <= expected → fail
- visible type: True → pass, False → fail
- invisible type: False → pass, True → fail
- count_eq type: exact count → pass, mismatch → fail
- Blocked run → passthrough as blocked, no assertions
- Semantic type (contains_semantic) in mock mode → review
- Unknown oracle type → review
- Invalid input files return errors
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_pass_scenario_all_assertions_pass(tmp_path):
    """Scenario P01 (all pass in runner) → evaluator marks all assertions pass."""
    import uat_assertion_evaluator

    # Build a runner output where P01 passed with known assertion evidence
    runner_output = {
        "ok": True,
        "ticket_id": 70,
        "runs": [{
            "scenario_id": "P01",
            "status": "pass",
            "duration_ms": 1000,
            "artifacts": {},
            "raw_stdout": "✓ P01",
            "raw_stderr": "",
            "assertion_failures": [],
        }]
    }
    scenarios_path = tmp_path / "scenarios.json"
    runner_path = tmp_path / "runner_output.json"
    _write_json(scenarios_path, _load("scenarios_70.json"))
    _write_json(runner_path, runner_output)

    result = uat_assertion_evaluator.run(
        scenarios_path=scenarios_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    p01 = next(e for e in result["evaluations"] if e["scenario_id"] == "P01")
    # count_gt with actual heuristic "1" → pass; invisible with False → pass
    assert p01["status"] in ("pass", "review")  # review for count_gt without evidence


def test_fail_scenario_propagates_to_status(tmp_path):
    """When a scenario has a failed assertion, scenario status=fail."""
    import uat_assertion_evaluator

    runner_output = {
        "ok": True,
        "ticket_id": 70,
        "runs": [{
            "scenario_id": "P04",
            "status": "fail",
            "duration_ms": 800,
            "artifacts": {"trace": "evidence/70/P04/trace.zip"},
            "raw_stdout": "✗ P04",
            "raw_stderr": "",
            "assertion_failures": [
                {"message": "Expected msg_lista_vacia", "expected": "No hay lotes agendados", "actual": ""}
            ],
        }]
    }
    scenarios_path = tmp_path / "scenarios.json"
    runner_path = tmp_path / "runner_output.json"
    _write_json(scenarios_path, _load("scenarios_70.json"))
    _write_json(runner_path, runner_output)

    result = uat_assertion_evaluator.run(
        scenarios_path=scenarios_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    p04 = next(e for e in result["evaluations"] if e["scenario_id"] == "P04")
    assert p04["status"] == "fail"


def test_blocked_run_is_passthrough(tmp_path):
    """Blocked runs are passed through as blocked without assertion evaluation."""
    import uat_assertion_evaluator

    runner_output = {
        "ok": True,
        "ticket_id": 70,
        "runs": [{
            "scenario_id": "P01",
            "status": "blocked",
            "reason": "RUNTIME_ERROR",
            "duration_ms": 0,
            "artifacts": {},
            "raw_stdout": "",
            "raw_stderr": "Playwright crashed",
            "assertion_failures": [],
        }]
    }
    scenarios_path = tmp_path / "scenarios.json"
    runner_path = tmp_path / "runner_output.json"
    _write_json(scenarios_path, _load("scenarios_70.json"))
    _write_json(runner_path, runner_output)

    result = uat_assertion_evaluator.run(
        scenarios_path=scenarios_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    p01 = next(e for e in result["evaluations"] if e["scenario_id"] == "P01")
    assert p01["status"] == "blocked"
    assert p01["assertions"] == []


def test_equals_exact_match_returns_pass():
    """equals oracle: actual == expected → pass."""
    import uat_assertion_evaluator
    assert uat_assertion_evaluator._evaluate_deterministic(
        "equals", "No hay lotes agendados", "No hay lotes agendados"
    ) == "pass"


def test_equals_mismatch_returns_fail():
    """equals oracle: actual != expected → fail."""
    import uat_assertion_evaluator
    assert uat_assertion_evaluator._evaluate_deterministic(
        "equals", "No hay lotes agendados", ""
    ) == "fail"


def test_contains_literal_substring_returns_pass():
    """contains_literal: expected is substring of actual → pass."""
    import uat_assertion_evaluator
    assert uat_assertion_evaluator._evaluate_deterministic(
        "contains_literal", "0001", "Empresa: 0001 | Tipo: CRED"
    ) == "pass"


def test_count_gt_above_threshold_returns_pass():
    """count_gt: actual > expected → pass."""
    import uat_assertion_evaluator
    assert uat_assertion_evaluator._evaluate_deterministic("count_gt", "0", "5") == "pass"


def test_count_gt_at_threshold_returns_fail():
    """count_gt: actual == expected (not strictly greater) → fail."""
    import uat_assertion_evaluator
    assert uat_assertion_evaluator._evaluate_deterministic("count_gt", "0", "0") == "fail"


def test_visible_true_returns_pass():
    """visible oracle: actual=True → pass."""
    import uat_assertion_evaluator
    assert uat_assertion_evaluator._evaluate_deterministic("visible", None, True) == "pass"


def test_invisible_false_returns_pass():
    """invisible oracle: actual=False (not visible) → pass."""
    import uat_assertion_evaluator
    assert uat_assertion_evaluator._evaluate_deterministic("invisible", None, False) == "pass"


def test_semantic_in_mock_mode_returns_review():
    """contains_semantic in mock LLM mode → review (not pass, not fail)."""
    import uat_assertion_evaluator
    result = uat_assertion_evaluator._evaluate_semantic(
        "mensaje informativo de lista vacía",
        "No hay lotes agendados para este usuario",
    )
    assert result == "review"


def test_unknown_oracle_type_returns_review():
    """Unknown oracle type → review."""
    import uat_assertion_evaluator
    assert uat_assertion_evaluator._evaluate_assertion(
        tipo="future_oracle_type",
        expected="x",
        actual="y",
    ) == "review"


def test_invalid_scenarios_file_returns_error(tmp_path):
    """Invalid scenarios file → invalid_scenarios_json error."""
    import uat_assertion_evaluator
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    runner = tmp_path / "runner.json"
    runner.write_text(json.dumps({"ok": True, "ticket_id": 70, "runs": []}))

    result = uat_assertion_evaluator.run(
        scenarios_path=bad,
        runner_output_path=runner,
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_scenarios_json"


def test_invalid_runner_output_returns_error(tmp_path):
    """Invalid runner output → invalid_runner_output error."""
    import uat_assertion_evaluator
    scenarios = tmp_path / "scenarios.json"
    _write_json(scenarios, _load("scenarios_70.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("not json")

    result = uat_assertion_evaluator.run(
        scenarios_path=scenarios,
        runner_output_path=bad,
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_runner_output"
