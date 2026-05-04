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


# ── M5 — runner harvests Playwright JSON reporter attachments ───────────────


def _mock_npx_with_attachments(tmp_results_dir: Path) -> MagicMock:
    """Build a subprocess.run mock whose stdout mimics Playwright's JSON
    reporter: one failed test with trace.zip / video.webm / error-context.md
    attachments pointing at real files under `tmp_results_dir`. Used to
    assert that the runner copies them into evidence/<sid>/."""
    trace_path = tmp_results_dir / "trace.zip"
    video_path = tmp_results_dir / "video.webm"
    err_ctx_path = tmp_results_dir / "error-context.md"
    trace_path.write_bytes(b"fake-trace-zip")
    video_path.write_bytes(b"fake-video-webm")
    err_ctx_path.write_text("# Error context\nLocator timed out", encoding="utf-8")
    pw_output = {
        "suites": [{
            "specs": [{
                "tests": [{
                    "results": [{
                        "errors": [],
                        "attachments": [
                            {"name": "trace", "contentType": "application/zip",
                             "path": str(trace_path)},
                            {"name": "video", "contentType": "video/webm",
                             "path": str(video_path)},
                            {"name": "error-context", "contentType": "text/markdown",
                             "path": str(err_ctx_path)},
                        ],
                    }],
                }],
            }],
        }],
    }
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = json.dumps(pw_output)
    mock.stderr = ""
    return mock


def test_runner_harvests_trace_and_video_into_evidence_dir(tmp_path):
    """Pre-1.1 the runner returned trace=null/video=null because it scanned
    `evidence/<sid>/` by extension while Playwright deposits artefacts under
    `test-results/<spec>-<project>/`. M5 fixes this by reading the JSON
    reporter `attachments[]` and copying each file into the evidence dir
    under canonical names.
    """
    import uat_test_runner
    tests_dir = _make_spec_files(tmp_path, count=1)
    evidence_out = tmp_path / "70"
    pw_dir = tmp_path / "test-results-fake"
    pw_dir.mkdir()

    with patch("subprocess.run", return_value=_mock_npx_with_attachments(pw_dir)):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)

    assert result["ok"] is True
    run = result["runs"][0]
    sid = run["scenario_id"]

    # Files should now exist with canonical names inside the scenario dir
    sdir = evidence_out / sid
    assert (sdir / "trace.zip").is_file(), "trace.zip not harvested"
    assert (sdir / "video.webm").is_file(), "video.webm not harvested"
    assert (sdir / "error-context.md").is_file(), "error-context.md not harvested"

    # Artefacts dict in the runner output should reflect them
    artifacts = run["artifacts"]
    assert artifacts["trace"] is not None
    assert artifacts["trace"].endswith("trace.zip")
    assert artifacts["video"] is not None
    assert artifacts["video"].endswith("video.webm")
    assert artifacts["error_context"] is not None
    assert artifacts["error_context"].endswith("error-context.md")


def test_runner_harvest_skips_missing_attachment_paths(tmp_path):
    """If Playwright reports an attachment whose path does not exist, the
    runner must skip it gracefully instead of crashing."""
    import uat_test_runner
    tests_dir = _make_spec_files(tmp_path, count=1)
    evidence_out = tmp_path / "70"
    pw_output = {
        "suites": [{
            "specs": [{
                "tests": [{
                    "results": [{
                        "attachments": [
                            {"name": "trace", "contentType": "application/zip",
                             "path": str(tmp_path / "does-not-exist.zip")},
                        ],
                    }],
                }],
            }],
        }],
    }
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = json.dumps(pw_output)
    mock.stderr = ""
    with patch("subprocess.run", return_value=mock):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)
    assert result["ok"] is True
    # No trace harvested → trace stays null
    assert result["runs"][0]["artifacts"]["trace"] is None
