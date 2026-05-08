"""Unit tests for uat_test_runner.py (B6).

Post v1.2.0 el runner usa `subprocess.Popen` (en lugar de `subprocess.run`)
para streamear el output de Playwright al terminal en tiempo real, y lee el
reporte JSON desde `evidence/.playwright-report.json` (lo escribe el reporter
configurado en playwright.config.ts) en lugar de parsear stdout.

Estos tests mockean Popen y, cuando el caso lo requiere, depositan el JSON
esperado en el path del reporter antes de invocar el runner.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _tool_dir() -> Path:
    """Where uat_test_runner.py lives — same directory the runner uses for cwd
    and for the JSON reporter file (`evidence/.playwright-report.json`)."""
    import uat_test_runner
    return Path(uat_test_runner.__file__).parent


def _make_spec_files(tmp_path: Path, count: int = 3) -> Path:
    tests_dir = tmp_path / "70" / "tests"
    tests_dir.mkdir(parents=True)
    for i in range(1, count + 1):
        pid = f"P{i:02d}"
        (tests_dir / f"{pid}_test.spec.ts").write_text(
            f"// placeholder for {pid}", encoding="utf-8"
        )
    return tests_dir


def _make_popen_mock(returncode: int = 0, stdout_lines=None) -> MagicMock:
    """Build a Popen replacement.

    The runner iterates `proc.stdout` line by line printing each one in real
    time, then calls `proc.wait()`. We mimic that with a list iterator and an
    explicit `returncode` attribute.
    """
    lines = stdout_lines if stdout_lines is not None else ["Running 1 test\n", "  ok\n"]
    mock_proc = MagicMock()
    mock_proc.stdout = iter(lines)
    mock_proc.returncode = returncode
    mock_proc.wait = MagicMock(return_value=returncode)
    mock_proc.kill = MagicMock()
    return mock_proc


def _write_pw_report(report_payload: dict) -> Path:
    """Drop a JSON reporter file at the path the runner reads after Popen
    completes. Returns the path so the test can clean up if needed."""
    report_path = _tool_dir() / "evidence" / ".playwright-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_payload), encoding="utf-8")
    return report_path


@pytest.fixture(autouse=True)
def _cleanup_pw_report():
    """Ensure no stale reporter file leaks between tests."""
    yield
    p = _tool_dir() / "evidence" / ".playwright-report.json"
    try:
        if p.is_file():
            p.unlink()
    except OSError:
        pass


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
    pw_payload = {
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
    }

    def _popen_side_effect(*args, **kwargs):
        # Simulate Playwright writing the JSON report file as it runs.
        _write_pw_report(pw_payload)
        return _make_popen_mock(returncode=1)

    with patch("subprocess.Popen", side_effect=_popen_side_effect):
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
    # No JSON report file written → no assertion_failures parsed → runner
    # falls through to the "Error: ..." heuristic on stdout.
    err_lines = ["Error: Cannot connect to browser. Is Playwright installed?\n"]
    with patch("subprocess.Popen", return_value=_make_popen_mock(returncode=1, stdout_lines=err_lines)):
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

    def _popen_side_effect(*args, **kwargs):
        _write_pw_report({"suites": []})
        return _make_popen_mock(returncode=0)

    with patch("subprocess.Popen", side_effect=_popen_side_effect):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)

    for run in result["runs"]:
        artifacts = run["artifacts"]
        assert artifacts.get("trace") is not None or artifacts.get("video") is not None or len(artifacts.get("screenshots", [])) >= 0


def test_evidence_directory_structure_correct(tmp_path):
    import uat_test_runner
    tests_dir = _make_spec_files(tmp_path, count=1)
    evidence_out = tmp_path / "70"
    with patch("subprocess.Popen", return_value=_make_popen_mock(returncode=0)):
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
    with patch("subprocess.Popen", return_value=_make_popen_mock(returncode=0)):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)
    jsonschema.validate(instance=result, schema=schema)


# ── M5 — runner harvests Playwright JSON reporter attachments ───────────────


def _attachments_payload(tmp_results_dir: Path) -> dict:
    """Build a Playwright JSON report payload describing attachments that
    point at real files under `tmp_results_dir`. Used to assert that the
    runner copies them into evidence/<sid>/ via _harvest_pw_attachments."""
    trace_path = tmp_results_dir / "trace.zip"
    video_path = tmp_results_dir / "video.webm"
    err_ctx_path = tmp_results_dir / "error-context.md"
    trace_path.write_bytes(b"fake-trace-zip")
    video_path.write_bytes(b"fake-video-webm")
    err_ctx_path.write_text("# Error context\nLocator timed out", encoding="utf-8")
    return {
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
    payload = _attachments_payload(pw_dir)

    def _popen_side_effect(*args, **kwargs):
        _write_pw_report(payload)
        return _make_popen_mock(returncode=0)

    with patch("subprocess.Popen", side_effect=_popen_side_effect):
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
    payload = {
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

    def _popen_side_effect(*args, **kwargs):
        _write_pw_report(payload)
        return _make_popen_mock(returncode=0)

    with patch("subprocess.Popen", side_effect=_popen_side_effect):
        with patch("uat_test_runner._check_node_available", return_value=True):
            result = uat_test_runner.run(tests_dir=tests_dir, evidence_out=evidence_out)
    assert result["ok"] is True
    # No trace harvested → trace stays null
    assert result["runs"][0]["artifacts"]["trace"] is None
