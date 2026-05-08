"""Unit tests for uat_dossier_builder.py (B7)."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"
TOOL_DIR = Path(__file__).parent.parent.parent


def _runner_output() -> dict:
    return json.loads((FIXTURES / "runner_output_70.json").read_text(encoding="utf-8"))


def _ticket_data() -> dict:
    return json.loads((FIXTURES / "ticket_70.json").read_text(encoding="utf-8"))


def _build_dossier(tmp_path: Path, runner_override: dict = None) -> tuple:
    import uat_dossier_builder
    runner = runner_override or _runner_output()
    runner_path = tmp_path / "runner_output.json"
    runner_path.write_text(json.dumps(runner), encoding="utf-8")
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(json.dumps(_ticket_data()), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = uat_dossier_builder.run(
        runner_output_path=runner_path,
        ticket_path=ticket_path,
        out_dir=out_dir,
    )
    return result, out_dir


def test_dossier_built_successfully_for_ticket_70(tmp_path):
    result, out_dir = _build_dossier(tmp_path)
    assert result["ok"] is True, result
    assert result["ticket_id"] == 70
    assert (out_dir / "dossier.json").is_file()
    assert (out_dir / "DOSSIER_UAT.md").is_file()
    assert (out_dir / "ado_comment.html").is_file()


def test_ado_comment_contains_idempotence_marker(tmp_path):
    _, out_dir = _build_dossier(tmp_path)
    html = (out_dir / "ado_comment.html").read_text(encoding="utf-8")
    marker_re = re.compile(
        r'<!--\s*stacky-qa-uat:run\s+id="[^"]+"\s+hash="[^"]+"\s*-->',
        re.IGNORECASE,
    )
    assert marker_re.search(html), f"Idempotence marker not found in ado_comment.html:\n{html[:200]}"


def test_hash_is_sha256_of_comment_content(tmp_path):
    import uat_dossier_builder
    result, out_dir = _build_dossier(tmp_path)
    comment_hash = result.get("comment_hash")
    assert comment_hash, "comment_hash must be present in dossier result"
    assert len(comment_hash) == 64, "SHA-256 hex must be 64 chars"
    # Verify it's a valid hex string
    int(comment_hash, 16)


def test_verdict_pass_when_all_pass(tmp_path):
    import uat_dossier_builder
    runner = _runner_output()
    for run in runner["runs"]:
        run["status"] = "pass"
    runner["pass"] = len(runner["runs"])
    runner["fail"] = 0
    runner["blocked"] = 0
    result, _ = _build_dossier(tmp_path, runner_override=runner)
    assert result["verdict"] == "PASS"


def test_verdict_fail_when_one_fails(tmp_path):
    runner = _runner_output()  # already has P04 as fail
    result, _ = _build_dossier(tmp_path, runner_override=runner)
    assert result["verdict"] == "FAIL"


def test_verdict_blocked_when_all_blocked(tmp_path):
    runner = _runner_output()
    for run in runner["runs"]:
        run["status"] = "blocked"
        run["reason"] = "RUNTIME_ERROR"
    runner["pass"] = 0
    runner["fail"] = 0
    runner["blocked"] = len(runner["runs"])
    result, _ = _build_dossier(tmp_path, runner_override=runner)
    assert result["verdict"] == "BLOCKED"


def test_verdict_mixed_when_fail_and_blocked(tmp_path):
    runner = _runner_output()
    runner["runs"][0]["status"] = "fail"
    runner["runs"][1]["status"] = "blocked"
    runner["runs"][1]["reason"] = "RUNTIME_ERROR"
    runner["pass"] = len(runner["runs"]) - 2
    runner["fail"] = 1
    runner["blocked"] = 1
    result, _ = _build_dossier(tmp_path, runner_override=runner)
    assert result["verdict"] == "MIXED"


def test_missing_artifact_returns_error(tmp_path):
    import uat_dossier_builder
    result = uat_dossier_builder.run(
        runner_output_path=tmp_path / "nonexistent.json",
        ticket_path=tmp_path / "ticket.json",
        out_dir=tmp_path / "out",
    )
    assert result["ok"] is False
    assert result["error"] == "missing_artifact"


def test_executive_summary_length_constraint(tmp_path):
    result, _ = _build_dossier(tmp_path)
    summary = result.get("executive_summary", "")
    assert len(summary) <= 600, f"executive_summary too long: {len(summary)} chars"
    assert len(summary) > 0


def test_dossier_json_validates_against_schema(tmp_path):
    import jsonschema
    _, out_dir = _build_dossier(tmp_path)
    schema_path = TOOL_DIR / "schemas" / "dossier.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    dossier = json.loads((out_dir / "dossier.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=dossier, schema=schema)


# ── Regression tests for false-negative FAIL verdicts (added in v1.2.0) ────────
#
# These tests pin the architectural invariant that a runner.status="fail"
# caused by a Playwright runtime error (timeout, overlay, bad selector) MUST
# NOT propagate to a global FAIL verdict. Otherwise the agent reports product
# defects that do not exist (the ticket-70 false-negative incident).

def _build_dossier_with_evaluations(tmp_path: Path, runner: dict, evaluations: dict) -> tuple:
    """Helper that wires both runner_output.json and evaluations.json so we
    exercise the consolidated-status path."""
    import uat_dossier_builder
    runner_path = tmp_path / "runner_output.json"
    runner_path.write_text(json.dumps(runner), encoding="utf-8")
    eval_path = tmp_path / "evaluations.json"
    eval_path.write_text(json.dumps(evaluations), encoding="utf-8")
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(json.dumps(_ticket_data()), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = uat_dossier_builder.run(
        runner_output_path=runner_path,
        ticket_path=ticket_path,
        out_dir=out_dir,
        evaluations_path=eval_path,
    )
    return result, out_dir


def _minimal_runner(scenario_id: str, status: str, raw_stdout: str = "",
                    assertion_failures: list = None) -> dict:
    """One-scenario runner_output.json fixture."""
    run = {
        "scenario_id": scenario_id,
        "spec_file": f"evidence/test/tests/{scenario_id}.spec.ts",
        "status": status,
        "duration_ms": 1000,
        "artifacts": {"trace": None, "video": None, "screenshots": [],
                      "console_log": None, "network_log": None},
        "raw_stdout": raw_stdout,
        "raw_stderr": "",
    }
    if assertion_failures:
        run["assertion_failures"] = assertion_failures
    return {
        "ok": True,
        "ticket_id": 70,
        "total": 1,
        "pass": 1 if status == "pass" else 0,
        "fail": 1 if status == "fail" else 0,
        "blocked": 1 if status == "blocked" else 0,
        "runs": [run],
    }


def test_evaluator_review_status_blocks_runner_fail(tmp_path):
    """When evaluator returns review (could not decide), the dossier must
    NOT propagate the runner's technical fail to a product FAIL verdict."""
    runner = _minimal_runner(
        "P01", "fail",
        raw_stdout="something exploded",
        assertion_failures=[{"message": "Error: not visible", "expected": "y", "actual": ""}],
    )
    evaluations = {
        "ok": True, "ticket_id": 70,
        "evaluations": [{"scenario_id": "P01", "status": "review",
                         "assertions": [{"oracle_id": 0, "tipo": "visible",
                                         "target": "x", "expected": "y",
                                         "actual": None, "status": "review",
                                         "evidence_ref": ""}]}],
    }
    result, _ = _build_dossier_with_evaluations(tmp_path, runner, evaluations)
    assert result["verdict"] == "BLOCKED", (
        "review evaluator status must reclassify runner.fail to BLOCKED, not FAIL"
    )
    assert result["scenarios"][0]["status"] == "blocked"
    assert result["context"]["fail"] == 0
    assert result["context"]["blocked"] == 1


def test_evaluator_real_fail_propagates_as_fail(tmp_path):
    """When evaluator confirms a real product defect (status=fail with a
    concrete oracle expected/actual mismatch), the dossier MUST emit FAIL."""
    runner = _minimal_runner("P01", "fail")
    evaluations = {
        "ok": True, "ticket_id": 70,
        "evaluations": [{
            "scenario_id": "P01", "status": "fail",
            "assertions": [{
                "oracle_id": 0, "tipo": "equals",
                "target": "msg_lista_vacia",
                "expected": "No hay lotes agendados", "actual": "",
                "status": "fail", "evidence_ref": "",
            }],
        }],
    }
    result, _ = _build_dossier_with_evaluations(tmp_path, runner, evaluations)
    assert result["verdict"] == "FAIL"
    assert result["scenarios"][0]["status"] == "fail"


def test_runner_fail_with_locator_fill_timeout_is_reclassified_blocked(tmp_path):
    """`TimeoutError: locator.fill: Timeout` is a defect of the test action
    sequence (page not ready, wrong selector, wrong value format), NOT a
    product defect. Must reclassify to BLOCKED test_generator_defect."""
    runner = _minimal_runner(
        "P04", "fail",
        raw_stdout="TimeoutError: locator.fill: Timeout 10000ms exceeded.",
        assertion_failures=[{
            "message": "TimeoutError: locator.fill: Timeout 10000ms exceeded.",
            "expected": "", "actual": "",
        }],
    )
    # No evaluations.json -> heuristic path must trigger.
    import uat_dossier_builder
    runner_path = tmp_path / "runner_output.json"
    runner_path.write_text(json.dumps(runner), encoding="utf-8")
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(json.dumps(_ticket_data()), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = uat_dossier_builder.run(
        runner_output_path=runner_path,
        ticket_path=ticket_path,
        out_dir=out_dir,
    )
    assert result["verdict"] == "BLOCKED"
    assert result["scenarios"][0]["status"] == "blocked"
    assert result["scenarios"][0].get("reason", "").startswith("test_generator_defect:")


def test_runner_fail_with_intercepted_pointer_events_is_blocked(tmp_path):
    """Click blocked by another open dropdown is a stale-DOM defect of the
    spec, not a product bug."""
    runner = _minimal_runner(
        "P05", "fail",
        raw_stdout=(
            "TimeoutError: locator.click: Timeout 10000ms exceeded.\n"
            "<a id=\"ddlAcciones\">Exportar Agendas</a> from <ul id=\"ddlAcciones_ddl\" "
            "class=\"dropdown-content\"> subtree intercepts pointer events"
        ),
    )
    import uat_dossier_builder
    runner_path = tmp_path / "runner_output.json"
    runner_path.write_text(json.dumps(runner), encoding="utf-8")
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(json.dumps(_ticket_data()), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = uat_dossier_builder.run(
        runner_output_path=runner_path,
        ticket_path=ticket_path,
        out_dir=out_dir,
    )
    assert result["verdict"] == "BLOCKED"
    assert "test_generator_defect:click_blocked_by_overlay" == result["scenarios"][0]["reason"]


def test_runner_fail_against_input_field_label_is_blocked(tmp_path):
    """The ticket-70 P01 case: oracle pointed at a layout label
    (input-field-label class), not at a runtime message. The toBeHidden() on
    a label that is always rendered is an oracle/compiler defect."""
    runner = _minimal_runner(
        "P01", "fail",
        raw_stdout=(
            "Expected: hidden\nReceived: visible\n"
            "locator resolved to <div id=\"c_lblAgendaUsu\" "
            "class=\"col s10 input-field-label\">Agendados por Usuario</div>"
        ),
    )
    import uat_dossier_builder
    runner_path = tmp_path / "runner_output.json"
    runner_path.write_text(json.dumps(runner), encoding="utf-8")
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(json.dumps(_ticket_data()), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = uat_dossier_builder.run(
        runner_output_path=runner_path,
        ticket_path=ticket_path,
        out_dir=out_dir,
    )
    assert result["verdict"] == "BLOCKED", (
        "Layout label false-positive must NOT bubble up as a product FAIL"
    )
    assert result["scenarios"][0]["reason"].startswith("test_generator_defect:")


def test_context_counts_recomputed_after_reclassification(tmp_path):
    """Counts in dossier.context must reflect the consolidated status, not
    the raw runner counts. Otherwise the dossier would self-contradict."""
    # Runner says 3 fail, 0 blocked
    runner = {
        "ok": True, "ticket_id": 70, "total": 3, "pass": 0, "fail": 3, "blocked": 0,
        "runs": [
            {"scenario_id": "P01", "spec_file": "x", "status": "fail",
             "duration_ms": 1, "artifacts": {},
             "raw_stdout": "TimeoutError: locator.fill: Timeout"},
            {"scenario_id": "P02", "spec_file": "x", "status": "fail",
             "duration_ms": 1, "artifacts": {},
             "raw_stdout": "intercepts pointer events"},
            {"scenario_id": "P03", "spec_file": "x", "status": "fail",
             "duration_ms": 1, "artifacts": {},
             "raw_stdout": "element is not visible"},
        ],
    }
    import uat_dossier_builder
    runner_path = tmp_path / "runner_output.json"
    runner_path.write_text(json.dumps(runner), encoding="utf-8")
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(json.dumps(_ticket_data()), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = uat_dossier_builder.run(
        runner_output_path=runner_path,
        ticket_path=ticket_path,
        out_dir=out_dir,
    )
    assert result["context"]["fail"] == 0
    assert result["context"]["blocked"] == 3
    assert result["verdict"] == "BLOCKED"
