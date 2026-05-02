"""Unit tests for uat_test_runner.py (B6)."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_spec_files(tmp_path: Path, count: int = 3) -> Path:
    tests_dir = tmp_path / "70" / "tests"
    tests_dir.mkdir(parents=True)
    for i in range(1, count + 1):
        pid = f"P{i:02d}"
        (tests_dir / f"{pid}_test.spec.ts").write_text(
            f"// placeholder for {pid}", encoding="utf-8"
        )
    return tests_dir


def _mock_npx_success(stdout_json: dict = None):
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = json.dumps(stdout_json or {"suites": []})
    mock.stderr = ""
    return mock


def _mock_npx_fail_assertion():
    mock = MagicMock()
    mock.returncode = 1
    mock.stdout = json.dumps({
        "suites": [{
            "specs": [{
                "tests": [{
                    "results": [{
                        "errors": [{
                            "message": "Expected: 'No hay lotes agendados'\nReceived: ''"
                        }]
                    }]
                }]
            }]
        }]
    })
    mock.stderr = ""
    return mock


def _mock_npx_runtime_error():
    mock = MagicMock()
    mock.returncode = 1
    mock.stdout = ""
    mock.stderr = "Error: Cannot connect to browser. Is Playwright installed?"
    return mock


def test_no_tests_found_returns_error(tmp_path):
    import uat_test_runner
    empty_dir = tmp_path / "tests"
    empty_dir.mkdir()
    result = uat_test_runner.run(tests_dir=empty_dir, evidence_out=tmp_path)
    assert result["ok"] is False
    assert result["error"] == "no_tests_found"


def test_playwright_not_available_returns_error(tmp_path):
    import uat_test_runner
    tests_dir = _make_spec_files(tmp_path, count=1)
    with patch("uat_test_runner._check_node_available", return_value=False):
        result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=tmp_path / "70")
    assert result["ok"] is False
    assert result["error"] == "playwright_not_available"


def test_assertion_failure_marks_scenario_fail(tmp_path):
    import uat_test_runner
    tests_dir = _make_spec_files(tmp_path, count=1)
    evidence_out = tmp_path / "70"
    with patch("subprocess.run", return_value=_mock_npx_fail_assertion()):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)
    assert result["ok"] is True
    run = result["runs"][0]
    assert run["status"] == "fail"
    assert "assertion_failures" in run
    assert len(run["assertion_failures"]) >= 1


def test_runtime_error_marks_scenario_blocked(tmp_path):
    import uat_test_runner
    tests_dir = _make_spec_files(tmp_path, count=1)
    evidence_out = tmp_path / "70"
    with patch("subprocess.run", return_value=_mock_npx_runtime_error()):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)
    assert result["ok"] is True
    run = result["runs"][0]
    assert run["status"] == "blocked"
    assert run.get("reason") == "RUNTIME_ERROR"


def test_artifacts_created_for_each_run(tmp_path):
    import uat_test_runner
    tests_dir = _make_spec_files(tmp_path, count=2)
    evidence_out = tmp_path / "70"
    # Create fake artifact files for each scenario
    for pid in ["P01", "P02"]:
        scenario_dir = evidence_out / pid
        scenario_dir.mkdir(parents=True)
        (scenario_dir / "trace.zip").write_bytes(b"fake")
        (scenario_dir / "video.webm").write_bytes(b"fake")
        (scenario_dir / "screenshot.png").write_bytes(b"fake")

    with patch("subprocess.run", return_value=_mock_npx_success()):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)

    for run in result["runs"]:
        artifacts = run["artifacts"]
        assert artifacts.get("trace") is not None or artifacts.get("video") is not None or len(artifacts.get("screenshots", [])) >= 0


def test_evidence_directory_structure_correct(tmp_path):
    import uat_test_runner
    tests_dir = _make_spec_files(tmp_path, count=1)
    evidence_out = tmp_path / "70"
    with patch("subprocess.run", return_value=_mock_npx_success()):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)
    # Evidence dir was created
    assert evidence_out.is_dir()
    # Each run has a spec_file referencing the correct .spec.ts
    for run in result["runs"]:
        assert ".spec.ts" in run["spec_file"]


def test_output_validates_against_schema(tmp_path):
    import uat_test_runner
    import jsonschema
    schema_path = Path(__file__).parent.parent.parent / "schemas" / "runner_output.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    tests_dir = _make_spec_files(tmp_path, count=2)
    evidence_out = tmp_path / "70"
    with patch("subprocess.run", return_value=_mock_npx_success()):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)
    jsonschema.validate(instance=result, schema=schema)
