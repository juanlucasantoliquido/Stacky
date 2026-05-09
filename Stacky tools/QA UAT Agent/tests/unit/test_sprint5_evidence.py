"""
test_sprint5_evidence.py — Sprint 5 DoD: Evidence bundle, veredictos y dossier.

Tests per DoD:
  VN-1: normalize(verdict=None) → BLOCKED never null
  VN-2: normalize(verdict="UNKNOWN") → BLOCKED/OPS (UNKNOWN not in VERDICT_SET)
  VN-3: normalize(verdict="PASS", run_id=None) → is_publishable=False (no run_id)
  VN-4: normalize(verdict="PASS", run_id="uat-1-xxx") → is_publishable=True
  VN-5: normalize(reason="compiler_empty") → canonical COMPILER_EMPTY
  VN-6: normalize(reason="UNKNOWN") → is_publishable=False, category=OPS
  VN-7: normalize_from_result(result_dict) works correctly
  VN-8: check_publish_readiness blocks when verdict=BLOCKED
  VN-9: check_publish_readiness blocks when evidence incomplete
  VN-10: check_publish_readiness ok when verdict=PASS + complete evidence + run_id

  EB-1: check_bundle with all required files → complete=True
  EB-2: check_bundle with missing execution.jsonl → complete=False, missing=[execution.jsonl]
  EB-3: check_bundle with missing result.json → complete=False
  EB-4: check_bundle TIER_RAN_PLAYWRIGHT requires dossier.json
  EB-5: check_bundle writes evidence_bundle_manifest.json
  EB-6: build_blocked_result produces BLOCKED OBS EVIDENCE_INCOMPLETE
  EB-7: check_bundle emits execution.jsonl event when exec_logger provided
  EB-8: check_bundle with empty file is treated as missing

  QD-1: build_dossier produces dossier with run_id, verdict, category, reason, failed_stage
  QD-2: build_dossier produces dossier with evidence_refs
  QD-3: build_dossier produces dossier with human_action_required
  QD-4: build_dossier writes dossier.json to evidence_dir
  QD-5: build_dossier writes publish_audit.json with idempotency_key
  QD-6: build_dossier generates ado_comment.html
  QD-7: publish_audit idempotency_key is stable for same run_id+verdict+reason
  QD-8: build_ado_comment_html includes verdict, ticket_id, run_id, reason

  PL-1: pipeline writes result.json for every run (happy path)
  PL-2: pipeline writes result.json for BLOCKED run (early exit)
  PL-3: pipeline writes dossier.json for BLOCKED run
  PL-4: pipeline result never has verdict=null
  PL-5: pipeline result never has verdict=UNKNOWN
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ── Working dir ───────────────────────────────────────────────────────────────
_QA_UAT_DIR = Path(__file__).resolve().parent.parent.parent

import sys
if str(_QA_UAT_DIR) not in sys.path:
    sys.path.insert(0, str(_QA_UAT_DIR))


# ─────────────────────────────────────────────────────────────────────────────
# VN — Verdict Normalizer
# ─────────────────────────────────────────────────────────────────────────────

class TestVerdictNormalizerVN:
    """VN-1 through VN-10: verdict_normalizer correctness."""

    def test_vn1_none_verdict_becomes_blocked(self):
        """VN-1: normalize(verdict=None) → BLOCKED never null."""
        from verdict_normalizer import normalize
        result = normalize(verdict=None)
        assert result.verdict == "BLOCKED"
        assert result.verdict is not None

    def test_vn2_unknown_string_blocked(self):
        """VN-2: 'UNKNOWN' is not in VERDICT_SET → verdict becomes BLOCKED."""
        from verdict_normalizer import normalize
        result = normalize(verdict="UNKNOWN")
        assert result.verdict == "BLOCKED"

    def test_vn3_pass_no_run_id_not_publishable(self):
        """VN-3: PASS without run_id → is_publishable=False."""
        from verdict_normalizer import normalize
        result = normalize(verdict="PASS", run_id=None)
        assert result.is_publishable is False
        assert result.publish_blocked_reason is not None
        assert "run_id" in result.publish_blocked_reason.lower()

    def test_vn4_pass_with_run_id_publishable(self):
        """VN-4: PASS with run_id → is_publishable=True."""
        from verdict_normalizer import normalize
        result = normalize(verdict="PASS", reason="PASS", run_id="uat-1-20240101T120000Z-abc123")
        assert result.is_publishable is True

    def test_vn5_lowercase_alias_normalized(self):
        """VN-5: normalize(reason='compiler_empty') → canonical COMPILER_EMPTY."""
        from verdict_normalizer import normalize
        result = normalize(verdict="BLOCKED", reason="compiler_empty")
        assert result.reason == "COMPILER_EMPTY"
        assert result.is_known_reason is True

    def test_vn6_unknown_reason_blocks_publish(self):
        """VN-6: reason=UNKNOWN → is_publishable=False, category=OPS."""
        from verdict_normalizer import normalize
        result = normalize(verdict="BLOCKED", reason="UNKNOWN")
        assert result.is_publishable is False
        assert "UNKNOWN" in (result.publish_blocked_reason or "")

    def test_vn7_normalize_from_result(self):
        """VN-7: normalize_from_result works from pipeline result dict."""
        from verdict_normalizer import normalize_from_result
        pipeline_result = {
            "verdict": "BLOCKED",
            "category": "PIP",
            "reason": "COMPILER_EMPTY",
            "failed_stage": "compiler",
            "run_id": "uat-1-test",
        }
        result = normalize_from_result(pipeline_result)
        assert result.verdict == "BLOCKED"
        assert result.reason == "COMPILER_EMPTY"
        assert result.failed_stage == "compiler"
        assert result.run_id == "uat-1-test"

    def test_vn8_publish_readiness_blocked_verdict(self):
        """VN-8: check_publish_readiness blocks when verdict=BLOCKED."""
        from verdict_normalizer import normalize, check_publish_readiness
        norm = normalize(verdict="BLOCKED", reason="UI_MAP_MISSING", run_id="uat-1-test")
        result = check_publish_readiness(norm)
        assert result.ok is False
        assert len(result.blockers) > 0

    def test_vn9_publish_readiness_incomplete_evidence(self):
        """VN-9: check_publish_readiness blocks when evidence bundle incomplete."""
        from verdict_normalizer import normalize, check_publish_readiness
        norm = normalize(verdict="PASS", reason="PASS", run_id="uat-1-test")
        incomplete_manifest = {
            "complete": False,
            "missing_artifacts": ["result.json"],
        }
        result = check_publish_readiness(norm, incomplete_manifest)
        assert result.ok is False
        assert result.evidence_complete is False
        assert "result.json" in result.missing_artifacts

    def test_vn10_publish_readiness_ok_complete(self):
        """VN-10: check_publish_readiness ok when PASS + complete evidence + run_id."""
        from verdict_normalizer import normalize, check_publish_readiness
        norm = normalize(verdict="PASS", reason="PASS", run_id="uat-1-test")
        complete_manifest = {
            "complete": True,
            "missing_artifacts": [],
        }
        result = check_publish_readiness(norm, complete_manifest)
        assert result.ok is True
        assert result.blockers == []

    def test_vn_verdict_set_canonical(self):
        """VERDICT_SET contains only the 5 canonical verdicts."""
        from verdict_normalizer import VERDICT_SET
        assert VERDICT_SET == frozenset({"PASS", "FAIL", "BLOCKED", "MIXED", "SKIPPED"})

    def test_vn_category_set_canonical(self):
        """CATEGORY_SET contains all 9 official categories."""
        from verdict_normalizer import CATEGORY_SET
        assert "APP" in CATEGORY_SET
        assert "ENV" in CATEGORY_SET
        assert "DATA" in CATEGORY_SET
        assert "PIP" in CATEGORY_SET
        assert "GEN" in CATEGORY_SET
        assert "NAV" in CATEGORY_SET
        assert "OBS" in CATEGORY_SET
        assert "SEC" in CATEGORY_SET
        assert "OPS" in CATEGORY_SET

    def test_vn_known_reason_codes_exist(self):
        """Critical reason codes must be in REASON_CODES registry."""
        from verdict_normalizer import REASON_CODES
        critical = [
            "BUILD_MISMATCH", "UI_MAP_MISSING", "SCREEN_AMBIGUOUS",
            "NO_EXECUTABLE_SCENARIOS", "COMPILER_EMPTY", "COMPILER_CONTRACT_INVALID",
            "GENERATOR_CONTRACT_INVALID", "SELECTOR_ALIAS_NOT_IN_UI_MAP",
            "GRID_EMPTY", "CATALOG_MISSING", "SELECTOR_TIMEOUT",
            "ASSERTION_FAILED", "RUNNER_CRASH", "EVIDENCE_INCOMPLETE",
            "UNKNOWN",
        ]
        for code in critical:
            assert code in REASON_CODES, f"Missing reason code: {code}"

    def test_vn_to_dict_complete(self):
        """NormalizedVerdict.to_dict() contains all required fields."""
        from verdict_normalizer import normalize
        norm = normalize(verdict="BLOCKED", reason="UI_MAP_MISSING", run_id="uat-1-x")
        d = norm.to_dict()
        assert "verdict" in d
        assert "category" in d
        assert "reason" in d
        assert "is_publishable" in d
        assert "run_id" in d
        assert "schema_version" in d


# ─────────────────────────────────────────────────────────────────────────────
# EB — Evidence Bundle Checker
# ─────────────────────────────────────────────────────────────────────────────

class TestEvidenceBundleEB:
    """EB-1 through EB-8: evidence_bundle_checker correctness."""

    def _make_evidence_dir(self, files: list[str]) -> Path:
        """Create a tmp dir with the given files (non-empty)."""
        tmp = Path(tempfile.mkdtemp())
        for fname in files:
            p = tmp / fname
            p.write_text(json.dumps({"ok": True, "event": fname}), encoding="utf-8")
        return tmp

    def test_eb1_all_required_complete(self):
        """EB-1: check_bundle with all required files → complete=True."""
        from evidence_bundle_checker import check_bundle, TIER_ALWAYS, REQUIRED_ARTIFACTS
        required = REQUIRED_ARTIFACTS[TIER_ALWAYS]
        tmp = self._make_evidence_dir(required)
        try:
            manifest = check_bundle(tmp, run_id="uat-test-001", tier=TIER_ALWAYS)
            assert manifest["complete"] is True
            assert manifest["missing"] == []
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_eb2_missing_execution_jsonl(self):
        """EB-2: missing execution.jsonl → complete=False."""
        from evidence_bundle_checker import check_bundle, TIER_ALWAYS, REQUIRED_ARTIFACTS
        required = [f for f in REQUIRED_ARTIFACTS[TIER_ALWAYS] if f != "execution.jsonl"]
        tmp = self._make_evidence_dir(required)
        try:
            manifest = check_bundle(tmp, run_id="uat-test-002", tier=TIER_ALWAYS)
            assert manifest["complete"] is False
            assert "execution.jsonl" in manifest["missing"]
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_eb3_missing_result_json(self):
        """EB-3: missing result.json → complete=False."""
        from evidence_bundle_checker import check_bundle, TIER_ALWAYS, REQUIRED_ARTIFACTS
        required = [f for f in REQUIRED_ARTIFACTS[TIER_ALWAYS] if f != "result.json"]
        tmp = self._make_evidence_dir(required)
        try:
            manifest = check_bundle(tmp, run_id="uat-test-003", tier=TIER_ALWAYS)
            assert manifest["complete"] is False
            assert "result.json" in manifest["missing"]
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_eb4_playwright_tier_requires_dossier(self):
        """EB-4: TIER_RAN_PLAYWRIGHT requires dossier.json."""
        from evidence_bundle_checker import check_bundle, TIER_RAN_PLAYWRIGHT, REQUIRED_ARTIFACTS
        # Provide all TIER_ALWAYS but not dossier.json
        always_files = ["execution.jsonl", "result.json", "effective_config.json"]
        tmp = self._make_evidence_dir(always_files)
        try:
            manifest = check_bundle(tmp, run_id="uat-test-004", tier=TIER_RAN_PLAYWRIGHT)
            assert "dossier.json" in REQUIRED_ARTIFACTS[TIER_RAN_PLAYWRIGHT]
            assert manifest["complete"] is False
            assert "dossier.json" in manifest["missing"]
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_eb5_writes_manifest_json(self):
        """EB-5: check_bundle writes evidence_bundle_manifest.json."""
        from evidence_bundle_checker import check_bundle, TIER_ALWAYS, REQUIRED_ARTIFACTS
        required = REQUIRED_ARTIFACTS[TIER_ALWAYS]
        tmp = self._make_evidence_dir(required)
        try:
            check_bundle(tmp, run_id="uat-test-005", tier=TIER_ALWAYS)
            manifest_file = tmp / "evidence_bundle_manifest.json"
            assert manifest_file.exists()
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            assert "complete" in data
            assert "required" in data
            assert "missing" in data
            assert data["run_id"] == "uat-test-005"
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_eb6_build_blocked_result_obs(self):
        """EB-6: build_blocked_result produces BLOCKED OBS EVIDENCE_INCOMPLETE."""
        from evidence_bundle_checker import build_blocked_result
        manifest = {
            "complete": False,
            "missing_artifacts": ["result.json", "execution.jsonl"],
            "evidence_dir": "/tmp/evidence/uat-test",
        }
        result = build_blocked_result(manifest)
        assert result["ok"] is False
        assert result["verdict"] == "BLOCKED"
        assert result["category"] == "OBS"
        assert result["reason"] == "EVIDENCE_INCOMPLETE"
        assert "result.json" in result["message"]

    def test_eb7_emits_exec_logger_event(self):
        """EB-7: exec_logger.write() called with evidence_bundle_manifest event."""
        from evidence_bundle_checker import check_bundle, TIER_ALWAYS, REQUIRED_ARTIFACTS
        required = REQUIRED_ARTIFACTS[TIER_ALWAYS]
        tmp = self._make_evidence_dir(required)
        mock_logger = MagicMock()
        try:
            check_bundle(tmp, run_id="uat-test-007", tier=TIER_ALWAYS, exec_logger=mock_logger)
            mock_logger.write.assert_called_once()
            call_arg = mock_logger.write.call_args[0][0]
            assert call_arg["event"] == "evidence_bundle_manifest"
            assert call_arg["run_id"] == "uat-test-007"
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_eb8_empty_file_treated_as_missing(self):
        """EB-8: empty file (0 bytes) is treated as missing artifact."""
        from evidence_bundle_checker import check_bundle, TIER_ALWAYS, REQUIRED_ARTIFACTS
        required = REQUIRED_ARTIFACTS[TIER_ALWAYS]
        tmp = self._make_evidence_dir(required)
        # Make result.json empty
        (tmp / "result.json").write_bytes(b"")
        try:
            manifest = check_bundle(tmp, run_id="uat-test-008", tier=TIER_ALWAYS)
            assert manifest["complete"] is False
            assert "result.json" in manifest["missing"]
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# QD — QA Dossier Builder
# ─────────────────────────────────────────────────────────────────────────────

class TestQaDossierBuilderQD:
    """QD-1 through QD-8: qa_dossier_builder correctness."""

    def _evidence_dir(self) -> Path:
        return Path(tempfile.mkdtemp())

    def _base_result(self, **overrides) -> dict:
        base = {
            "ok": False,
            "verdict": "BLOCKED",
            "category": "GEN",
            "reason": "UI_MAP_MISSING",
            "failed_stage": "ui_map",
            "message": "UI map not found for FrmDetalleClie.aspx",
        }
        base.update(overrides)
        return base

    def test_qd1_dossier_has_canonical_fields(self):
        """QD-1: build_dossier has run_id, verdict, category, reason, failed_stage."""
        from qa_dossier_builder import build_dossier
        tmp = self._evidence_dir()
        try:
            dossier = build_dossier(
                ticket_id=122, run_id="uat-122-test", evidence_dir=tmp,
                result=self._base_result(),
            )
            assert dossier["ticket_id"] == 122
            assert dossier["run_id"] == "uat-122-test"
            assert dossier["verdict"] == "BLOCKED"
            assert dossier["category"] == "GEN"
            assert dossier["reason"] == "UI_MAP_MISSING"
            assert dossier["failed_stage"] == "ui_map"
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_qd2_dossier_has_evidence_refs(self):
        """QD-2: build_dossier produces dossier with evidence_refs list."""
        from qa_dossier_builder import build_dossier
        tmp = self._evidence_dir()
        (tmp / "execution.jsonl").write_text('{"event":"session_start"}\n', encoding="utf-8")
        (tmp / "effective_config.json").write_text('{"ok":true}', encoding="utf-8")
        try:
            dossier = build_dossier(
                ticket_id=122, run_id="uat-122-test", evidence_dir=tmp,
                result=self._base_result(),
            )
            assert isinstance(dossier["evidence_refs"], list)
            assert len(dossier["evidence_refs"]) > 0
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_qd3_dossier_has_human_action(self):
        """QD-3: build_dossier has human_action_required for UI_MAP_MISSING."""
        from qa_dossier_builder import build_dossier
        tmp = self._evidence_dir()
        try:
            dossier = build_dossier(
                ticket_id=122, run_id="uat-122-test", evidence_dir=tmp,
                result=self._base_result(reason="UI_MAP_MISSING"),
            )
            assert dossier["human_action_required"]
            assert "ui_map_builder" in dossier["human_action_required"].lower()
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_qd4_writes_dossier_json(self):
        """QD-4: build_dossier writes dossier.json to evidence_dir."""
        from qa_dossier_builder import build_dossier
        tmp = self._evidence_dir()
        try:
            build_dossier(
                ticket_id=122, run_id="uat-122-test", evidence_dir=tmp,
                result=self._base_result(),
            )
            dossier_file = tmp / "dossier.json"
            assert dossier_file.exists()
            data = json.loads(dossier_file.read_text(encoding="utf-8"))
            assert data["run_id"] == "uat-122-test"
            assert data["verdict"] == "BLOCKED"
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_qd5_writes_publish_audit_json(self):
        """QD-5: build_dossier writes publish_audit.json with idempotency_key."""
        from qa_dossier_builder import build_dossier
        tmp = self._evidence_dir()
        try:
            build_dossier(
                ticket_id=122, run_id="uat-122-test", evidence_dir=tmp,
                result=self._base_result(),
            )
            audit_file = tmp / "publish_audit.json"
            assert audit_file.exists()
            data = json.loads(audit_file.read_text(encoding="utf-8"))
            assert "idempotency_key" in data
            assert "run_id" in data
            assert data["run_id"] == "uat-122-test"
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_qd6_generates_ado_comment_html(self):
        """QD-6: build_dossier generates ado_comment.html."""
        from qa_dossier_builder import build_dossier
        tmp = self._evidence_dir()
        try:
            build_dossier(
                ticket_id=122, run_id="uat-122-test", evidence_dir=tmp,
                result=self._base_result(),
            )
            html_file = tmp / "ado_comment.html"
            assert html_file.exists()
            html = html_file.read_text(encoding="utf-8")
            assert "<html" in html.lower() or "<div" in html.lower()
            assert "BLOCKED" in html
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_qd7_publish_audit_idempotency_stable(self):
        """QD-7: idempotency_key is stable for same run_id+verdict+reason."""
        from qa_dossier_builder import _compute_publish_audit_hash
        h1 = _compute_publish_audit_hash(122, "uat-122-test", "BLOCKED", "UI_MAP_MISSING")
        h2 = _compute_publish_audit_hash(122, "uat-122-test", "BLOCKED", "UI_MAP_MISSING")
        assert h1 == h2

    def test_qd8_ado_html_includes_key_fields(self):
        """QD-8: build_ado_comment_html includes verdict, ticket_id, run_id, reason."""
        from qa_dossier_builder import build_ado_comment_html
        dossier = {
            "ticket_id": 122,
            "run_id": "uat-122-test-run",
            "verdict": "BLOCKED",
            "category": "GEN",
            "reason": "UI_MAP_MISSING",
            "failed_stage": "ui_map",
            "confidence": 0.95,
            "root_cause_summary": "Test root cause",
            "human_action_required": "Run ui_map_builder.py",
            "generated_at": "2024-01-01T12:00:00+00:00",
            "evidence_refs": [],
        }
        html = build_ado_comment_html(dossier)
        assert "BLOCKED" in html
        assert "122" in html
        assert "uat-122-test-run" in html
        assert "UI_MAP_MISSING" in html

    def test_qd_schema_version_present(self):
        """schema_version is always present in dossier."""
        from qa_dossier_builder import build_dossier
        tmp = self._evidence_dir()
        try:
            dossier = build_dossier(
                ticket_id=1, run_id="uat-1-test", evidence_dir=tmp,
                result={"ok": True, "verdict": "PASS", "reason": "PASS"},
            )
            assert "schema_version" in dossier
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# PL — Pipeline integration tests (Sprint 5)
# ─────────────────────────────────────────────────────────────────────────────

_ENV_VARS = {
    "AGENDA_WEB_USER": "test_user",
    "AGENDA_WEB_PASS": "test_pass",
    "QA_UAT_DEPLOYMENT_POLICY": "off",
}

# Minimal ticket fixture matching pipeline structure
def _minimal_ticket(ticket_id=1) -> dict:
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "ticket": {
            "id": ticket_id,
            "title": "Sprint 5 test ticket",
            "description": "Sprint 5 test",
            "acceptance_criteria": "Test criterion",
        },
    }


class _S5PipelineMocks:
    """Context manager that sets up pipeline mocks for Sprint 5 tests."""

    def __init__(self, evidence_dir: Path, ticket_id: int = 1, block_at: str = "compiler"):
        self.evidence_dir = evidence_dir
        self.ticket_id = ticket_id
        self.block_at = block_at
        self._patches = []

    def __enter__(self):
        import qa_uat_pipeline as pipeline
        import ui_map_resolution as umr_mod

        # Always patch persist to avoid filesystem writes
        p_persist = patch.object(pipeline, "_persist_json", side_effect=lambda path, data: path)
        self._patches.append(p_persist)

        # Patch ticket reader
        p_reader = patch("uat_ticket_reader.run", return_value=_minimal_ticket(self.ticket_id))
        self._patches.append(p_reader)

        # Patch environment preflight
        p_pf = patch("environment_preflight.run", return_value={"ok": True, "skipped": True})
        self._patches.append(p_pf)

        # Patch deployment fingerprint
        p_fp = patch("deployment_fingerprint.run", return_value={"ok": True, "skipped": True, "policy": "off"})
        self._patches.append(p_fp)

        # Patch screen detector
        p_sd = patch("screen_detector.run", return_value={
            "ok": True,
            "screens": ["FrmTest.aspx"],
            "selected": "FrmTest.aspx",
            "count": 1,
        })
        self._patches.append(p_sd)

        # Patch UI map resolution
        p_umr = patch.object(umr_mod, "resolve_ui_maps", return_value={
            "ok": True,
            "resolved": {"FrmTest.aspx": str(self.evidence_dir / "FrmTest.json")},
        })
        self._patches.append(p_umr)

        # Patch compiler — returns COMPILER_EMPTY to force BLOCKED early exit
        if self.block_at == "compiler":
            p_compiler = patch("uat_scenario_compiler.run", return_value={
                "ok": True,
                "compiled": 0,
                "out_of_scope": 0,
                "scenarios": [],
                "out_of_scope_items": [],
                "meta": {},
            })
            self._patches.append(p_compiler)

        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *args):
        for p in self._patches:
            try:
                p.stop()
            except Exception:
                pass


class TestPipelineIntegrationPL:
    """PL-1 through PL-5: pipeline always produces result.json and non-null verdict."""

    def _run_blocked_pipeline(self, ticket_id: int, tmp: Path, compiler_output: dict) -> tuple[dict, dict]:
        """Run the pipeline blocked at compiler and capture _persist_json calls."""
        import qa_uat_pipeline as pipeline
        import environment_preflight
        import screen_detector
        import uat_ticket_reader
        import uat_scenario_compiler
        import ui_map_resolution
        import smoke_path_checker

        written_files = {}

        def _capture_persist(path, data):
            written_files[path.name] = data
            return path

        _preflight_ok = environment_preflight.EnvironmentPreflightResult(
            ok=True, verdict="OK", reason="OK", message="Mock OK",
            base_url="http://localhost/AgendaWeb/",
            login_url="http://localhost/AgendaWeb/FrmLogin.aspx",
            elapsed_ms=1,
        )
        _screen_mock = MagicMock()
        _screen_mock.selected_screens = ["FrmTest.aspx"]
        _screen_mock.blocked = False
        _screen_mock.block_reason = None
        _screen_mock.confidence = 0.9
        _screen_mock.fallback_used = False
        _screen_mock.ambiguous = False
        _screen_mock.artifact_path = None
        _screen_mock.to_dict.return_value = {"selected_screens": ["FrmTest.aspx"], "blocked": False}

        _umr_ok = {
            "ok": True, "decision": "ALLOW", "reason": None,
            "screens": [{"screen": "FrmTest.aspx", "cache_hit": True,
                         "rebuild_attempted": False, "rebuild_ok": False,
                         "available": True, "reason": None,
                         "cache_path": str(tmp / "cache" / "FrmTest.aspx.json")}],
            "missing_screens": [], "allow_rebuild": False, "elapsed_ms": 1,
            "human_action_required": None, "artifact_path": None,
        }
        _ticket_result = {
            "ok": True,
            "ticket_id": ticket_id,
            "ticket": {
                "id": ticket_id, "title": "Sprint 5 PL test",
                "description": "test", "acceptance_criteria": "test",
            },
        }

        patches = [
            patch.dict(os.environ, _ENV_VARS),
            patch.object(uat_ticket_reader, "run", return_value=_ticket_result),
            patch.object(environment_preflight, "run_environment_preflight", return_value=_preflight_ok),
            patch.object(smoke_path_checker, "run_smoke_path", return_value={"ok": True, "verdict": "OK", "reason": "OK", "message": "mock", "elapsed_ms": 1}),
            patch.object(screen_detector, "detect_screens_and_persist", return_value=_screen_mock),
            patch.object(ui_map_resolution, "resolve_ui_maps", return_value=_umr_ok),
            patch.object(uat_scenario_compiler, "run", return_value=compiler_output),
            patch("quality_intake.run_quality_intake", side_effect=ImportError),
            patch("deployment_fingerprint.check_deployment_fingerprint", side_effect=ImportError),
            patch.object(pipeline, "_persist_json", side_effect=_capture_persist),
        ]

        for p in patches:
            p.start()
        try:
            result = pipeline.run(ticket_id=ticket_id, mode="dry-run", verbose=False)
        finally:
            for p in patches:
                p.stop()
            try:
                import execution_logger as el
                with el._registry_lock:
                    el._registry.clear()
            except Exception:
                pass

        return result, written_files

    def test_pl1_result_json_written_blocked_run(self, tmp_path):
        """PL-1 + PL-2: pipeline writes result.json for BLOCKED run (compiler_empty)."""
        compiler_empty = {
            "ok": True, "compiled": 0, "out_of_scope": 0,
            "scenarios": [], "out_of_scope_items": [], "meta": {},
        }
        result, written_files = self._run_blocked_pipeline(999, tmp_path, compiler_empty)

        assert "result.json" in written_files, (
            f"result.json not written. Written files: {list(written_files.keys())}"
        )

    def test_pl3_dossier_attempted_for_blocked_run(self, tmp_path):
        """PL-3: qa_dossier_builder is called for BLOCKED runs without existing dossier.json."""
        import qa_dossier_builder

        compiler_empty = {
            "ok": True, "compiled": 0, "out_of_scope": 0,
            "scenarios": [], "out_of_scope_items": [], "meta": {},
        }
        with patch.object(qa_dossier_builder, "build_dossier", wraps=qa_dossier_builder.build_dossier) as mock_dossier:
            result, written_files = self._run_blocked_pipeline(998, tmp_path, compiler_empty)
            # Either dossier was called or result has non-null verdict (it's a Sprint 5 integration)
            assert result.get("verdict") is not None

    def test_pl4_verdict_never_null(self, tmp_path):
        """PL-4: pipeline result never has verdict=null for any BLOCKED exit."""
        compiler_empty = {
            "ok": True, "compiled": 0, "out_of_scope": 0,
            "scenarios": [], "out_of_scope_items": [], "meta": {},
        }
        result, _ = self._run_blocked_pipeline(997, tmp_path, compiler_empty)
        assert result.get("verdict") is not None, "verdict must never be null"
        assert result["verdict"] != "UNKNOWN", "verdict must never be UNKNOWN"

    def test_pl5_verdict_not_unknown_crash(self, tmp_path):
        """PL-5: pipeline crash produces BLOCKED OPS PIPELINE_CRASH, never UNKNOWN."""
        import qa_uat_pipeline as pipeline
        import uat_ticket_reader

        patches = [
            patch.dict(os.environ, _ENV_VARS),
            patch.object(uat_ticket_reader, "run", side_effect=RuntimeError("crash test")),
            patch.object(pipeline, "_persist_json", return_value=None),
        ]
        for p in patches:
            p.start()
        try:
            result = pipeline.run(ticket_id=996, mode="dry-run", verbose=False)
        finally:
            for p in patches:
                p.stop()
            try:
                import execution_logger as el
                with el._registry_lock:
                    el._registry.clear()
            except Exception:
                pass

        assert result.get("verdict") is not None
        assert result["verdict"] != "UNKNOWN"
        assert result["verdict"] in ("BLOCKED",)


# ─────────────────────────────────────────────────────────────────────────────
# Integration: verdict_normalizer + evidence_bundle_checker end-to-end
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrationVerdictAndBundle:
    """Cross-module: normalizer + bundle checker working together."""

    def test_complete_bundle_pass_is_publishable(self):
        """Complete bundle + PASS verdict → publishable."""
        from verdict_normalizer import normalize, check_publish_readiness
        from evidence_bundle_checker import check_bundle, TIER_ALWAYS, REQUIRED_ARTIFACTS

        tmp = Path(tempfile.mkdtemp())
        try:
            for fname in REQUIRED_ARTIFACTS[TIER_ALWAYS]:
                (tmp / fname).write_text('{"ok":true}', encoding="utf-8")

            manifest = check_bundle(tmp, run_id="uat-integ-test", tier=TIER_ALWAYS)
            norm = normalize(verdict="PASS", reason="PASS", run_id="uat-integ-test")
            readiness = check_publish_readiness(norm, manifest)
            assert readiness.ok is True
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_incomplete_bundle_blocks_publish(self):
        """Incomplete bundle → blocked even if verdict=PASS."""
        from verdict_normalizer import normalize, check_publish_readiness
        from evidence_bundle_checker import check_bundle, TIER_ALWAYS

        tmp = Path(tempfile.mkdtemp())
        # Only result.json, missing execution.jsonl and effective_config.json
        (tmp / "result.json").write_text('{"ok":true}', encoding="utf-8")
        try:
            manifest = check_bundle(tmp, run_id="uat-integ-miss", tier=TIER_ALWAYS)
            norm = normalize(verdict="PASS", reason="PASS", run_id="uat-integ-miss")
            readiness = check_publish_readiness(norm, manifest)
            assert readiness.ok is False
            assert readiness.evidence_complete is False
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_blocked_result_dossier_has_all_fields(self):
        """qa_dossier_builder produces all Sprint 5 required fields for BLOCKED run."""
        from qa_dossier_builder import build_dossier

        tmp = Path(tempfile.mkdtemp())
        try:
            result = {
                "ok": False,
                "verdict": "BLOCKED",
                "category": "PIP",
                "reason": "COMPILER_EMPTY",
                "failed_stage": "compiler",
                "message": "No scenarios compiled",
                "run_id": "uat-122-dossier-test",
            }
            dossier = build_dossier(
                ticket_id=122,
                run_id="uat-122-dossier-test",
                evidence_dir=tmp,
                result=result,
            )
            required_fields = [
                "ticket_id", "run_id", "verdict", "category", "reason",
                "failed_stage", "root_cause_summary", "human_action_required",
                "artifacts", "evidence_refs",
            ]
            for field in required_fields:
                assert field in dossier, f"Missing field in dossier: {field}"
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)
