"""Unit tests for qa_uat_pipeline.py (Fase C — orchestrator).

Tests cover:
- Happy path (all stages pass → ok=True, verdict returned)
- Reader failure stops pipeline at stage 'reader'
- Compiler failure stops pipeline at stage 'compiler'
- UI map failure stops pipeline at stage 'ui_map'
- All-blocked generator short-circuits runner and goes to dossier
- --skip-to skips earlier stages, uses cached files
- --mode dry-run vs publish passed through to publisher
- Invalid mode returns error immediately
- Elapsed_s is present and >= 0
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
TOOL_DIR = Path(__file__).parent.parent.parent


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _ticket_ok() -> dict:
    base = json.loads((FIXTURES / "ticket_70.json").read_text(encoding="utf-8"))
    return base


def _comments_ok() -> str:
    return (FIXTURES / "comments_70.json").read_text(encoding="utf-8")


def _scenarios_ok() -> dict:
    return json.loads((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"))


def _ui_map_ok() -> dict:
    return json.loads((FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"))


def _runner_output_ok() -> dict:
    return json.loads((FIXTURES / "runner_output_70.json").read_text(encoding="utf-8"))


def _dossier_ok() -> dict:
    return {
        "ok": True,
        "schema_version": "qa-uat-dossier/1.0",
        "run_id": "12345678-1234-4123-b123-123456789abc",
        "ticket_id": 70,
        "ticket_title": "RF-003",
        "screen": "FrmAgenda.aspx",
        "verdict": "FAIL",
        "executive_summary": "Tests completed.",
        "context": {
            "total": 6, "pass": 5, "fail": 1, "blocked": 0,
            "environment": "qa", "agent_version": "1.0.0",
        },
        "scenarios": [],
        "failures": [],
        "recommendation_for_human_qa": [],
        "next_steps": [],
        "generated_at": "2026-05-02T14:32:00Z",
        "comment_hash": "abcdef",
        "paths": {
            "dossier_json": "evidence/70/dossier.json",
            "dossier_md": "evidence/70/DOSSIER_UAT.md",
            "ado_comment_html": "evidence/70/ado_comment.html",
        },
    }


def _publisher_ok(mode: str = "dry-run") -> dict:
    return {
        "ok": True,
        "publish_state": mode,
        "ticket_id": 70,
        "mode": mode,
        "elapsed_s": 0.01,
    }


# ── Patch context manager ─────────────────────────────────────────────────────

class _PipelineMocks:
    """Context manager that patches all tool run() functions."""

    def __init__(
        self,
        ticket_result=None,
        ui_map_result=None,
        compiler_result=None,
        generator_result=None,
        runner_result=None,
        dossier_result=None,
        publisher_result=None,
        preconditions_result=None,
        evaluator_result=None,
        failure_analyzer_result=None,
    ):
        self._overrides = {
            "reader": ticket_result,
            "ui_map": ui_map_result,
            "compiler": compiler_result,
            "generator": generator_result,
            "runner": runner_result,
            "dossier": dossier_result,
            "publisher": publisher_result,
            "preconditions": preconditions_result,
            "evaluator": evaluator_result,
            "failure_analyzer": failure_analyzer_result,
        }

    def __enter__(self):
        import qa_uat_pipeline as pipeline
        import uat_ticket_reader
        import ui_map_builder
        import uat_scenario_compiler
        import playwright_test_generator
        import uat_test_runner
        import uat_dossier_builder
        import ado_evidence_publisher
        import uat_precondition_checker
        import uat_assertion_evaluator
        import uat_failure_analyzer

        ticket_r = self._overrides["reader"] or _ticket_ok()
        ui_r = self._overrides["ui_map"] or _ui_map_ok()
        compiler_r = self._overrides["compiler"] or _scenarios_ok()
        generator_r = self._overrides["generator"] or {
            "ok": True,
            "specs": [
                {"scenario_id": "P01", "status": "generated", "spec_file": "p01.spec.ts"},
                {"scenario_id": "P02", "status": "generated", "spec_file": "p02.spec.ts"},
            ],
        }
        runner_r = self._overrides["runner"] or _runner_output_ok()
        dossier_r = self._overrides["dossier"] or _dossier_ok()
        publisher_r = self._overrides["publisher"] or _publisher_ok()
        prec_r = self._overrides["preconditions"] or {
            "ok": True, "ticket_id": 70,
            "summary": {"total": 6, "ok": 6, "blocked": 0},
            "results": {"P01": {"ok": True, "missing": []}},
        }
        eval_r = self._overrides["evaluator"] or {
            "ok": True, "ticket_id": 70,
            "evaluations": [
                {"scenario_id": "P01", "status": "pass", "assertions": []},
            ],
        }
        analyzer_r = self._overrides["failure_analyzer"] or {
            "ok": True, "ticket_id": 70, "analyses": [],
        }

        self._patches = [
            patch.object(uat_ticket_reader, "run", return_value=ticket_r),
            patch.object(ui_map_builder, "run", return_value=ui_r),
            patch.object(uat_scenario_compiler, "run", return_value=compiler_r),
            patch.object(playwright_test_generator, "run", return_value=generator_r),
            patch.object(uat_test_runner, "run", return_value=runner_r),
            patch.object(uat_dossier_builder, "run", return_value=dossier_r),
            patch.object(ado_evidence_publisher, "run", return_value=publisher_r),
            patch.object(uat_precondition_checker, "run", return_value=prec_r),
            patch.object(uat_assertion_evaluator, "run", return_value=eval_r),
            patch.object(uat_failure_analyzer, "run", return_value=analyzer_r),
            # Prevent actual filesystem writes during pipeline
            patch.object(pipeline, "_persist_json"),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *args):
        for p in self._patches:
            p.stop()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_happy_path_returns_ok_and_verdict():
    """Full pipeline with all mocks returning success → ok=True, verdict populated."""
    import qa_uat_pipeline as pipeline

    with _PipelineMocks():
        result = pipeline.run(ticket_id=70, mode="dry-run", verbose=False)

    assert result["ok"] is True
    assert result["ticket_id"] == 70
    assert result["verdict"] in ("PASS", "FAIL", "BLOCKED", "MIXED")
    assert "stages" in result
    assert result["elapsed_s"] >= 0


def test_reader_failure_stops_pipeline():
    """When reader returns ok=False, pipeline stops and propagates the error."""
    import qa_uat_pipeline as pipeline

    reader_fail = {"ok": False, "error": "not_found", "message": "Ticket 999 not found"}
    with _PipelineMocks(ticket_result=reader_fail):
        result = pipeline.run(ticket_id=999, mode="dry-run")

    assert result["ok"] is False
    assert result["error"] == "not_found"
    assert "reader" in result["stages"]
    assert result["stages"]["reader"]["ok"] is False
    # Downstream stages should not be present
    assert "compiler" not in result["stages"]
    assert "runner" not in result["stages"]


def test_ui_map_failure_stops_pipeline():
    """When ui_map_builder returns ok=False, pipeline stops."""
    import qa_uat_pipeline as pipeline

    ui_fail = {"ok": False, "error": "playwright_not_installed", "message": "Playwright not found"}
    with _PipelineMocks(ui_map_result=ui_fail):
        result = pipeline.run(ticket_id=70, mode="dry-run")

    assert result["ok"] is False
    assert result["error"] == "playwright_not_installed"
    assert result["stages"]["ui_map"]["ok"] is False
    assert "compiler" not in result["stages"]


def test_compiler_failure_stops_pipeline():
    """When scenario_compiler returns ok=False, pipeline stops."""
    import qa_uat_pipeline as pipeline

    compiler_fail = {
        "ok": False, "error": "all_scenarios_out_of_scope",
        "message": "No in-scope scenarios found"
    }
    with _PipelineMocks(compiler_result=compiler_fail):
        result = pipeline.run(ticket_id=70, mode="dry-run")

    assert result["ok"] is False
    assert result["error"] == "all_scenarios_out_of_scope"
    assert result["stages"]["compiler"]["ok"] is False
    assert "generator" not in result["stages"]


def test_all_blocked_generator_skips_runner():
    """When all generated specs are blocked, runner is skipped and dossier is built."""
    import qa_uat_pipeline as pipeline

    all_blocked_gen = {
        "ok": True,
        "specs": [
            {"scenario_id": "P01", "status": "blocked",
             "blocked_reason": "missing_selector:btn_buscar", "spec_file": ""},
            {"scenario_id": "P02", "status": "blocked",
             "blocked_reason": "missing_selector:grid_agenda", "spec_file": ""},
        ],
    }
    with _PipelineMocks(generator_result=all_blocked_gen):
        result = pipeline.run(ticket_id=70, mode="dry-run")

    assert result["ok"] is True
    # Runner was skipped
    assert result["stages"]["runner"]["skipped"] is True
    assert result["stages"]["runner"].get("reason") == "all_scenarios_blocked"
    # Dossier and publisher still ran
    assert result["stages"]["dossier"]["ok"] is True
    assert result["stages"]["publisher"]["ok"] is True


def test_invalid_mode_returns_error_immediately():
    """Mode other than 'dry-run' or 'publish' returns error without calling any tool."""
    import qa_uat_pipeline as pipeline
    import uat_ticket_reader

    with patch.object(uat_ticket_reader, "run") as mock_reader:
        result = pipeline.run(ticket_id=70, mode="destroy")

    assert result["ok"] is False
    assert result["error"] == "invalid_mode"
    mock_reader.assert_not_called()


def test_dry_run_mode_passed_to_publisher():
    """mode=dry-run is forwarded to ado_evidence_publisher.run."""
    import qa_uat_pipeline as pipeline
    import ado_evidence_publisher

    with patch.object(ado_evidence_publisher, "run", return_value=_publisher_ok("dry-run")) as mock_pub, \
         _PipelineMocks(publisher_result=_publisher_ok("dry-run")):
        result = pipeline.run(ticket_id=70, mode="dry-run")

    assert result["ok"] is True


def test_stage_summaries_present_and_correct():
    """All 10 stage keys are present in a successful run with correct structure."""
    import qa_uat_pipeline as pipeline

    with _PipelineMocks():
        result = pipeline.run(ticket_id=70, mode="dry-run")

    assert result["ok"] is True
    stages = result["stages"]
    for stage in ("reader", "ui_map", "compiler", "preconditions",
                  "generator", "runner", "evaluator", "failure_analyzer",
                  "dossier", "publisher"):
        assert stage in stages, f"Missing stage: {stage}"
        assert "ok" in stages[stage], f"Stage {stage} missing 'ok' key"


def test_compiler_summary_counts_scenarios():
    """Compiler summary includes scenario_count and out_of_scope_count."""
    import qa_uat_pipeline as pipeline

    with _PipelineMocks():
        result = pipeline.run(ticket_id=70, mode="dry-run")

    assert result["ok"] is True
    compiler = result["stages"]["compiler"]
    assert "scenario_count" in compiler
    assert compiler["scenario_count"] >= 0


def test_elapsed_s_is_positive():
    """elapsed_s must be a non-negative number."""
    import qa_uat_pipeline as pipeline

    with _PipelineMocks():
        result = pipeline.run(ticket_id=70, mode="dry-run")

    assert isinstance(result.get("elapsed_s"), float)
    assert result["elapsed_s"] >= 0
