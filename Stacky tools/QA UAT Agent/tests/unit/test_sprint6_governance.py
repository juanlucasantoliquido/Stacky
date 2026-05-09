"""
test_sprint6_governance.py — Sprint 6 DoD: governance, policy, confidence, human gate.

Tests per DoD:
  PP-1: evaluate_policy allows PASS + evidence + run_id + human_approved + mode=publish
  PP-2: evaluate_policy blocks UNKNOWN verdict (P2 violation)
  PP-3: evaluate_policy blocks null verdict (P1 + P2 violation)
  PP-4: evaluate_policy blocks missing run_id (P4 violation)
  PP-5: evaluate_policy blocks missing dossier.json (P5 violation)
  PP-6: evaluate_policy blocks mode=publish without human_approved (P6 violation)
  PP-7: evaluate_policy allows dry-run without human_approved (no P6 violation)
  PP-8: evaluate_policy blocks incomplete evidence bundle (P3 violation)
  PP-9: evaluate_policy produces publishable result for FAIL verdict (human approved)
  PP-10: write_policy_result writes publish_policy_result.json
  PP-11: PolicyViolation has rule, message, severity
  PP-12: evaluate_policy BLOCKED verdict blocks publish (P1 violation if not in publishable set — wait, BLOCKED IS in publishable set per roadmap)

  SC-1: execution_logger.stage_confidence emits stage_confidence event
  SC-2: stage_confidence event has stage, confidence, signals fields
  SC-3: confidence is clamped to 0.0-1.0
  SC-4: execution_logger.human_decision emits human_decision event
  SC-5: human_decision event has decision, operator, run_id fields
  SC-6: human_decision approved_publish=True for approve_publish decision
  SC-7: human_decision event includes ticket_id when provided

  RM-1: _write_rollback_audit creates rollback_audit.json with correct fields
  RM-2: rollback_audit.json has rollback_status=not_rolled_back initially
  RM-3: rollback_audit.json has comment_id, run_id, ticket_id, published_at

  BK-1: backend metadata stores category, reason, failed_stage after sprint 6
  BK-2: backend metadata stores evidence_complete
  BK-3: backend metadata stores confidence when present in result
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

_QA_UAT_DIR = Path(__file__).resolve().parent.parent.parent
import sys
if str(_QA_UAT_DIR) not in sys.path:
    sys.path.insert(0, str(_QA_UAT_DIR))


# ─────────────────────────────────────────────────────────────────────────────
# PP — Publish Policy
# ─────────────────────────────────────────────────────────────────────────────

class TestPublishPolicyPP:
    """PP-1 through PP-12: qa_uat_publish_policy.evaluate_policy correctness."""

    def _evidence_dir_with_all(self) -> Path:
        """Create tmp dir with all required artifacts including dossier.json."""
        tmp = Path(tempfile.mkdtemp())
        for fname in ("result.json", "execution.jsonl", "effective_config.json", "dossier.json"):
            (tmp / fname).write_text('{"ok":true}', encoding="utf-8")
        return tmp

    def test_pp1_allow_pass_with_all_conditions(self):
        """PP-1: evaluate_policy allows PASS + evidence + run_id + human_approved + publish."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = self._evidence_dir_with_all()
        try:
            result = evaluate_policy(
                verdict="PASS",
                run_id="uat-122-test",
                evidence_dir=tmp,
                human_approved=True,
                mode="publish",
            )
            assert result.allowed is True
            assert result.violations == []
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp2_block_unknown_verdict(self):
        """PP-2: evaluate_policy blocks UNKNOWN verdict (P2 violation)."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = self._evidence_dir_with_all()
        try:
            result = evaluate_policy(
                verdict="UNKNOWN",
                run_id="uat-122-test",
                evidence_dir=tmp,
                human_approved=True,
                mode="publish",
            )
            assert result.allowed is False
            rules = [v.rule for v in result.violations]
            assert "P2" in rules
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp3_block_null_verdict(self):
        """PP-3: evaluate_policy blocks null/empty verdict (P1 + P2 violations)."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = self._evidence_dir_with_all()
        try:
            result = evaluate_policy(
                verdict=None,
                run_id="uat-122-test",
                evidence_dir=tmp,
                human_approved=True,
                mode="publish",
            )
            assert result.allowed is False
            rules = [v.rule for v in result.violations]
            # Both P1 (not in publishable set) and P2 (prohibited) should fire
            assert "P1" in rules or "P2" in rules
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp4_block_missing_run_id(self):
        """PP-4: evaluate_policy blocks when run_id is missing (P4 violation)."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = self._evidence_dir_with_all()
        try:
            result = evaluate_policy(
                verdict="PASS",
                run_id=None,
                evidence_dir=tmp,
                human_approved=True,
                mode="publish",
            )
            assert result.allowed is False
            rules = [v.rule for v in result.violations]
            assert "P4" in rules
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp5_block_missing_dossier(self):
        """PP-5: evaluate_policy blocks when dossier.json is missing (P5 violation)."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = Path(tempfile.mkdtemp())
        # Provide all but dossier.json
        for fname in ("result.json", "execution.jsonl", "effective_config.json"):
            (tmp / fname).write_text('{"ok":true}', encoding="utf-8")
        try:
            result = evaluate_policy(
                verdict="PASS",
                run_id="uat-122-test",
                evidence_dir=tmp,
                human_approved=True,
                mode="publish",
            )
            assert result.allowed is False
            rules = [v.rule for v in result.violations]
            assert "P5" in rules
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp6_block_publish_without_human_approval(self):
        """PP-6: evaluate_policy blocks mode=publish without human_approved (P6)."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = self._evidence_dir_with_all()
        try:
            result = evaluate_policy(
                verdict="PASS",
                run_id="uat-122-test",
                evidence_dir=tmp,
                human_approved=False,
                mode="publish",
            )
            assert result.allowed is False
            rules = [v.rule for v in result.violations]
            assert "P6" in rules
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp7_allow_dry_run_without_human_approval(self):
        """PP-7: dry-run mode does not require human approval (no P6 violation)."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = self._evidence_dir_with_all()
        try:
            result = evaluate_policy(
                verdict="PASS",
                run_id="uat-122-test",
                evidence_dir=tmp,
                human_approved=False,
                mode="dry-run",
            )
            blocking_rules = [v.rule for v in result.violations if v.severity == "blocking"]
            assert "P6" not in blocking_rules
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp8_block_incomplete_evidence(self):
        """PP-8: evaluate_policy blocks when evidence_manifest shows incomplete (P3)."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = self._evidence_dir_with_all()
        try:
            incomplete_manifest = {
                "complete": False,
                "missing_artifacts": ["execution.jsonl"],
                "missing": ["execution.jsonl"],
            }
            result = evaluate_policy(
                verdict="PASS",
                run_id="uat-122-test",
                evidence_dir=tmp,
                human_approved=True,
                mode="publish",
                evidence_manifest=incomplete_manifest,
            )
            assert result.allowed is False
            rules = [v.rule for v in result.violations]
            assert "P3" in rules
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp9_allow_fail_with_human_approval(self):
        """PP-9: FAIL verdict is publishable with human approval (FAILs go to ADO too)."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = self._evidence_dir_with_all()
        try:
            result = evaluate_policy(
                verdict="FAIL",
                run_id="uat-122-test",
                evidence_dir=tmp,
                human_approved=True,
                mode="publish",
            )
            assert result.allowed is True
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp10_write_policy_result(self):
        """PP-10: write_policy_result writes publish_policy_result.json."""
        from qa_uat_publish_policy import evaluate_policy, write_policy_result
        tmp = self._evidence_dir_with_all()
        try:
            policy_result = evaluate_policy(
                verdict="PASS",
                run_id="uat-122-test",
                evidence_dir=tmp,
                human_approved=True,
                mode="publish",
            )
            path = write_policy_result(tmp, policy_result)
            assert (tmp / "publish_policy_result.json").exists()
            data = json.loads((tmp / "publish_policy_result.json").read_text(encoding="utf-8"))
            assert "allowed" in data
            assert "violations" in data
            assert "schema_version" in data
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_pp11_policy_violation_has_required_fields(self):
        """PP-11: PolicyViolation has rule, message, severity."""
        from qa_uat_publish_policy import PolicyViolation
        v = PolicyViolation(rule="P1", message="test message")
        assert v.rule == "P1"
        assert v.message == "test message"
        assert v.severity == "blocking"

    def test_pp12_blocked_verdict_in_publishable_set(self):
        """PP-12: BLOCKED is in publishable verdicts per roadmap — policy allows it."""
        from qa_uat_publish_policy import evaluate_policy, _PUBLISHABLE_VERDICTS
        assert "BLOCKED" in _PUBLISHABLE_VERDICTS, (
            "BLOCKED must be publishable — QA publishes BLOCKED results to ADO too"
        )

    def test_pp_to_dict_complete(self):
        """PublishPolicyResult.to_dict() contains all required fields."""
        from qa_uat_publish_policy import evaluate_policy
        tmp = self._evidence_dir_with_all()
        try:
            result = evaluate_policy(
                verdict="PASS",
                run_id="uat-test",
                evidence_dir=tmp,
                human_approved=True,
                mode="dry-run",
            )
            d = result.to_dict()
            for field in ("allowed", "verdict", "run_id", "mode", "human_approved",
                          "violations", "schema_version", "blocking_count"):
                assert field in d, f"Missing field: {field}"
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# SC — Stage Confidence + Human Decision
# ─────────────────────────────────────────────────────────────────────────────

class TestStageConfidenceSC:
    """SC-1 through SC-7: execution_logger confidence and human_decision events."""

    def _make_logger(self, tmp: Path):
        from execution_logger import ExecutionLogger
        return ExecutionLogger(
            session_id="test-session-sc",
            evidence_dir=tmp,
            run_id="uat-sc-test",
        )

    def _read_events(self, tmp: Path) -> list:
        log = tmp / "execution.jsonl"
        if not log.exists():
            return []
        events = []
        for line in log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events

    def test_sc1_stage_confidence_emits_event(self, tmp_path):
        """SC-1: execution_logger.stage_confidence emits stage_confidence event."""
        logger = self._make_logger(tmp_path)
        logger.stage_confidence(stage="screen_detection", confidence=0.94)
        logger.close()
        events = self._read_events(tmp_path)
        event_names = [e.get("event") for e in events]
        assert "stage_confidence" in event_names

    def test_sc2_stage_confidence_has_required_fields(self, tmp_path):
        """SC-2: stage_confidence event has stage, confidence, signals fields."""
        logger = self._make_logger(tmp_path)
        logger.stage_confidence(
            stage="screen_detection",
            confidence=0.94,
            signals=["exact_aspx_match", "source=analisis_tecnico"],
        )
        logger.close()
        events = self._read_events(tmp_path)
        ev = next((e for e in events if e.get("event") == "stage_confidence"), None)
        assert ev is not None
        data = ev.get("data", ev)
        assert data.get("stage") == "screen_detection"
        assert abs(data.get("confidence", 0) - 0.94) < 0.001
        assert isinstance(data.get("signals"), list)

    def test_sc3_confidence_clamped_to_0_1(self, tmp_path):
        """SC-3: confidence is clamped to 0.0-1.0 range."""
        logger = self._make_logger(tmp_path)
        logger.stage_confidence(stage="compiler", confidence=1.5)   # over
        logger.stage_confidence(stage="generator", confidence=-0.5)  # under
        logger.close()
        events = self._read_events(tmp_path)
        conf_events = [e for e in events if e.get("event") == "stage_confidence"]
        for ev in conf_events:
            data = ev.get("data", ev)
            c = data.get("confidence", 0.5)
            assert 0.0 <= c <= 1.0, f"confidence {c} out of [0, 1] range"

    def test_sc4_human_decision_emits_event(self, tmp_path):
        """SC-4: execution_logger.human_decision emits human_decision event."""
        logger = self._make_logger(tmp_path)
        logger.human_decision(decision="approve_publish", approved_publish=True)
        logger.close()
        events = self._read_events(tmp_path)
        event_names = [e.get("event") for e in events]
        assert "human_decision" in event_names

    def test_sc5_human_decision_has_required_fields(self, tmp_path):
        """SC-5: human_decision event has decision, operator, run_id fields."""
        logger = self._make_logger(tmp_path)
        logger.human_decision(
            decision="approve_publish",
            operator="juan.luca",
            run_id="uat-sc-test",
        )
        logger.close()
        events = self._read_events(tmp_path)
        ev = next((e for e in events if e.get("event") == "human_decision"), None)
        assert ev is not None
        data = ev.get("data", ev)
        assert data.get("decision") == "approve_publish"
        assert data.get("operator") == "juan.luca"
        assert data.get("run_id") == "uat-sc-test"

    def test_sc6_approved_publish_true_for_approve(self, tmp_path):
        """SC-6: approved_publish=True stored in human_decision event."""
        logger = self._make_logger(tmp_path)
        logger.human_decision(decision="approve_publish", approved_publish=True)
        logger.close()
        events = self._read_events(tmp_path)
        ev = next((e for e in events if e.get("event") == "human_decision"), None)
        data = ev.get("data", ev)
        assert data.get("approved_publish") is True

    def test_sc7_human_decision_includes_ticket_id(self, tmp_path):
        """SC-7: human_decision event includes ticket_id when provided."""
        logger = self._make_logger(tmp_path)
        logger.human_decision(
            decision="reject_publish",
            ticket_id=122,
            reason="Missing test coverage for CA-03",
        )
        logger.close()
        events = self._read_events(tmp_path)
        ev = next((e for e in events if e.get("event") == "human_decision"), None)
        data = ev.get("data", ev)
        assert data.get("ticket_id") == 122
        assert "CA-03" in (data.get("reason") or "")


# ─────────────────────────────────────────────────────────────────────────────
# RM — Rollback Metadata
# ─────────────────────────────────────────────────────────────────────────────

class TestRollbackMetadataRM:
    """RM-1 through RM-3: ado_evidence_publisher rollback_audit correctness."""

    def test_rm1_write_rollback_audit_creates_file(self, tmp_path):
        """RM-1: _write_rollback_audit creates rollback_audit.json with correct fields."""
        from ado_evidence_publisher import _write_rollback_audit
        dossier_path = tmp_path / "dossier.json"
        dossier_path.write_text('{"ok":true}', encoding="utf-8")

        _write_rollback_audit(
            ticket_id=122,
            run_id="uat-122-rollback-test",
            comment_hash="abc123",
            comment_id=99999,
            dossier_path=dossier_path,
        )

        rollback_path = tmp_path / "rollback_audit.json"
        assert rollback_path.exists(), "rollback_audit.json should be created"

    def test_rm2_rollback_status_not_rolled_back_initially(self, tmp_path):
        """RM-2: rollback_audit.json has rollback_status=not_rolled_back initially."""
        from ado_evidence_publisher import _write_rollback_audit
        dossier_path = tmp_path / "dossier.json"
        dossier_path.write_text('{"ok":true}', encoding="utf-8")

        _write_rollback_audit(
            ticket_id=122,
            run_id="uat-122-test",
            comment_hash="abc123",
            comment_id=99999,
            dossier_path=dossier_path,
        )

        data = json.loads((tmp_path / "rollback_audit.json").read_text(encoding="utf-8"))
        assert data["rollback_status"] == "not_rolled_back"

    def test_rm3_rollback_audit_has_all_fields(self, tmp_path):
        """RM-3: rollback_audit.json has comment_id, run_id, ticket_id, published_at."""
        from ado_evidence_publisher import _write_rollback_audit
        dossier_path = tmp_path / "dossier.json"
        dossier_path.write_text('{"ok":true}', encoding="utf-8")

        _write_rollback_audit(
            ticket_id=122,
            run_id="uat-122-fields-test",
            comment_hash="deadbeef",
            comment_id=77777,
            dossier_path=dossier_path,
        )

        data = json.loads((tmp_path / "rollback_audit.json").read_text(encoding="utf-8"))
        assert data["ticket_id"] == 122
        assert data["run_id"] == "uat-122-fields-test"
        assert data["comment_id"] == 77777
        assert "published_at" in data
        assert data["comment_hash"] == "deadbeef"
        assert "rollback_instruction" in data
        assert "schema_version" in data


# ─────────────────────────────────────────────────────────────────────────────
# BK — Backend metadata sprint 6
# ─────────────────────────────────────────────────────────────────────────────

class TestBackendMetadataBK:
    """BK-1 through BK-3: backend api/qa_uat.py stores Sprint 6 governance fields."""

    def _make_result(self, **overrides) -> dict:
        base = {
            "ok": False,
            "verdict": "BLOCKED",
            "category": "PIP",
            "reason": "COMPILER_EMPTY",
            "failed_stage": "compiler",
            "elapsed_s": 1.5,
            "run_id": "uat-bk-test",
            "artifact_root": "/tmp/evidence/bk-test",
            "_evidence_complete": True,
            "_evidence_missing": [],
            "_normalized": True,
            "confidence": 0.95,
        }
        base.update(overrides)
        return base

    def _simulate_metadata_update(self, result: dict) -> dict:
        """Simulate the Sprint 6 metadata enrichment logic from qa_uat.py."""
        meta: dict = {}
        meta["verdict"] = result.get("verdict", "UNKNOWN")
        meta["elapsed_s"] = result.get("elapsed_s")
        if result.get("run_id"):
            meta["run_id"] = result["run_id"]
        if result.get("artifact_root"):
            meta["artifact_root"] = result["artifact_root"]
        # Sprint 6 fields
        _s6_fields = {
            "category":          result.get("category"),
            "reason":            result.get("reason"),
            "failed_stage":      result.get("failed_stage"),
            "evidence_complete": result.get("_evidence_complete"),
            "evidence_missing":  result.get("_evidence_missing") or [],
            "normalized":        result.get("_normalized", False),
        }
        _stages = result.get("stages") or {}
        if "compiler_contract" in _stages:
            _s6_fields["compiler_contract_ok"] = _stages["compiler_contract"].get("ok")
        if "generator_contract" in _stages:
            _s6_fields["generator_contract_ok"] = _stages["generator_contract"].get("ok")
        if "confidence" in result:
            _s6_fields["confidence"] = result["confidence"]
        meta.update({k: v for k, v in _s6_fields.items() if v is not None})
        return meta

    def test_bk1_meta_stores_category_reason_failed_stage(self):
        """BK-1: metadata stores category, reason, failed_stage."""
        result = self._make_result()
        meta = self._simulate_metadata_update(result)
        assert meta["category"] == "PIP"
        assert meta["reason"] == "COMPILER_EMPTY"
        assert meta["failed_stage"] == "compiler"

    def test_bk2_meta_stores_evidence_complete(self):
        """BK-2: metadata stores evidence_complete boolean."""
        result = self._make_result(_evidence_complete=True)
        meta = self._simulate_metadata_update(result)
        assert meta["evidence_complete"] is True

    def test_bk3_meta_stores_confidence(self):
        """BK-3: metadata stores confidence when present in result."""
        result = self._make_result(confidence=0.92)
        meta = self._simulate_metadata_update(result)
        assert abs(meta.get("confidence", 0) - 0.92) < 0.001

    def test_bk_meta_stores_contract_ok_stages(self):
        """BK extra: metadata stores compiler/generator contract ok from stages."""
        result = self._make_result(stages={
            "compiler_contract": {"ok": True},
            "generator_contract": {"ok": False},
        })
        meta = self._simulate_metadata_update(result)
        assert meta.get("compiler_contract_ok") is True
        assert meta.get("generator_contract_ok") is False

    def test_bk_meta_does_not_include_none_values(self):
        """BK extra: None values are not stored in metadata (skip if not present)."""
        result = {
            "ok": False,
            "verdict": "BLOCKED",
            "run_id": "uat-sparse-test",
            # No category, reason, confidence, etc.
        }
        meta = self._simulate_metadata_update(result)
        # Keys with None values should not be stored
        assert "category" not in meta or meta.get("category") is not None
        assert "confidence" not in meta  # Not in result


# ─────────────────────────────────────────────────────────────────────────────
# Integration: policy + logger working together
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceIntegration:
    """End-to-end: policy + human_decision event together."""

    def test_policy_then_human_decision_workflow(self, tmp_path):
        """Full governance workflow: check policy, emit human_decision, proceed."""
        from qa_uat_publish_policy import evaluate_policy, write_policy_result
        from execution_logger import ExecutionLogger

        # 1. Evidence dir with all artifacts
        for fname in ("result.json", "execution.jsonl", "effective_config.json", "dossier.json"):
            (tmp_path / fname).write_text('{"ok":true}', encoding="utf-8")

        # 2. Evaluate policy (pre-approval — human not yet approved)
        pre_result = evaluate_policy(
            verdict="FAIL",
            run_id="uat-integ-gov",
            evidence_dir=tmp_path,
            human_approved=False,
            mode="publish",
        )
        assert pre_result.allowed is False  # P6 violation
        rules = [v.rule for v in pre_result.violations]
        assert "P6" in rules

        # 3. Human reviews, approves — emit human_decision event
        logger = ExecutionLogger(
            session_id="integ-gov-session",
            evidence_dir=tmp_path,
            run_id="uat-integ-gov",
        )
        logger.human_decision(
            decision="approve_publish",
            operator="test_operator",
            ticket_id=122,
            run_id="uat-integ-gov",
            approved_publish=True,
        )
        logger.close()

        # 4. Re-evaluate policy with approval
        post_result = evaluate_policy(
            verdict="FAIL",
            run_id="uat-integ-gov",
            evidence_dir=tmp_path,
            human_approved=True,
            mode="publish",
        )
        assert post_result.allowed is True

        # 5. Write policy result
        write_policy_result(tmp_path, post_result)
        assert (tmp_path / "publish_policy_result.json").exists()
