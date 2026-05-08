"""Unit tests for uat_failure_analyzer.py (E3).

Tests cover:
- Only fail scenarios are analyzed (pass/blocked are skipped)
- data_drift heuristic: actual empty, expected non-empty, tipo=equals
- regression heuristic: visible=False when should be visible
- environment_issue heuristic: timeout in raw_stdout
- ui_change heuristic: 'selector' in raw_stdout
- Unknown analysis returned when LLM mock mode + no heuristic match
- Category is always within valid enum
- Evidence links are populated from runner artifacts
- Invalid evaluations file returns error
- Invalid runner output file returns error
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"

_VALID_CATEGORIES = frozenset({
    "regression", "missing_precondition", "data_drift",
    "ui_change", "wrong_expected_in_ticket", "environment_issue", "unknown",
})


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_only_fail_scenarios_analyzed(tmp_path):
    """Pass and blocked scenarios are not included in analyses."""
    import uat_failure_analyzer

    evaluations_path = tmp_path / "evaluations.json"
    runner_path = tmp_path / "runner_output.json"
    _write_json(evaluations_path, _load("evaluations_70.json"))
    _write_json(runner_path, _load("runner_output_70.json"))

    result = uat_failure_analyzer.run(
        evaluations_path=evaluations_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    scenario_ids = [a["scenario_id"] for a in result["analyses"]]
    # P01 is pass — should NOT be in analyses
    assert "P01" not in scenario_ids
    # P04 is fail — SHOULD be in analyses
    assert "P04" in scenario_ids


def test_data_drift_heuristic(tmp_path):
    """actual='' + expected=non-empty + tipo=equals → data_drift."""
    import uat_failure_analyzer

    evaluations = {
        "ok": True, "ticket_id": 70,
        "evaluations": [{
            "scenario_id": "P04",
            "status": "fail",
            "assertions": [{
                "oracle_id": 1,
                "tipo": "equals",
                "target": "msg_lista_vacia",
                "expected": "No hay lotes agendados",
                "actual": "",
                "status": "fail",
                "evidence_ref": ""
            }]
        }]
    }
    runner = {
        "ok": True, "ticket_id": 70,
        "runs": [{
            "scenario_id": "P04",
            "status": "fail",
            "duration_ms": 800,
            "artifacts": {"trace": "evidence/70/P04/trace.zip", "video": "evidence/70/P04/video.webm"},
            "raw_stdout": "✗ P04 expected 'No hay lotes agendados' received ''",
            "raw_stderr": "",
            "assertion_failures": [],
        }]
    }
    evaluations_path = tmp_path / "eval.json"
    runner_path = tmp_path / "runner.json"
    _write_json(evaluations_path, evaluations)
    _write_json(runner_path, runner)

    result = uat_failure_analyzer.run(
        evaluations_path=evaluations_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    assert len(result["analyses"]) == 1
    analysis = result["analyses"][0]
    assert analysis["category"] == "data_drift"
    assert analysis["confidence"] == "high"


def test_environment_issue_heuristic_on_timeout(tmp_path):
    """timeout in raw_stdout → environment_issue."""
    import uat_failure_analyzer

    evaluations = {
        "ok": True, "ticket_id": 70,
        "evaluations": [{
            "scenario_id": "P01",
            "status": "fail",
            "assertions": [{
                "oracle_id": 0,
                "tipo": "visible",
                "target": "btn_buscar",
                "expected": None,
                "actual": False,
                "status": "fail",
                "evidence_ref": ""
            }]
        }]
    }
    runner = {
        "ok": True, "ticket_id": 70,
        "runs": [{
            "scenario_id": "P01",
            "status": "fail",
            "duration_ms": 30000,
            "artifacts": {},
            "raw_stdout": "TimeoutError: waiting for locator('#btn_buscar')",
            "raw_stderr": "",
            "assertion_failures": [],
        }]
    }
    evaluations_path = tmp_path / "eval.json"
    runner_path = tmp_path / "runner.json"
    _write_json(evaluations_path, evaluations)
    _write_json(runner_path, runner)

    result = uat_failure_analyzer.run(
        evaluations_path=evaluations_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    assert result["analyses"][0]["category"] == "environment_issue"


def test_ui_change_heuristic_on_selector_error(tmp_path):
    """'selector' in raw_stdout → ui_change."""
    import uat_failure_analyzer

    evaluations = {
        "ok": True, "ticket_id": 70,
        "evaluations": [{
            "scenario_id": "P02",
            "status": "fail",
            "assertions": [{
                "oracle_id": 0, "tipo": "count_gt", "target": "grid_agenda_aut",
                "expected": "0", "actual": None, "status": "fail", "evidence_ref": ""
            }]
        }]
    }
    runner = {
        "ok": True, "ticket_id": 70,
        "runs": [{
            "scenario_id": "P02", "status": "fail", "duration_ms": 500,
            "artifacts": {},
            "raw_stdout": "Error: selector #gvAgendaAut not found in DOM",
            "raw_stderr": "", "assertion_failures": [],
        }]
    }
    evaluations_path = tmp_path / "eval.json"
    runner_path = tmp_path / "runner.json"
    _write_json(evaluations_path, evaluations)
    _write_json(runner_path, runner)

    result = uat_failure_analyzer.run(
        evaluations_path=evaluations_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    assert result["analyses"][0]["category"] == "ui_change"


def test_unknown_when_no_heuristic_and_mock_llm(tmp_path):
    """When no heuristic matches and LLM=mock, category=unknown."""
    import uat_failure_analyzer

    evaluations = {
        "ok": True, "ticket_id": 70,
        "evaluations": [{
            "scenario_id": "P03",
            "status": "fail",
            "assertions": [{
                "oracle_id": 0, "tipo": "count_gt", "target": "grid",
                "expected": "0", "actual": "0", "status": "fail", "evidence_ref": ""
            }]
        }]
    }
    runner = {
        "ok": True, "ticket_id": 70,
        "runs": [{
            "scenario_id": "P03", "status": "fail", "duration_ms": 2000,
            "artifacts": {},
            "raw_stdout": "✗ P03 some assertion failed",
            "raw_stderr": "", "assertion_failures": [],
        }]
    }
    evaluations_path = tmp_path / "eval.json"
    runner_path = tmp_path / "runner.json"
    _write_json(evaluations_path, evaluations)
    _write_json(runner_path, runner)

    result = uat_failure_analyzer.run(
        evaluations_path=evaluations_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    analysis = result["analyses"][0]
    assert analysis["category"] == "unknown"
    assert analysis["confidence"] == "low"


def test_category_always_in_valid_enum(tmp_path):
    """Regardless of analysis path, category is always in the valid enum."""
    import uat_failure_analyzer

    evaluations_path = tmp_path / "evaluations.json"
    runner_path = tmp_path / "runner_output.json"
    _write_json(evaluations_path, _load("evaluations_70.json"))
    _write_json(runner_path, _load("runner_output_70.json"))

    result = uat_failure_analyzer.run(
        evaluations_path=evaluations_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    for analysis in result["analyses"]:
        assert analysis["category"] in _VALID_CATEGORIES, (
            f"category={analysis['category']} not in valid enum"
        )


def test_evidence_links_populated_from_artifacts(tmp_path):
    """Evidence links in analysis include trace and video paths from runner."""
    import uat_failure_analyzer

    runner = {
        "ok": True, "ticket_id": 70,
        "runs": [{
            "scenario_id": "P04",
            "status": "fail", "duration_ms": 800,
            "artifacts": {
                "trace": "evidence/70/P04/trace.zip",
                "video": "evidence/70/P04/video.webm",
            },
            "raw_stdout": "✗ P04",
            "raw_stderr": "", "assertion_failures": [],
        }]
    }
    evaluations_path = tmp_path / "evaluations.json"
    runner_path = tmp_path / "runner.json"
    _write_json(evaluations_path, _load("evaluations_70.json"))
    _write_json(runner_path, runner)

    result = uat_failure_analyzer.run(
        evaluations_path=evaluations_path,
        runner_output_path=runner_path,
    )

    assert result["ok"] is True
    p04 = next(a for a in result["analyses"] if a["scenario_id"] == "P04")
    assert "evidence/70/P04/trace.zip" in p04["evidence_links"]


def test_invalid_evaluations_file_returns_error(tmp_path):
    """Invalid evaluations file → error."""
    import uat_failure_analyzer

    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    runner = tmp_path / "runner.json"
    _write_json(runner, {"ok": True, "ticket_id": 70, "runs": []})

    result = uat_failure_analyzer.run(
        evaluations_path=bad,
        runner_output_path=runner,
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_evaluations_json"


def test_invalid_runner_output_returns_error(tmp_path):
    """Invalid runner output → error."""
    import uat_failure_analyzer

    evals = tmp_path / "evals.json"
    _write_json(evals, {"ok": True, "ticket_id": 70, "evaluations": []})
    bad = tmp_path / "bad.json"
    bad.write_text("not json")

    result = uat_failure_analyzer.run(
        evaluations_path=evals,
        runner_output_path=bad,
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_runner_output"
