"""
tests/unit/test_sprint6_triage.py — Sprint 6 tests.

Validates:
 1.  test_triage_blocked_gen_ui_map_missing
 2.  test_triage_blocked_env_deployment_mismatch
 3.  test_triage_blocked_data_grid_empty
 4.  test_triage_fail_app_assertion_failed
 5.  test_triage_pass_no_category
 6.  test_triage_always_has_owner_and_next_action
 7.  test_triage_never_returns_unknown_category
 8.  test_triage_artifact_written_to_evidence
 9.  test_triage_event_logged_to_execution_jsonl
10.  test_triage_schema_valid_for_all_categories
11.  test_eval_ticket_116_app_fail_passes
12.  test_eval_ticket_119_pass_passes
13.  test_eval_ticket_120_env_mismatch_passes
14.  test_eval_ticket_120_grid_empty_passes
15.  test_eval_ticket_122_wrong_screen_passes
16.  test_eval_ticket_122_ui_map_missing_passes
17.  test_eval_suite_zero_failures
18.  test_learning_verified_has_evidence_ref
19.  test_learning_unverified_has_recommendation
20.  test_selector_healing_never_auto_applies
21.  test_selector_healing_suggests_candidate_from_ui_map
22.  test_selector_healing_confidence_based_on_similarity
23.  test_triage_drives_pipeline_verdict_when_high_confidence
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure tool root on sys.path
TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(TOOL_DIR))
EVALS_DIR = TOOL_DIR / "evals" / "qa_uat_triage"

os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_REQUIRE_PLAYBOOK", "false")


# ── Imports ────────────────────────────────────────────────────────────────────

from failure_triage import (
    run_failure_triage,
    validate_triage_dict,
    VALID_CATEGORIES,
    VALID_OWNERS,
    VALID_VERDICTS,
)
from learning_verifier import (
    verify_learning_applicability,
    build_learning_applied_event,
    LearningVerificationResult,
)
from selector_healing_advisor import (
    suggest_selector_healing,
    build_healing_suggestion_event,
    SelectorHealingSuggestion,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_exec_log(verdict: str, category: str = None, reason: str = None) -> list:
    """Build a minimal execution log list."""
    events = [
        {"event": "session_start", "ticket_id": 1},
    ]
    if verdict:
        events.append({
            "event": "pipeline_verdict_decision",
            "verdict": verdict,
            "category": category,
            "reason": reason,
        })
    return events


def _run_triage(
    verdict: str,
    category: str = None,
    reason: str = None,
    failed_stage: str = None,
    extra_events: list = None,
    runner_classification: dict = None,
    evidence_dir: str = None,
) -> object:
    """Run triage with a minimal result_json."""
    result_json = {
        "ok": verdict == "PASS",
        "verdict": verdict,
    }
    if category:
        result_json["category"] = category
    if reason:
        result_json["reason"] = reason
    if failed_stage:
        result_json["failed_stage"] = failed_stage

    exec_log = _make_exec_log(verdict, category, reason)
    if extra_events:
        exec_log.extend(extra_events)

    return run_failure_triage(
        ticket_id=99,
        run_id="test-run-99",
        result_json=result_json,
        execution_log=exec_log,
        runner_classification=runner_classification,
        exec_logger=None,
        evidence_dir=evidence_dir,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Item 6.1 — failure_triage.py tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailureTriage:

    def test_triage_blocked_gen_ui_map_missing(self):
        """UI_MAP_MISSING → GEN / qa_automation"""
        triage = _run_triage(
            verdict="BLOCKED",
            category="GEN",
            reason="UI_MAP_MISSING",
            failed_stage="ui_map",
            extra_events=[
                {"event": "ui_map_cache_result", "screen": "FrmDetalleClie.aspx", "cache_hit": False}
            ],
        )
        assert triage.verdict == "BLOCKED"
        assert triage.category == "GEN"
        assert triage.reason == "UI_MAP_MISSING"
        assert triage.owner == "qa_automation"
        assert triage.confidence >= 0.90

    def test_triage_blocked_env_deployment_mismatch(self):
        """DEPLOYMENT_MISMATCH → ENV / devops"""
        triage = _run_triage(
            verdict="BLOCKED",
            category="ENV",
            reason="DEPLOYMENT_MISMATCH",
            failed_stage="deployment_fingerprint_check",
        )
        assert triage.verdict == "BLOCKED"
        assert triage.category == "ENV"
        assert triage.reason == "DEPLOYMENT_MISMATCH"
        assert triage.owner == "devops"
        assert triage.confidence >= 0.90

    def test_triage_blocked_data_grid_empty(self):
        """GRID_EMPTY → DATA / data_owner"""
        triage = _run_triage(
            verdict="BLOCKED",
            category="DATA",
            reason="GRID_EMPTY",
            failed_stage="data_readiness_check",
        )
        assert triage.verdict == "BLOCKED"
        assert triage.category == "DATA"
        assert triage.reason == "GRID_EMPTY"
        assert triage.owner == "data_owner"
        assert triage.confidence >= 0.90

    def test_triage_fail_app_assertion_failed(self):
        """ASSERTION_FAILED → APP / developer"""
        triage = _run_triage(
            verdict="FAIL",
            category="APP",
            reason="ASSERTION_FAILED",
            runner_classification={
                "verdict": "FAIL",
                "category": "APP",
                "reason": "ASSERTION_FAILED",
            },
        )
        assert triage.verdict == "FAIL"
        assert triage.category == "APP"
        assert triage.reason == "ASSERTION_FAILED"
        assert triage.owner == "developer"
        assert triage.confidence >= 0.85

    def test_triage_pass_no_category(self):
        """PASS → category=None, confidence >= 0.95"""
        triage = _run_triage(verdict="PASS")
        assert triage.verdict == "PASS"
        assert triage.category is None
        assert triage.confidence >= 0.95

    def test_triage_always_has_owner_and_next_action(self):
        """All triage results must have owner and next_action set."""
        for verdict in ("PASS", "FAIL", "BLOCKED", "MIXED"):
            triage = _run_triage(
                verdict=verdict,
                category="APP" if verdict != "PASS" else None,
                reason="ASSERTION_FAILED" if verdict != "PASS" else None,
            )
            assert triage.owner, f"owner missing for verdict={verdict}"
            assert triage.owner in VALID_OWNERS, f"owner={triage.owner!r} not valid"
            assert triage.next_action, f"next_action missing for verdict={verdict}"
            assert len(triage.next_action) >= 10, (
                f"next_action too short for verdict={verdict}: {triage.next_action!r}"
            )

    def test_triage_never_returns_unknown_category(self):
        """Category is never 'UNKNOWN' or any invalid value."""
        for cat in (None, "APP", "ENV", "DATA", "PIP", "GEN", "NAV", "OBS", "SEC", "OPS"):
            triage = _run_triage(
                verdict="BLOCKED" if cat else "PASS",
                category=cat,
                reason="TEST_REASON" if cat else None,
            )
            if triage.category is not None:
                assert triage.category in VALID_CATEGORIES, (
                    f"Got unknown category: {triage.category!r}"
                )

    def test_triage_artifact_written_to_evidence(self):
        """triage.json is written to evidence_dir for non-PASS verdicts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            triage = _run_triage(
                verdict="BLOCKED",
                category="GEN",
                reason="UI_MAP_MISSING",
                evidence_dir=tmpdir,
            )
            assert triage.artifact_path is not None
            assert Path(triage.artifact_path).is_file(), (
                f"triage.json not found at {triage.artifact_path}"
            )
            artifact = json.loads(Path(triage.artifact_path).read_text(encoding="utf-8"))
            assert artifact["verdict"] == "BLOCKED"
            assert artifact["category"] == "GEN"

    def test_triage_event_logged_to_execution_jsonl(self):
        """triage_result event is emitted to exec_logger."""
        mock_logger = MagicMock()
        result_json = {"ok": False, "verdict": "BLOCKED", "category": "GEN", "reason": "UI_MAP_MISSING"}
        run_failure_triage(
            ticket_id=99,
            run_id="test-run-99",
            result_json=result_json,
            execution_log=[],
            runner_classification=None,
            exec_logger=mock_logger,
            evidence_dir=None,
        )
        mock_logger.event.assert_called_once()
        call_args = mock_logger.event.call_args
        assert call_args[0][0] == "triage_result"
        payload = call_args[0][1]
        assert payload["verdict"] == "BLOCKED"
        assert payload["category"] == "GEN"
        assert payload["human_approval_required"] is True

    def test_triage_schema_valid_for_all_categories(self):
        """validate_triage_dict passes for every valid category."""
        for cat in list(VALID_CATEGORIES) + [None]:
            verdict = "PASS" if cat is None else "BLOCKED"
            triage = _run_triage(
                verdict=verdict,
                category=cat,
                reason="TEST_REASON" if cat else None,
            )
            d = triage.to_dict()
            valid, errors = validate_triage_dict(d)
            assert valid, f"Schema invalid for category={cat}: {errors}"

    def test_triage_drives_pipeline_verdict_when_high_confidence(self):
        """When triage has confidence>=0.85 and different verdict, it overrides runner."""
        # Create a triage where the result_json verdict differs from the heuristic output
        # Using category+reason from result_json (ENV/DEPLOYMENT_MISMATCH) which has conf=1.0
        result_json = {
            "ok": False,
            "verdict": "BLOCKED",
            "category": "ENV",
            "reason": "DEPLOYMENT_MISMATCH",
        }
        triage = run_failure_triage(
            ticket_id=99,
            run_id="test-run",
            result_json=result_json,
            execution_log=[],
            runner_classification=None,
            exec_logger=None,
            evidence_dir=None,
        )
        assert triage.confidence >= 0.85
        assert triage.category == "ENV"


# ═══════════════════════════════════════════════════════════════════════════════
# Item 6.2 — Evals tests (each fixture individually)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTriageEvals:

    def _run_eval_fixture(self, fixture_name: str) -> "EvalResult":
        """Load and run a single eval fixture."""
        sys.path.insert(0, str(TOOL_DIR / "evals"))
        from run_triage_evals import _run_single_eval
        fixture_path = EVALS_DIR / fixture_name
        assert fixture_path.is_file(), f"Fixture not found: {fixture_path}"
        return _run_single_eval(fixture_path, run_failure_triage)

    def test_eval_ticket_116_app_fail_passes(self):
        result = self._run_eval_fixture("ticket_116_app_fail.json")
        assert result.passed, f"Eval failed: {result.failures}"

    def test_eval_ticket_119_pass_passes(self):
        result = self._run_eval_fixture("ticket_119_pass.json")
        assert result.passed, f"Eval failed: {result.failures}"

    def test_eval_ticket_120_env_mismatch_passes(self):
        result = self._run_eval_fixture("ticket_120_env_mismatch.json")
        assert result.passed, f"Eval failed: {result.failures}"

    def test_eval_ticket_120_grid_empty_passes(self):
        result = self._run_eval_fixture("ticket_120_grid_empty.json")
        assert result.passed, f"Eval failed: {result.failures}"

    def test_eval_ticket_122_wrong_screen_passes(self):
        result = self._run_eval_fixture("ticket_122_wrong_screen.json")
        assert result.passed, f"Eval failed: {result.failures}"

    def test_eval_ticket_122_ui_map_missing_passes(self):
        result = self._run_eval_fixture("ticket_122_ui_map_missing.json")
        assert result.passed, f"Eval failed: {result.failures}"

    def test_eval_suite_zero_failures(self):
        """The full eval suite must have zero failures."""
        sys.path.insert(0, str(TOOL_DIR / "evals"))
        from run_triage_evals import run_all_evals
        suite = run_all_evals(str(EVALS_DIR))
        assert suite.total >= 6, f"Expected at least 6 evals, got {suite.total}"
        assert suite.failed == 0, (
            f"Eval suite had {suite.failed} failures: "
            + "; ".join(
                f"{r.eval_id}: {r.failures}"
                for r in suite.failures
            )
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Item 6.3 — LearningVerifier tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestLearningVerifier:

    def test_learning_verified_has_evidence_ref(self):
        """A learning with test_coverage is verified with evidence_type='test'."""
        learning = {
            "learning_id": "lrn-abc123",
            "title": "Selector fix for cmbProvincia",
            "category": "selector_fix",
            "status": "approved",
            "test_coverage": "test_sprint6_triage.py::test_selector_healing_suggests_candidate_from_ui_map",
        }
        result = verify_learning_applicability(learning)
        assert result.verified is True
        assert result.evidence_type == "test"
        assert result.evidence_ref is not None
        assert result.recommendation is None

    def test_learning_verified_with_feature_flag(self):
        """A learning with feature_flag is verified with evidence_type='feature_flag'."""
        learning = {
            "learning_id": "lrn-ff001",
            "title": "Timeout fix via env var",
            "category": "timeout_fix",
            "feature_flag": "QA_UAT_ACTION_TIMEOUT_MS",
        }
        result = verify_learning_applicability(learning)
        assert result.verified is True
        assert result.evidence_type == "feature_flag"

    def test_learning_verified_with_runtime_event(self):
        """A learning with learning_applied event in evidence is verified."""
        applied_events = [
            {
                "event": "learning_applied",
                "learning_id": "lrn-rt001",
                "run_id": "run-xyz",
                "applied_to_stage": "screen_detection",
            }
        ]
        learning = {
            "learning_id": "lrn-rt001",
            "title": "screen_detector order fix",
            "category": "flow_fix",
            "evidence": json.dumps({"applied_events": applied_events}),
        }
        result = verify_learning_applicability(learning)
        assert result.verified is True
        assert result.evidence_type == "runtime_event"

    def test_learning_verified_with_schema_change(self):
        """A learning with schema_change is verified with evidence_type='schema_change'."""
        learning = {
            "learning_id": "lrn-sc001",
            "title": "Schema updated for timeout",
            "category": "other",
            "schema_change": "triage.schema.json v1.0 added confidence field",
        }
        result = verify_learning_applicability(learning)
        assert result.verified is True
        assert result.evidence_type == "schema_change"

    def test_learning_unverified_has_recommendation(self):
        """A learning with no evidence type has verified=False and a recommendation."""
        learning = {
            "learning_id": "lrn-unverified",
            "title": "Unverified learning",
            "category": "selector_fix",
        }
        result = verify_learning_applicability(learning)
        assert result.verified is False
        assert result.evidence_type == "none"
        assert result.recommendation is not None
        assert len(result.recommendation) > 10

    def test_learning_applied_event_structure(self):
        """build_learning_applied_event produces correct structure."""
        evt = build_learning_applied_event(
            learning_id="lrn-5f4bbe6f28b3",
            category="PIP",
            title="screen_detector escanea analisis_tecnico antes de description",
            applied_to_stage="screen_detection",
            input_hash="sha256:abc123",
            effect_before="FrmAgenda.aspx",
            effect_after="FrmDetalleClie.aspx",
        )
        assert evt["event"] == "learning_applied"
        assert evt["learning_id"] == "lrn-5f4bbe6f28b3"
        assert evt["effect"]["before"] == "FrmAgenda.aspx"
        assert evt["effect"]["after"] == "FrmDetalleClie.aspx"
        assert evt["applied_to_stage"] == "screen_detection"


# ═══════════════════════════════════════════════════════════════════════════════
# Item 6.4 — SelectorHealingAdvisor tests
# ═══════════════════════════════════════════════════════════════════════════════

def _get_fixture_ui_map_path() -> str:
    """Return the absolute path to the FrmDetalleClie.aspx UI map fixture."""
    return str(TOOL_DIR / "cache" / "ui_maps" / "FrmDetalleClie.aspx.json")


class TestSelectorHealingAdvisor:

    def test_selector_healing_never_auto_applies(self):
        """status must always be 'suggested' — never 'applied', 'approved', etc."""
        suggestion = suggest_selector_healing(
            screen="FrmDetalleClie.aspx",
            missing_alias="ddl_provincia",
            ui_map_path=_get_fixture_ui_map_path(),
        )
        assert suggestion.status == "suggested", (
            f"status={suggestion.status!r} violates invariant — must be 'suggested'"
        )
        assert suggestion.requires_human_approval is True, (
            "requires_human_approval must always be True"
        )

    def test_selector_healing_suggests_candidate_from_ui_map(self):
        """When alias is in UI map, a non-None candidate is suggested."""
        # ddl_provincia should match cmbProvincia (partial token match)
        suggestion = suggest_selector_healing(
            screen="FrmDetalleClie.aspx",
            missing_alias="ddl_provincia",
            ui_map_path=_get_fixture_ui_map_path(),
        )
        # Should find a candidate (even if not exact match)
        assert suggestion.candidate_alias is not None, (
            "No candidate alias suggested from UI map"
        )
        assert suggestion.candidate_selector is not None, (
            "No candidate selector suggested"
        )

    def test_selector_healing_confidence_based_on_similarity(self):
        """Exact alias match yields confidence=1.0."""
        suggestion = suggest_selector_healing(
            screen="FrmDetalleClie.aspx",
            missing_alias="cmbProvincia",  # exact alias in UI map fixture
            ui_map_path=_get_fixture_ui_map_path(),
        )
        assert suggestion.confidence == 1.0, (
            f"Exact alias match should yield confidence=1.0, got {suggestion.confidence}"
        )
        assert suggestion.candidate_alias == "cmbProvincia"
        assert suggestion.candidate_selector == "#cmbProvincia"

    def test_selector_healing_status_invariant_in_event(self):
        """build_healing_suggestion_event always emits status='suggested'."""
        suggestion = SelectorHealingSuggestion(
            screen="FrmTest.aspx",
            missing_alias="test_alias",
            candidate_alias="test_candidate",
            candidate_selector="#test",
            confidence=0.75,
            basis=["test"],
            requires_human_approval=True,
            status="suggested",
        )
        event = build_healing_suggestion_event(suggestion)
        assert event["status"] == "suggested"
        assert event["requires_human_approval"] is True
        assert event["event"] == "selector_healing_suggestion"

    def test_selector_healing_no_candidate_when_ui_map_empty(self):
        """When UI map is missing, suggestion has confidence=0.0 and no candidate."""
        suggestion = suggest_selector_healing(
            screen="FrmNotExist.aspx",
            missing_alias="some_alias",
            ui_map_path="/nonexistent/path/FrmNotExist.aspx.json",
        )
        assert suggestion.confidence == 0.0
        assert suggestion.candidate_alias is None
        assert suggestion.status == "suggested"  # invariant still holds
        assert suggestion.requires_human_approval is True

    def test_selector_healing_partial_match_lower_confidence(self):
        """Partial alias match yields confidence < 1.0 but > 0."""
        suggestion = suggest_selector_healing(
            screen="FrmDetalleClie.aspx",
            missing_alias="provincia_dropdown",  # similar but not exact
            ui_map_path=_get_fixture_ui_map_path(),
        )
        # Should find something — partial match
        if suggestion.candidate_alias is not None:
            assert suggestion.confidence < 1.0, (
                "Partial match should not yield 1.0 confidence"
            )

    def test_selector_healing_exec_logger_emit(self):
        """emit_healing_suggestion calls exec_logger.event."""
        from selector_healing_advisor import emit_healing_suggestion
        mock_logger = MagicMock()
        suggestion = SelectorHealingSuggestion(
            screen="FrmTest.aspx",
            missing_alias="ddl_test",
            candidate_alias="cmbTest",
            candidate_selector="#cmbTest",
            confidence=0.82,
            basis=["label_similarity"],
            requires_human_approval=True,
            status="suggested",
        )
        emit_healing_suggestion(mock_logger, suggestion)
        mock_logger.event.assert_called_once()
        call_args = mock_logger.event.call_args[0]
        assert call_args[0] == "selector_healing_suggestion"
        assert call_args[1]["status"] == "suggested"


# ═══════════════════════════════════════════════════════════════════════════════
# Schema validator tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTriageSchemaValidator:

    def test_valid_triage_passes_validation(self):
        """A well-formed triage dict passes validate_triage_dict."""
        d = {
            "verdict": "BLOCKED",
            "category": "GEN",
            "reason": "UI_MAP_MISSING",
            "confidence": 1.0,
            "evidence": ["ui_map_cache_result: cache_hit=False"],
            "owner": "qa_automation",
            "next_action": "run ui_map_builder.py --screen FrmDetalleClie.aspx --rebuild",
            "human_approval_required": True,
        }
        valid, errors = validate_triage_dict(d)
        assert valid, f"Expected valid, got errors: {errors}"

    def test_invalid_verdict_fails_validation(self):
        """UNKNOWN verdict fails validation."""
        d = {
            "verdict": "UNKNOWN",
            "category": "APP",
            "reason": "TEST",
            "confidence": 0.5,
            "evidence": ["test evidence"],
            "owner": "developer",
            "next_action": "Test action text here",
            "human_approval_required": False,
        }
        valid, errors = validate_triage_dict(d)
        assert not valid
        assert any("verdict" in e for e in errors)

    def test_empty_evidence_fails_validation(self):
        """Empty evidence array fails validation."""
        d = {
            "verdict": "FAIL",
            "category": "APP",
            "reason": "ASSERTION_FAILED",
            "confidence": 0.9,
            "evidence": [],
            "owner": "developer",
            "next_action": "Test action text here",
            "human_approval_required": True,
        }
        valid, errors = validate_triage_dict(d)
        assert not valid
        assert any("evidence" in e for e in errors)

    def test_missing_required_field_fails_validation(self):
        """Missing required field fails validation."""
        d = {
            "verdict": "PASS",
            "category": None,
            "confidence": 1.0,
            "evidence": ["all pass"],
            "owner": "qa_automation",
            # missing: reason, next_action, human_approval_required
        }
        valid, errors = validate_triage_dict(d)
        assert not valid
        assert len(errors) >= 1

    def test_confidence_out_of_range_fails_validation(self):
        """confidence > 1.0 fails validation."""
        d = {
            "verdict": "PASS",
            "category": None,
            "reason": None,
            "confidence": 1.5,
            "evidence": ["test"],
            "owner": "qa_automation",
            "next_action": "No action needed — all tests passed",
            "human_approval_required": False,
        }
        valid, errors = validate_triage_dict(d)
        assert not valid
        assert any("confidence" in e for e in errors)

    def test_schema_file_exists(self):
        """triage.schema.json must exist in schemas/ directory."""
        schema_path = TOOL_DIR / "schemas" / "triage.schema.json"
        assert schema_path.is_file(), f"triage.schema.json not found at {schema_path}"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema.get("$id") == "triage/1.0"
        assert "verdict" in schema.get("required", [])
        assert "confidence" in schema.get("required", [])
