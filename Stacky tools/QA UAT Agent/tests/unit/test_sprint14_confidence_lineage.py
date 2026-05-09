"""
tests/unit/test_sprint14_confidence_lineage.py — Sprint 14 tests.

Tests:
  test_confidence_scorer.py
    1.  test_score_all_empty_scenarios_returns_ok
    2.  test_score_oracle_pass_adds_bonus
    3.  test_score_oracle_fail_adds_penalty
    4.  test_score_no_oracle_p0_adds_heavy_penalty
    5.  test_score_no_oracle_non_p0_no_penalty
    6.  test_score_seed_applied_adds_bonus
    7.  test_score_seed_skipped_adds_penalty
    8.  test_score_cleanup_confirmed_adds_bonus
    9.  test_score_cleanup_failed_adds_penalty
    10. test_score_many_assertions_adds_bonus
    11. test_score_no_assertions_adds_penalty
    12. test_score_fingerprint_matched_adds_bonus
    13. test_score_fingerprint_mismatch_adds_penalty
    14. test_score_screenshot_trace_add_bonus
    15. test_score_clamped_to_0_100
    16. test_score_level_high_medium_low
    17. test_publish_blocked_when_score_below_threshold
    18. test_publish_not_blocked_when_score_above_threshold
    19. test_score_all_writes_confidence_report_artifact
    20. test_confidence_report_to_dict_has_schema_version
    21. test_score_all_reads_oracle_artifact_from_evidence

  data_lineage_builder.py
    22. test_build_empty_run_dir_returns_ok
    23. test_build_writes_data_lineage_artifact
    24. test_build_lineage_schema_version
    25. test_build_extracts_seeded_fields_from_sql
    26. test_build_marks_cleaned_up_when_cleanup_artifact_present

  GET /api/qa-uat/confidence-report (Flask)
    27. test_confidence_endpoint_missing_params_400
    28. test_confidence_endpoint_no_report_returns_ok_null
    29. test_confidence_endpoint_returns_report_when_exists

  POST /api/qa-uat/confidence-report/score (Flask)
    30. test_confidence_score_endpoint_missing_run_id_400
    31. test_confidence_score_endpoint_missing_ticket_id_400
    32. test_confidence_score_endpoint_returns_result

  GET /api/qa-uat/data-lineage (Flask)
    33. test_data_lineage_endpoint_missing_params_400
    34. test_data_lineage_endpoint_no_lineage_returns_ok_null
    35. test_data_lineage_endpoint_returns_lineage_when_exists

  POST /api/qa-uat/data-lineage/build (Flask)
    36. test_data_lineage_build_endpoint_missing_run_id_400
    37. test_data_lineage_build_endpoint_returns_result

All tests run without DB or network.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(TOOL_DIR))

BACKEND_DIR = TOOL_DIR.parent.parent / "Stacky Agents" / "backend"


# ─────────────────────────────────────────────────────────────────────────────
# test_confidence_scorer — unit tests
# ─────────────────────────────────────────────────────────────────────────────

from test_confidence_scorer import (  # noqa: E402
    score,
    score_all,
    ConfidenceLevel,
    ConfidenceScore,
    ConfidenceScorerResult,
    _DEFAULT_MIN_CONFIDENCE,
    _W_ORACLE_PASS,
    _W_SEED_APPLIED,
    _W_CLEANUP_CONFIRMED,
    _W_MANY_ASSERTIONS,
    _W_FINGERPRINT_MATCHED,
    _W_SCREENSHOT,
    _W_TRACE,
    _P_NO_ORACLE_P0,
    _P_ORACLE_FAIL,
    _P_WEAK_ONLY_ORACLE,
    _P_SEED_SKIPPED,
    _P_CLEANUP_FAILED,
    _P_NO_ASSERTIONS,
    _P_FINGERPRINT_MISMATCH,
)


class TestConfidenceScorer:

    def test_score_all_empty_scenarios_returns_ok(self, tmp_path):
        result = score_all(scenarios=[], evidence_dir=tmp_path, run_id="r1", ticket_id=1)
        assert isinstance(result, ConfidenceScorerResult)
        assert result.ok is True
        assert result.total_scenarios == 0
        assert result.publish_blocked is False

    def test_score_oracle_pass_adds_bonus(self):
        cs = score("SC-001", oracle_verdict="PASS")
        oracle_delta = sum(f.delta for f in cs.factors if f.name == "oracle_pass")
        assert oracle_delta == _W_ORACLE_PASS

    def test_score_oracle_fail_adds_penalty(self):
        cs = score("SC-001", oracle_verdict="FAIL")
        oracle_delta = sum(f.delta for f in cs.factors if f.name == "oracle_fail")
        assert oracle_delta == _P_ORACLE_FAIL

    def test_score_no_oracle_p0_adds_heavy_penalty(self):
        cs = score("SC-P0", is_p0=True, oracle_verdict=None)
        penalty = sum(f.delta for f in cs.factors if f.name == "no_oracle_p0")
        assert penalty == _P_NO_ORACLE_P0

    def test_score_no_oracle_non_p0_no_penalty(self):
        cs = score("SC-P1", is_p0=False, oracle_verdict=None)
        penalty_factors = [f for f in cs.factors if "oracle" in f.name.lower()]
        assert len(penalty_factors) == 0

    def test_score_seed_applied_adds_bonus(self):
        cs = score("SC-001", seed_verdict="APPLIED")
        delta = sum(f.delta for f in cs.factors if f.name == "seed_applied")
        assert delta == _W_SEED_APPLIED

    def test_score_seed_skipped_adds_penalty(self):
        cs = score("SC-001", seed_verdict="SKIPPED")
        delta = sum(f.delta for f in cs.factors if f.name == "seed_skipped")
        assert delta == _P_SEED_SKIPPED

    def test_score_cleanup_confirmed_adds_bonus(self):
        cs = score("SC-001", cleanup_verdict="CLEANED")
        delta = sum(f.delta for f in cs.factors if f.name == "cleanup_confirmed")
        assert delta == _W_CLEANUP_CONFIRMED

    def test_score_cleanup_failed_adds_penalty(self):
        cs = score("SC-001", cleanup_verdict="ERROR")
        delta = sum(f.delta for f in cs.factors if f.name == "cleanup_failed")
        assert delta == _P_CLEANUP_FAILED

    def test_score_many_assertions_adds_bonus(self):
        cs = score("SC-001", assertion_count=5)
        delta = sum(f.delta for f in cs.factors if f.name == "many_assertions")
        assert delta == _W_MANY_ASSERTIONS

    def test_score_no_assertions_adds_penalty(self):
        cs = score("SC-001", assertion_count=0)
        delta = sum(f.delta for f in cs.factors if f.name == "no_assertions")
        assert delta == _P_NO_ASSERTIONS

    def test_score_fingerprint_matched_adds_bonus(self):
        cs = score("SC-001", deployment_matched=True)
        delta = sum(f.delta for f in cs.factors if f.name == "fingerprint_matched")
        assert delta == _W_FINGERPRINT_MATCHED

    def test_score_fingerprint_mismatch_adds_penalty(self):
        cs = score("SC-001", deployment_matched=False)
        delta = sum(f.delta for f in cs.factors if f.name == "fingerprint_mismatch")
        assert delta == _P_FINGERPRINT_MISMATCH

    def test_score_screenshot_trace_add_bonus(self):
        cs = score("SC-001", has_screenshot=True, has_trace=True)
        screenshot_delta = sum(f.delta for f in cs.factors if f.name == "screenshot")
        trace_delta = sum(f.delta for f in cs.factors if f.name == "trace")
        assert screenshot_delta == _W_SCREENSHOT
        assert trace_delta == _W_TRACE

    def test_score_clamped_to_0_100(self):
        # With all bonuses maximized
        cs_high = score(
            "SC-ALL",
            oracle_verdict="PASS",
            seed_verdict="APPLIED",
            cleanup_verdict="CLEANED",
            assertion_count=10,
            deployment_matched=True,
            has_screenshot=True,
            has_trace=True,
        )
        assert 0 <= cs_high.score <= 100

        # With all penalties maximized
        cs_low = score(
            "SC-NONE",
            is_p0=True,
            oracle_verdict="FAIL",
            seed_verdict="SKIPPED",
            cleanup_verdict="ERROR",
            assertion_count=0,
            deployment_matched=False,
        )
        assert 0 <= cs_low.score <= 100

    def test_score_level_high_medium_low(self):
        assert score("SC", oracle_verdict="PASS", seed_verdict="APPLIED",
                     assertion_count=5, cleanup_verdict="CLEANED").level in (
            ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW
        )
        # Guaranteed LOW: P0 with no oracle, no assertions, no seed
        cs_low = score("SC-LOW", is_p0=True, oracle_verdict=None, assertion_count=0)
        assert cs_low.level == ConfidenceLevel.LOW

    def test_publish_blocked_when_score_below_threshold(self):
        cs = score("SC-LOW", is_p0=True, oracle_verdict=None, assertion_count=0, min_confidence=60)
        assert cs.publish_blocked is True

    def test_publish_not_blocked_when_score_above_threshold(self):
        cs = score(
            "SC-HIGH",
            oracle_verdict="PASS",
            seed_verdict="APPLIED",
            cleanup_verdict="CLEANED",
            assertion_count=10,
            deployment_matched=True,
            has_screenshot=True,
            has_trace=True,
            min_confidence=60,
        )
        assert cs.publish_blocked is False

    def test_score_all_writes_confidence_report_artifact(self, tmp_path):
        result = score_all(
            scenarios=[{"scenario_id": "SC-001", "priority": 1}],
            evidence_dir=tmp_path,
            run_id="run-conf",
            ticket_id=77,
        )
        artifact = tmp_path / "77" / "run-conf" / "confidence_report.json"
        assert artifact.is_file()
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["run_id"] == "run-conf"
        assert data["ticket_id"] == 77
        assert "schema_version" in data

    def test_confidence_report_to_dict_has_schema_version(self, tmp_path):
        result = score_all(scenarios=[], evidence_dir=tmp_path, run_id="r1", ticket_id=1)
        d = result.to_dict()
        assert "schema_version" in d
        assert d["schema_version"].startswith("confidence_report/")

    def test_score_all_reads_oracle_artifact_from_evidence(self, tmp_path):
        """score_all picks up oracle_verdict from oracle_result.json artifact"""
        # Create a fake oracle_result.json
        evidence_run_dir = tmp_path / "88" / "run-oracle"
        evidence_run_dir.mkdir(parents=True)
        (evidence_run_dir / "oracle_result.json").write_text(json.dumps({
            "scenario_results": [
                {
                    "scenario_id": "SC-ORACLE",
                    "oracle_verdict": "PASS",
                    "is_p0": True,
                    "oracle_count": 1,
                    "strong_count": 1,
                    "weak_count": 0,
                    "pass_count": 1,
                    "fail_count": 0,
                    "blocking": False,
                    "oracle_checks": [],
                }
            ]
        }), encoding="utf-8")

        result = score_all(
            scenarios=[{"scenario_id": "SC-ORACLE", "priority": 0}],
            evidence_dir=tmp_path,
            run_id="run-oracle",
            ticket_id=88,
        )
        assert result.total_scenarios == 1
        sc = result.scenario_scores[0]
        assert sc.scenario_id == "SC-ORACLE"
        # oracle_pass factor should be present since oracle_verdict=PASS was read
        oracle_bonus = sum(f.delta for f in sc.factors if f.name == "oracle_pass")
        assert oracle_bonus == _W_ORACLE_PASS


# ─────────────────────────────────────────────────────────────────────────────
# data_lineage_builder — unit tests
# ─────────────────────────────────────────────────────────────────────────────

from data_lineage_builder import (  # noqa: E402
    build,
    DataLineageResult,
    LineageSource,
    _safe_value,
    _extract_seed_fields_from_sql,
)


class TestDataLineageBuilder:

    def test_build_empty_run_dir_returns_ok(self, tmp_path):
        result = build(evidence_dir=tmp_path, run_id="run-1", ticket_id=1)
        assert isinstance(result, DataLineageResult)
        assert result.ok is True
        assert result.total_entries == 0

    def test_build_writes_data_lineage_artifact(self, tmp_path):
        result = build(evidence_dir=tmp_path, run_id="run-lin", ticket_id=33)
        artifact = tmp_path / "33" / "run-lin" / "data_lineage.json"
        assert artifact.is_file()
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["run_id"] == "run-lin"
        assert data["ticket_id"] == 33

    def test_build_lineage_schema_version(self, tmp_path):
        result = build(evidence_dir=tmp_path, run_id="r1", ticket_id=1)
        d = result.to_dict()
        assert "schema_version" in d
        assert d["schema_version"].startswith("data_lineage/")

    def test_build_extracts_seeded_fields_from_sql(self, tmp_path):
        """Seed SQL with INSERT INTO → fields extracted as SEEDED lineage entries"""
        run_dir = tmp_path / "99" / "run-seed"
        run_dir.mkdir(parents=True)

        # Write a fake seed execution artifact
        seed_script = run_dir / "seed_proposal_SC-001.sql"
        seed_script.write_text(
            "BEGIN TRANSACTION;\n"
            "INSERT INTO Cliente (CLCOD, CLNOM) VALUES ('123456', 'Juan Prueba');\n"
            "ROLLBACK;\n",
            encoding="utf-8",
        )
        (run_dir / "seed_execution_result_SC-001.json").write_text(json.dumps({
            "scenario_id": "SC-001",
            "seed_run_id": "seed-99-ABC",
            "script_path": str(seed_script),
            "verdict": "APPLIED",
            "applied_at": "2026-05-01T12:00:00Z",
        }), encoding="utf-8")

        result = build(evidence_dir=tmp_path, run_id="run-seed", ticket_id=99)
        assert result.seeded_count >= 1
        fields = {e.field for e in result.entries}
        assert "CLCOD" in fields or "seed_script" in fields  # at minimum the script entry

    def test_build_marks_cleaned_up_when_cleanup_artifact_present(self, tmp_path):
        """Cleanup artifact marks the corresponding SEEDED entry as cleaned_up=True"""
        run_dir = tmp_path / "99" / "run-clean"
        run_dir.mkdir(parents=True)

        seed_script = run_dir / "seed_proposal_SC-002.sql"
        seed_script.write_text("INSERT INTO T (X) VALUES ('A');", encoding="utf-8")

        (run_dir / "seed_execution_result_SC-002.json").write_text(json.dumps({
            "scenario_id": "SC-002",
            "seed_run_id": "seed-99-XYZ",
            "script_path": str(seed_script),
            "verdict": "APPLIED",
        }), encoding="utf-8")

        (run_dir / "seed_cleanup_result_SC-002.json").write_text(json.dumps({
            "scenario_id": "SC-002",
            "verdict": "CLEANED",
            "cleaned_at": "2026-05-01T12:10:00Z",
        }), encoding="utf-8")

        result = build(evidence_dir=tmp_path, run_id="run-clean", ticket_id=99)
        cleaned_entries = [e for e in result.entries if e.scenario_id == "SC-002" and e.cleaned_up]
        assert len(cleaned_entries) >= 1

    def test_safe_value_redacts_pii_fields(self):
        assert _safe_value("password", "secret123") is None
        assert _safe_value("dni", "12345678") is None
        assert _safe_value("email", "test@test.com") is None

    def test_safe_value_keeps_non_pii(self):
        assert _safe_value("CLCOD", "123456") == "123456"
        assert _safe_value("estado", "ACT") == "ACT"

    def test_extract_seed_fields_parses_insert(self):
        sql = "INSERT INTO Cliente (CLCOD, CLNOM) VALUES ('999', 'Test User');"
        fields = _extract_seed_fields_from_sql(sql)
        assert "CLCOD" in fields
        assert fields["CLCOD"] == "999"


# ─────────────────────────────────────────────────────────────────────────────
# Flask endpoint tests
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app  # type: ignore[import]
    application = create_app()
    yield application


@pytest.fixture()
def client(app, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    with patch("api.qa_uat._PIPELINE_ROOT", tmp_path):
        with app.test_client() as c:
            yield c, tmp_path


class TestConfidenceReportEndpoint:

    def test_confidence_endpoint_missing_params_400(self, client):
        c, _ = client
        resp = c.get("/api/qa-uat/confidence-report")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_confidence_endpoint_no_report_returns_ok_null(self, client):
        c, _ = client
        resp = c.get("/api/qa-uat/confidence-report?run_id=run-1&ticket_id=99")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["report"] is None

    def test_confidence_endpoint_returns_report_when_exists(self, client):
        c, tmp = client
        artifact_dir = tmp / "evidence" / "99" / "run-conf"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "confidence_report.json").write_text(json.dumps({
            "schema_version": "confidence_report/1.0",
            "ok": True,
            "run_id": "run-conf",
            "ticket_id": 99,
            "total_scenarios": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "blocked_count": 0,
            "min_confidence": 60,
            "publish_blocked": False,
            "scenario_scores": [],
        }), encoding="utf-8")
        resp = c.get("/api/qa-uat/confidence-report?run_id=run-conf&ticket_id=99")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["report"]["run_id"] == "run-conf"


class TestConfidenceScoreEndpoint:

    def test_confidence_score_endpoint_missing_run_id_400(self, client):
        c, _ = client
        resp = c.post(
            "/api/qa-uat/confidence-report/score",
            json={"ticket_id": 99},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_confidence_score_endpoint_missing_ticket_id_400(self, client):
        c, _ = client
        resp = c.post(
            "/api/qa-uat/confidence-report/score",
            json={"run_id": "run-1"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_confidence_score_endpoint_returns_result(self, client):
        c, tmp = client
        (tmp / "evidence" / "99" / "run-score").mkdir(parents=True, exist_ok=True)
        resp = c.post(
            "/api/qa-uat/confidence-report/score",
            json={"run_id": "run-score", "ticket_id": 99},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "result" in data
        assert data["result"]["run_id"] == "run-score"


class TestDataLineageEndpoints:

    def test_data_lineage_endpoint_missing_params_400(self, client):
        c, _ = client
        resp = c.get("/api/qa-uat/data-lineage")
        assert resp.status_code == 400

    def test_data_lineage_endpoint_no_lineage_returns_ok_null(self, client):
        c, _ = client
        resp = c.get("/api/qa-uat/data-lineage?run_id=run-1&ticket_id=99")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["lineage"] is None

    def test_data_lineage_endpoint_returns_lineage_when_exists(self, client):
        c, tmp = client
        artifact_dir = tmp / "evidence" / "99" / "run-lin"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "data_lineage.json").write_text(json.dumps({
            "schema_version": "data_lineage/1.0",
            "ok": True,
            "run_id": "run-lin",
            "ticket_id": 99,
            "total_entries": 0,
            "seeded_count": 0,
            "user_supplied_count": 0,
            "fixture_count": 0,
            "discovered_count": 0,
            "unknown_count": 0,
            "entries": [],
        }), encoding="utf-8")
        resp = c.get("/api/qa-uat/data-lineage?run_id=run-lin&ticket_id=99")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["lineage"]["run_id"] == "run-lin"

    def test_data_lineage_build_endpoint_missing_run_id_400(self, client):
        c, _ = client
        resp = c.post(
            "/api/qa-uat/data-lineage/build",
            json={"ticket_id": 99},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_data_lineage_build_endpoint_returns_result(self, client):
        c, tmp = client
        (tmp / "evidence" / "99" / "run-build").mkdir(parents=True, exist_ok=True)
        resp = c.post(
            "/api/qa-uat/data-lineage/build",
            json={"run_id": "run-build", "ticket_id": 99},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["result"]["run_id"] == "run-build"
