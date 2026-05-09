"""
tests/unit/test_sprint3_env_data_preflight.py — Sprint 3 tests.

Validates:
1.  test_fingerprint_match_allows_pipeline
2.  test_fingerprint_mismatch_blocks_before_playwright
3.  test_fingerprint_missing_blocks_publish_mode
4.  test_fingerprint_missing_warns_dry_run_mode
5.  test_fingerprint_skipped_when_no_expected_build
6.  test_fingerprint_event_written_to_execution_jsonl
7.  test_fingerprint_artifact_written_to_evidence
8.  test_data_readiness_grid_empty_blocks_data_category
9.  test_data_readiness_rows_present_allows_runner
10. test_data_readiness_no_dml_only_read_allowed
11. test_data_readiness_artifact_written_to_evidence
12. test_data_readiness_event_logged_to_execution_jsonl
13. test_nav_timeout_not_final_reason_when_grid_empty
14. test_categories_data_and_nav_are_mutually_exclusive
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure tool root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_REQUIRE_PLAYBOOK", "false")

TOOL_DIR = Path(__file__).parent.parent.parent


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_expected(build_id: str = "Task-120", branch: str = "feature/RF-007") -> dict:
    return {"build_id": build_id, "commit": None, "branch": branch}


def _make_active(build_id: str = "Task-120", branch: str = "feature/RF-007") -> dict:
    return {"build_id": build_id, "commit": None, "branch": branch}


def _grid_precondition(entity: str = "ROBLG", min_rows: int = 1, input_data: dict = None) -> dict:
    return {
        "entity": entity,
        "type": "grid",
        "input_data": input_data or {"CLCOD": "12345"},
        "expected": {"min_rows": min_rows},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. test_fingerprint_match_allows_pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def test_fingerprint_match_allows_pipeline():
    """When active build matches expected, decision is ALLOW."""
    from deployment_fingerprint import check_deployment_fingerprint, _probe_sources

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)

        # Stub source probe to return matching active build
        with patch(
            "deployment_fingerprint._probe_sources",
            return_value=({"build_id": "Task-120", "commit": None, "branch": "feature/RF-007"}, "health_endpoint", ""),
        ):
            result = check_deployment_fingerprint(
                ticket_id=120,
                expected=_make_expected("Task-120", "feature/RF-007"),
                base_url="http://localhost:35017/AgendaWeb/",
                mode="publish",
                evidence_dir=evidence_dir,
                run_id="120",
            )

    assert result.decision == "ALLOW", f"Expected ALLOW but got {result.decision}"
    assert result.matched is True
    assert result.reason is None
    assert result.category is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. test_fingerprint_mismatch_blocks_before_playwright
# ═══════════════════════════════════════════════════════════════════════════════

def test_fingerprint_mismatch_blocks_before_playwright():
    """When active build differs from expected, decision is BLOCKED ENV DEPLOYMENT_MISMATCH."""
    from deployment_fingerprint import check_deployment_fingerprint

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)

        with patch(
            "deployment_fingerprint._probe_sources",
            return_value=(
                {"build_id": "Task-119", "commit": None, "branch": "feature/RF-006"},
                "health_endpoint",
                "",
            ),
        ):
            result = check_deployment_fingerprint(
                ticket_id=120,
                expected=_make_expected("Task-120", "feature/RF-007"),
                base_url="http://localhost:35017/AgendaWeb/",
                mode="publish",
                evidence_dir=evidence_dir,
                run_id="120",
            )

    assert result.decision == "BLOCKED", f"Expected BLOCKED but got {result.decision}"
    assert result.matched is False
    assert result.category == "ENV"
    assert result.reason == "DEPLOYMENT_MISMATCH"
    assert result.active["build_id"] == "Task-119"
    assert result.expected["build_id"] == "Task-120"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. test_fingerprint_missing_blocks_publish_mode
# ═══════════════════════════════════════════════════════════════════════════════

def test_fingerprint_missing_blocks_publish_mode():
    """When no source available and mode=publish, decision is BLOCKED ENV FINGERPRINT_SOURCE_MISSING."""
    from deployment_fingerprint import check_deployment_fingerprint

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)

        with patch(
            "deployment_fingerprint._probe_sources",
            return_value=({}, "unavailable", "all sources failed"),
        ):
            result = check_deployment_fingerprint(
                ticket_id=120,
                expected=_make_expected(),
                base_url="http://localhost:35017/AgendaWeb/",
                mode="publish",
                evidence_dir=evidence_dir,
                run_id="120",
            )

    assert result.decision == "BLOCKED", f"Expected BLOCKED but got {result.decision}"
    assert result.category == "ENV"
    assert result.reason == "FINGERPRINT_SOURCE_MISSING"
    assert result.matched is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. test_fingerprint_missing_warns_dry_run_mode
# ═══════════════════════════════════════════════════════════════════════════════

def test_fingerprint_missing_warns_dry_run_mode():
    """When no source available and mode=dry-run, decision is WARN (pipeline continues)."""
    from deployment_fingerprint import check_deployment_fingerprint

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)

        with patch(
            "deployment_fingerprint._probe_sources",
            return_value=({}, "unavailable", "all sources failed"),
        ):
            result = check_deployment_fingerprint(
                ticket_id=120,
                expected=_make_expected(),
                base_url="http://localhost:35017/AgendaWeb/",
                mode="dry-run",
                evidence_dir=evidence_dir,
                run_id="120",
            )

    assert result.decision == "WARN", f"Expected WARN but got {result.decision}"
    assert result.reason == "FINGERPRINT_SOURCE_MISSING"
    # In dry-run mode, WARN means matched=True (pipeline is allowed to continue)
    assert result.matched is True


# ═══════════════════════════════════════════════════════════════════════════════
# 5. test_fingerprint_skipped_when_no_expected_build
# ═══════════════════════════════════════════════════════════════════════════════

def test_fingerprint_skipped_when_no_expected_build():
    """When expected=None, result is WARN with skipped=True and NO_EXPECTED_BUILD_DEFINED."""
    from deployment_fingerprint import check_deployment_fingerprint

    with tempfile.TemporaryDirectory() as tmpdir:
        result = check_deployment_fingerprint(
            ticket_id=120,
            expected=None,
            base_url="http://localhost:35017/AgendaWeb/",
            mode="publish",
            evidence_dir=Path(tmpdir),
            run_id="120",
        )

    assert result.decision == "WARN"
    assert result.skipped is True
    assert result.reason == "NO_EXPECTED_BUILD_DEFINED"
    assert result.matched is True


# ═══════════════════════════════════════════════════════════════════════════════
# 6. test_fingerprint_event_written_to_execution_jsonl
# ═══════════════════════════════════════════════════════════════════════════════

def test_fingerprint_event_written_to_execution_jsonl():
    """deployment_fingerprint_check event must appear in execution.jsonl."""
    from execution_logger import get_logger, close_logger
    from deployment_fingerprint import check_deployment_fingerprint

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)
        log = get_logger("test_fp_event", evidence_dir=evidence_dir)
        log.session_start({
            "run_id": "test_fp_event",
            "ticket_id": 120,
            "mode": "dry-run",
            "tool": "qa_uat_agent",
            "tool_version": "test",
            "started_at": "2026-05-09T00:00:00Z",
        })

        with patch(
            "deployment_fingerprint._probe_sources",
            return_value=({}, "unavailable", "no source"),
        ):
            check_deployment_fingerprint(
                ticket_id=120,
                expected=_make_expected(),
                base_url="http://localhost:35017/AgendaWeb/",
                mode="dry-run",
                exec_logger=log,
                evidence_dir=evidence_dir,
                run_id="test_fp_event",
            )

        log.pipeline_verdict(
            verdict="WARN",
            category="ENV",
            reason="FINGERPRINT_SOURCE_MISSING",
            failed_stage=None,
            confidence=1.0,
        )
        log.session_end({"ok": True, "verdict": "WARN", "elapsed_s": 0.1})
        close_logger("test_fp_event")

        jsonl = evidence_dir / "execution.jsonl"
        events = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
        event_names = [e["event"] for e in events]

        assert "deployment_fingerprint_check" in event_names, (
            f"deployment_fingerprint_check must be in events. Got: {event_names}"
        )
        fp_events = [e for e in events if e["event"] == "deployment_fingerprint_check"]
        fp_data = fp_events[0]["data"]
        assert fp_data.get("ticket_id") == 120
        assert fp_data.get("decision") in ("WARN", "BLOCKED", "ALLOW")
        assert "source" in fp_data
        assert "expected" in fp_data
        assert "active" in fp_data


# ═══════════════════════════════════════════════════════════════════════════════
# 7. test_fingerprint_artifact_written_to_evidence
# ═══════════════════════════════════════════════════════════════════════════════

def test_fingerprint_artifact_written_to_evidence():
    """deployment_fingerprint.json must be written to evidence_dir/<run_id>/."""
    from deployment_fingerprint import check_deployment_fingerprint

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)

        with patch(
            "deployment_fingerprint._probe_sources",
            return_value=(
                {"build_id": "Task-120", "commit": "abc123", "branch": "feature/RF-007"},
                "health_endpoint",
                "",
            ),
        ):
            result = check_deployment_fingerprint(
                ticket_id=120,
                expected=_make_expected("Task-120", "feature/RF-007"),
                base_url="http://localhost:35017/AgendaWeb/",
                mode="publish",
                evidence_dir=evidence_dir,
                run_id="120",
            )

        artifact = evidence_dir / "120" / "deployment_fingerprint.json"
        assert artifact.exists(), f"Artifact must be at {artifact}"
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data.get("schema_version") == "deployment_fingerprint/1.0"
        assert data.get("decision") == "ALLOW"
        assert data.get("source") == "health_endpoint"
        assert result.artifact_path == str(artifact)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. test_data_readiness_grid_empty_blocks_data_category
# ═══════════════════════════════════════════════════════════════════════════════

def test_data_readiness_grid_empty_blocks_data_category():
    """When a grid has 0 rows, decision is BLOCKED category=DATA reason=GRID_EMPTY."""
    from uat_precondition_checker import check_data_readiness

    # Mock connector that returns 0 rows
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0,)
    mock_conn.cursor.return_value = mock_cursor

    def mock_connector():
        return mock_conn

    # Add ROBLG to safe tables for this test
    with patch("uat_precondition_checker._get_safe_tables", return_value=frozenset({"ROBLG"})):
        result = check_data_readiness(
            ticket_id=120,
            scenario_id="RF-007-CA-01",
            preconditions=[_grid_precondition("ROBLG", min_rows=1, input_data={"CLCOD": "12345"})],
            _db_connector=mock_connector,
        )

    assert result.decision == "BLOCKED", f"Expected BLOCKED but got {result.decision}"
    assert result.all_ready is False
    assert result.category == "DATA"
    assert result.reason == "GRID_EMPTY"
    assert len(result.checks) == 1
    assert result.checks[0].actual.get("row_count") == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 9. test_data_readiness_rows_present_allows_runner
# ═══════════════════════════════════════════════════════════════════════════════

def test_data_readiness_rows_present_allows_runner():
    """When a grid has >= min_rows rows, decision is ALLOW."""
    from uat_precondition_checker import check_data_readiness

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (5,)  # 5 rows
    mock_conn.cursor.return_value = mock_cursor

    def mock_connector():
        return mock_conn

    with patch("uat_precondition_checker._get_safe_tables", return_value=frozenset({"ROBLG"})):
        result = check_data_readiness(
            ticket_id=120,
            scenario_id="RF-007-CA-01",
            preconditions=[_grid_precondition("ROBLG", min_rows=1)],
            _db_connector=mock_connector,
        )

    assert result.decision == "ALLOW", f"Expected ALLOW but got {result.decision}"
    assert result.all_ready is True
    assert result.category is None
    assert result.reason is None
    assert result.checks[0].actual.get("row_count") == 5


# ═══════════════════════════════════════════════════════════════════════════════
# 10. test_data_readiness_no_dml_only_read_allowed
# ═══════════════════════════════════════════════════════════════════════════════

def test_data_readiness_no_dml_only_read_allowed():
    """data_readiness checks must NEVER issue INSERT/UPDATE/DELETE queries.

    Verifies that the mock cursor only receives SELECT COUNT(*) queries,
    which is the only type of query issued by check_data_readiness.
    """
    from uat_precondition_checker import check_data_readiness

    issued_queries: list = []
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (3,)

    def capture_execute(query, *args, **kwargs):
        issued_queries.append(query.strip())

    mock_cursor.execute.side_effect = capture_execute
    mock_conn.cursor.return_value = mock_cursor

    def mock_connector():
        return mock_conn

    with patch("uat_precondition_checker._get_safe_tables", return_value=frozenset({"ROBLG"})):
        check_data_readiness(
            ticket_id=120,
            scenario_id="RF-007-CA-01",
            preconditions=[_grid_precondition("ROBLG", min_rows=1)],
            _db_connector=mock_connector,
        )

    for query in issued_queries:
        upper_q = query.upper()
        # Must be SELECT only — no DML
        assert upper_q.startswith("SELECT"), (
            f"Illegal non-SELECT query issued by data_readiness check: {query!r}"
        )
        assert "INSERT" not in upper_q, f"INSERT found in query: {query!r}"
        assert "UPDATE" not in upper_q, f"UPDATE found in query: {query!r}"
        assert "DELETE" not in upper_q, f"DELETE found in query: {query!r}"
        assert "DROP" not in upper_q, f"DROP found in query: {query!r}"
        assert "EXEC" not in upper_q, f"EXEC found in query: {query!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# 11. test_data_readiness_artifact_written_to_evidence
# ═══════════════════════════════════════════════════════════════════════════════

def test_data_readiness_artifact_written_to_evidence():
    """data_readiness.json must be written to evidence_dir/<run_id>/."""
    from uat_precondition_checker import check_data_readiness

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (2,)
    mock_conn.cursor.return_value = mock_cursor

    def mock_connector():
        return mock_conn

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)

        with patch("uat_precondition_checker._get_safe_tables", return_value=frozenset({"ROBLG"})):
            result = check_data_readiness(
                ticket_id=120,
                scenario_id="RF-007-CA-01",
                preconditions=[_grid_precondition("ROBLG", min_rows=1)],
                _db_connector=mock_connector,
                evidence_dir=evidence_dir,
                run_id="120",
            )

        artifact = evidence_dir / "120" / "data_readiness.json"
        assert artifact.exists(), f"Artifact must be at {artifact}"
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data.get("schema_version") == "data_readiness/1.0"
        assert data.get("scenario_id") == "RF-007-CA-01"
        assert data.get("decision") == "ALLOW"
        assert isinstance(data.get("checks"), list)
        assert result.artifact_path == str(artifact)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. test_data_readiness_event_logged_to_execution_jsonl
# ═══════════════════════════════════════════════════════════════════════════════

def test_data_readiness_event_logged_to_execution_jsonl():
    """data_readiness_check event must appear in execution.jsonl."""
    from execution_logger import get_logger, close_logger
    from uat_precondition_checker import check_data_readiness

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0,)  # grid empty
    mock_conn.cursor.return_value = mock_cursor

    def mock_connector():
        return mock_conn

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)
        log = get_logger("test_dr_event", evidence_dir=evidence_dir)
        log.session_start({
            "run_id": "test_dr_event",
            "ticket_id": 120,
            "mode": "dry-run",
            "tool": "qa_uat_agent",
            "tool_version": "test",
            "started_at": "2026-05-09T00:00:00Z",
        })

        with patch("uat_precondition_checker._get_safe_tables", return_value=frozenset({"ROBLG"})):
            check_data_readiness(
                ticket_id=120,
                scenario_id="RF-007-CA-01",
                preconditions=[_grid_precondition("ROBLG", min_rows=1)],
                _db_connector=mock_connector,
                exec_logger=log,
            )

        log.pipeline_verdict(
            verdict="BLOCKED",
            category="DATA",
            reason="GRID_EMPTY",
            failed_stage="data_readiness_check",
            confidence=1.0,
        )
        log.session_end({
            "ok": False,
            "verdict": "BLOCKED",
            "category": "DATA",
            "reason": "GRID_EMPTY",
            "elapsed_s": 0.1,
        })
        close_logger("test_dr_event")

        jsonl = evidence_dir / "execution.jsonl"
        events = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
        event_names = [e["event"] for e in events]

        assert "data_readiness_check" in event_names, (
            f"data_readiness_check must be in events. Got: {event_names}"
        )
        dr_events = [e for e in events if e["event"] == "data_readiness_check"]
        dr_data = dr_events[0]["data"]
        assert dr_data.get("ticket_id") == 120
        assert dr_data.get("scenario_id") == "RF-007-CA-01"
        assert dr_data.get("decision") == "BLOCKED"
        assert dr_data.get("category") == "DATA"
        assert dr_data.get("reason") == "GRID_EMPTY"
        assert isinstance(dr_data.get("checks"), list)


# ═══════════════════════════════════════════════════════════════════════════════
# 13. test_nav_timeout_not_final_reason_when_grid_empty
# ═══════════════════════════════════════════════════════════════════════════════

def test_nav_timeout_not_final_reason_when_grid_empty():
    """infer_failure_category must return DATA for GRID_EMPTY, not NAV.

    NAVIGATION_TIMEOUT must not be the final reason when the real cause
    is an empty grid (data issue).
    """
    from uat_precondition_checker import infer_failure_category

    assert infer_failure_category("GRID_EMPTY") == "DATA"
    assert infer_failure_category("TEST_ENTITY_NOT_FOUND") == "DATA"
    assert infer_failure_category("TEST_USER_PERMISSION_MISSING") == "DATA"

    # Navigation reasons must not be confused with data reasons
    assert infer_failure_category("SELECTOR_NOT_FOUND") == "NAV"
    assert infer_failure_category("SELECTOR_TIMEOUT") == "NAV"

    # ENV reasons
    assert infer_failure_category("PAGE_LOAD_FAILED") == "ENV"
    assert infer_failure_category("DEPLOYMENT_MISMATCH") == "ENV"
    assert infer_failure_category("DATA_SOURCE_UNREACHABLE") == "ENV"


# ═══════════════════════════════════════════════════════════════════════════════
# 14. test_categories_data_and_nav_are_mutually_exclusive
# ═══════════════════════════════════════════════════════════════════════════════

def test_categories_data_and_nav_are_mutually_exclusive():
    """DATA and NAV categories must be mutually exclusive for known reason codes.

    A reason code must map to exactly one category — never both DATA and NAV.
    """
    from uat_precondition_checker import infer_failure_category

    data_reasons = [
        "GRID_EMPTY",
        "TEST_ENTITY_NOT_FOUND",
        "TEST_USER_PERMISSION_MISSING",
    ]
    nav_reasons = [
        "SELECTOR_NOT_FOUND",
        "SELECTOR_TIMEOUT",
    ]

    data_categories = {r: infer_failure_category(r) for r in data_reasons}
    nav_categories = {r: infer_failure_category(r) for r in nav_reasons}

    for reason, cat in data_categories.items():
        assert cat == "DATA", (
            f"DATA reason {reason!r} mapped to {cat!r} — must be DATA"
        )
    for reason, cat in nav_categories.items():
        assert cat == "NAV", (
            f"NAV reason {reason!r} mapped to {cat!r} — must be NAV"
        )

    # Cross-check: no DATA reason is NAV and vice-versa
    data_set = set(data_reasons)
    nav_set = set(nav_reasons)
    assert data_set.isdisjoint(nav_set), (
        f"DATA and NAV reason sets must be disjoint. Overlap: {data_set & nav_set}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Additional: DeploymentFingerprintResult dataclass contract
# ═══════════════════════════════════════════════════════════════════════════════

def test_deployment_fingerprint_result_to_dict_contract():
    """DeploymentFingerprintResult.to_dict() must include all required keys."""
    from deployment_fingerprint import DeploymentFingerprintResult

    result = DeploymentFingerprintResult(
        matched=False,
        source="health_endpoint",
        expected={"build_id": "Task-120", "commit": None, "branch": "feature/RF-007"},
        active={"build_id": "Task-119", "commit": None, "branch": "feature/RF-006"},
        decision="BLOCKED",
        category="ENV",
        reason="DEPLOYMENT_MISMATCH",
        skipped=False,
        elapsed_ms=841,
        artifact_path=None,
    )
    d = result.to_dict()
    required = {
        "matched", "source", "expected", "active",
        "decision", "category", "reason", "skipped",
        "elapsed_ms", "artifact_path",
    }
    missing = required - set(d.keys())
    assert not missing, f"to_dict() missing keys: {missing}"


def test_data_check_result_to_dict_contract():
    """DataCheck.to_dict() must include all required keys."""
    from uat_precondition_checker import DataCheck

    check = DataCheck(
        entity="ROBLG",
        type="grid",
        input_data={"CLCOD": "12345"},
        expected={"min_rows": 1},
        actual={"row_count": 0},
        decision="BLOCKED",
        category="DATA",
        reason="GRID_EMPTY",
        human_action_required="seed_cliente_con_obligaciones",
        skipped=False,
    )
    d = check.to_dict()
    required = {
        "entity", "type", "input_data", "expected", "actual",
        "decision", "category", "reason", "human_action_required", "skipped",
    }
    missing = required - set(d.keys())
    assert not missing, f"DataCheck.to_dict() missing keys: {missing}"


def test_data_readiness_result_to_dict_contract():
    """DataReadinessResult.to_dict() must include all required keys."""
    from uat_precondition_checker import DataReadinessResult, DataCheck

    check = DataCheck(
        entity="ROBLG",
        type="grid",
        input_data={"CLCOD": "12345"},
        expected={"min_rows": 1},
        actual={"row_count": 0},
        decision="BLOCKED",
        category="DATA",
        reason="GRID_EMPTY",
        human_action_required="seed_data",
        skipped=False,
    )
    result = DataReadinessResult(
        all_ready=False,
        checks=[check],
        decision="BLOCKED",
        category="DATA",
        reason="GRID_EMPTY",
        artifact_path="/tmp/data_readiness.json",
    )
    d = result.to_dict()
    required = {"all_ready", "checks", "decision", "category", "reason", "artifact_path"}
    missing = required - set(d.keys())
    assert not missing, f"DataReadinessResult.to_dict() missing keys: {missing}"


def test_fingerprint_sources_list_all_valid():
    """All source names in _ALL_SOURCES must be handled by _probe_sources without error."""
    from deployment_fingerprint import _ALL_SOURCES, _probe_sources, _SOURCE_NONE

    # Mock all HTTP and file IO to return None
    with (
        patch("deployment_fingerprint._probe_health_endpoint", return_value=None),
        patch("deployment_fingerprint._probe_file_manifest", return_value=None),
        patch("deployment_fingerprint._probe_html_meta", return_value=None),
        patch("deployment_fingerprint._probe_dll_hash", return_value=None),
        patch("deployment_fingerprint._probe_manual_config", return_value=None),
    ):
        active, source, err = _probe_sources("http://localhost/", _ALL_SOURCES)

    assert source == _SOURCE_NONE, f"Expected unavailable when all probe return None, got {source}"
    assert active == {}


def test_data_readiness_skipped_when_no_preconditions():
    """check_data_readiness with empty preconditions returns ALLOW immediately."""
    from uat_precondition_checker import check_data_readiness

    result = check_data_readiness(
        ticket_id=120,
        scenario_id="RF-007-CA-01",
        preconditions=[],
    )

    assert result.decision == "ALLOW"
    assert result.all_ready is True
    assert result.checks == []


def test_data_readiness_user_permission_missing():
    """When user lacks required permission, decision is BLOCKED DATA TEST_USER_PERMISSION_MISSING."""
    from uat_precondition_checker import check_data_readiness

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0,)  # 0 matching permission rows
    mock_conn.cursor.return_value = mock_cursor

    def mock_connector():
        return mock_conn

    result = check_data_readiness(
        ticket_id=120,
        scenario_id="RF-007-CA-01",
        preconditions=[{
            "entity": "RASIST",
            "type": "user_permission",
            "input_data": {"user": "QA_TEST_USER"},
            "expected": {"permission": "MENU_OBLIGACIONES"},
        }],
        _db_connector=mock_connector,
    )

    assert result.decision == "BLOCKED"
    assert result.category == "DATA"
    assert result.reason == "TEST_USER_PERMISSION_MISSING"


def test_data_readiness_api_unreachable():
    """When API endpoint is unreachable, decision is BLOCKED ENV DATA_SOURCE_UNREACHABLE."""
    from uat_precondition_checker import check_data_readiness
    import urllib.error

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        result = check_data_readiness(
            ticket_id=120,
            scenario_id="RF-007-CA-01",
            preconditions=[{
                "entity": "GridObligaciones",
                "type": "api_endpoint",
                "input_data": {"url": "http://localhost:35017/AgendaWeb/api/obligaciones"},
                "expected": {"status_ok": True},
            }],
        )

    assert result.decision == "BLOCKED"
    assert result.category == "ENV"
    assert result.reason == "DATA_SOURCE_UNREACHABLE"
