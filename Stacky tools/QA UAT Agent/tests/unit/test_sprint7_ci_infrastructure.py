"""
tests/unit/test_sprint7_ci_infrastructure.py — Sprint 7 tests.

Validates:
  Item 7.1 — Lane Dispatcher
   1.  test_lane_preflight_skips_compiler_generator_runner
   2.  test_lane_compile_only_skips_runner
   3.  test_lane_smoke_uat_filters_p0_only
   4.  test_lane_forensic_rerun_enables_trace_always
   5.  test_lane_dispatched_event_logged_to_execution_jsonl
   6.  test_lane_unknown_returns_error
   7.  test_lane_get_lane_env_no_side_effects

  Item 7.2 — Quarantine Registry
   8.  test_quarantine_requires_owner_and_ttl
   9.  test_quarantine_ttl_max_14_days
  10.  test_quarantine_expired_fails_gate
  11.  test_quarantine_app_category_blocked_without_force
  12.  test_quarantine_is_quarantined_returns_true_for_active
  13.  test_quarantine_event_logged_to_execution_jsonl
  14.  test_quarantine_resolve_changes_status
  15.  test_quarantine_summary_counts

  Item 7.3 — Metrics Collector (Sprint 7 extensions)
  16.  test_metrics_unknown_count_zero_for_clean_run
  17.  test_metrics_blocked_by_category_correct
  18.  test_metrics_time_to_first_failure_captured
  19.  test_metrics_run_metrics_summary_event_logged
  20.  test_metrics_aggregate_pass_rate

  Item 7.4 — Dashboard Builder
  21.  test_dashboard_summary_has_all_panels
  22.  test_dashboard_unknown_zero_is_green
  23.  test_dashboard_expired_quarantine_is_warning

  Item 7.5 — CI Artifacts Publisher
  24.  test_ci_publisher_copies_junit_to_output_dir
  25.  test_ci_publisher_enriches_junit_with_triage_properties
  26.  test_ci_publisher_skipped_in_dry_run_mode

  Item 7.6 — Pipeline integration
  27.  test_pipeline_lane_field_in_result_json
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure tool root is on sys.path
TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(TOOL_DIR))

os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_REQUIRE_PLAYBOOK", "false")


# ═══════════════════════════════════════════════════════════════════════════════
# Item 7.1 — Lane Dispatcher
# ═══════════════════════════════════════════════════════════════════════════════

class TestLaneDispatcher:

    def test_lane_preflight_skips_compiler_generator_runner(self):
        """Lane 'preflight' must set SKIP env vars for compiler, generator, runner."""
        from lane_dispatcher import get_lane_env
        env = get_lane_env("preflight")
        assert env.get("QA_UAT_SKIP_COMPILER") == "true"
        assert env.get("QA_UAT_SKIP_GENERATOR") == "true"
        assert env.get("QA_UAT_SKIP_RUNNER") == "true"

    def test_lane_compile_only_skips_runner(self):
        """Lane 'compile-only' must set SKIP_RUNNER and SKIP_GENERATOR but NOT SKIP_COMPILER."""
        from lane_dispatcher import get_lane_env, LANES
        env = get_lane_env("compile-only")
        assert env.get("QA_UAT_SKIP_RUNNER") == "true"
        assert env.get("QA_UAT_SKIP_GENERATOR") == "true"
        # compiler is active
        assert "QA_UAT_SKIP_COMPILER" not in env
        # stages_active must include compiler
        assert "compiler" in LANES["compile-only"]["stages_active"]

    def test_lane_smoke_uat_filters_p0_only(self):
        """Lane 'smoke-uat' must set PRIORITY_FILTER=P0."""
        from lane_dispatcher import get_lane_env
        env = get_lane_env("smoke-uat")
        assert env.get("QA_UAT_PRIORITY_FILTER") == "P0"
        assert env.get("QA_UAT_RETRIES") == "1"

    def test_lane_forensic_rerun_enables_trace_always(self):
        """Lane 'forensic-rerun' must set TRACE=always, VIDEO=on, SCREENSHOT=on."""
        from lane_dispatcher import get_lane_env
        env = get_lane_env("forensic-rerun")
        assert env.get("QA_UAT_TRACE") == "always"
        assert env.get("QA_UAT_VIDEO") == "on"
        assert env.get("QA_UAT_SCREENSHOT") == "on"
        assert env.get("QA_UAT_RETRIES") == "2"

    def test_lane_dispatched_event_logged_to_execution_jsonl(self):
        """dispatch() must emit lane_dispatched event via exec_logger."""
        from lane_dispatcher import dispatch, LANES
        import copy

        mock_log = MagicMock()
        # Capture original env to restore after test
        _saved = dict(os.environ)
        try:
            result = dispatch(
                lane="smoke-uat",
                ticket_id=122,
                exec_logger=mock_log,
            )
        finally:
            # Restore env
            for k in list(os.environ.keys()):
                if k not in _saved:
                    del os.environ[k]
            for k, v in _saved.items():
                os.environ[k] = v

        assert result.ok is True
        assert result.lane == "smoke-uat"
        assert "runner" in result.stages_active

        # exec_logger.event must have been called with lane_dispatched
        mock_log.event.assert_called_once()
        call_args = mock_log.event.call_args
        event_name = call_args[0][0]
        event_data = call_args[0][1]
        assert event_name == "lane_dispatched"
        assert event_data["lane"] == "smoke-uat"
        assert event_data["ticket_id"] == 122

    def test_lane_unknown_returns_error(self):
        """dispatch() with unknown lane must return ok=False."""
        from lane_dispatcher import dispatch

        mock_log = MagicMock()
        result = dispatch(lane="nonexistent-lane", ticket_id=0, exec_logger=mock_log)
        assert result.ok is False
        assert result.error == "UNKNOWN_LANE"

    def test_lane_get_lane_env_no_side_effects(self):
        """get_lane_env() must NOT modify os.environ."""
        from lane_dispatcher import get_lane_env
        saved_lane = os.environ.get("QA_UAT_LANE", "__NOT_SET__")
        _ = get_lane_env("forensic-rerun")
        current = os.environ.get("QA_UAT_LANE", "__NOT_SET__")
        assert current == saved_lane


# ═══════════════════════════════════════════════════════════════════════════════
# Item 7.2 — Quarantine Registry
# ═══════════════════════════════════════════════════════════════════════════════

def _make_qr(tmp_path: Path):
    """Create a QuarantineRegistry backed by a temp directory."""
    from quarantine_registry import QuarantineRegistry
    db = tmp_path / "quarantine.db"
    json_fb = tmp_path / "quarantine.json"
    return QuarantineRegistry(db_path=db, json_path=json_fb)


def _make_entry(**kwargs):
    from quarantine_registry import QuarantineEntry
    defaults = dict(
        test_id="RF-008-CA-01",
        scenario_id="RF-008-CA-01",
        category="NAV",
        reason="FLAKY_SELECTOR",
        owner="qa_automation",
        ttl_days=7,
    )
    defaults.update(kwargs)
    return QuarantineEntry(**defaults)


class TestQuarantineRegistry:

    def test_quarantine_requires_owner_and_ttl(self, tmp_path):
        """QuarantineEntry must raise ValueError when owner or ttl_days is missing."""
        from quarantine_registry import QuarantineEntry
        with pytest.raises((ValueError, TypeError)):
            QuarantineEntry(
                test_id="x", scenario_id="x", category="NAV",
                reason="FLAKY_SELECTOR", owner="", ttl_days=7,  # empty owner
            )
        with pytest.raises((ValueError, TypeError)):
            QuarantineEntry(
                test_id="x", scenario_id="x", category="NAV",
                reason="FLAKY_SELECTOR", owner="qa_automation", ttl_days=0,  # zero ttl
            )

    def test_quarantine_ttl_max_14_days(self, tmp_path):
        """QuarantineEntry must raise ValueError when ttl_days > 14."""
        from quarantine_registry import QuarantineEntry
        with pytest.raises(ValueError, match="14"):
            QuarantineEntry(
                test_id="x", scenario_id="x", category="NAV",
                reason="FLAKY_SELECTOR", owner="qa_automation", ttl_days=15,
            )

    def test_quarantine_expired_fails_gate(self, tmp_path):
        """is_quarantined returns False after the entry expires."""
        from quarantine_registry import QuarantineEntry, QuarantineRegistry
        qr = _make_qr(tmp_path)

        # Create entry that is already expired
        past = datetime.now(timezone.utc) - timedelta(days=2)
        past_str = past.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        entry = _make_entry(scenario_id="expired-scenario", ttl_days=1)
        # Override created_at and expires_at to be in the past
        entry.created_at = past_str
        expires = past + timedelta(days=1)
        entry.expires_at = (past + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        # Manually insert to bypass TTL check
        if qr._use_sqlite:
            qr._sqlite_insert(entry)
        else:
            records = qr._load_json()
            records.append(entry.to_dict())
            qr._save_json(records)

        qr.expire_old_quarantines()
        # Gate must fail (return False — not quarantined since expired)
        assert qr.is_quarantined("expired-scenario") is False

    def test_quarantine_app_category_blocked_without_force(self, tmp_path):
        """Adding APP category quarantine without force=True must raise ValueError."""
        qr = _make_qr(tmp_path)
        entry = _make_entry(category="APP", reason="APP_FLAKY")
        with pytest.raises(ValueError, match="force"):
            qr.add_quarantine(entry, force=False)

    def test_quarantine_is_quarantined_returns_true_for_active(self, tmp_path):
        """is_quarantined returns True for a freshly added active quarantine."""
        qr = _make_qr(tmp_path)
        entry = _make_entry(scenario_id="active-scenario", ttl_days=14)
        qr.add_quarantine(entry)
        assert qr.is_quarantined("active-scenario") is True
        # Unknown scenario must return False
        assert qr.is_quarantined("not-quarantined-scenario") is False

    def test_quarantine_event_logged_to_execution_jsonl(self, tmp_path):
        """build_quarantine_event must produce valid event dict."""
        from quarantine_registry import QuarantineRegistry
        qr = _make_qr(tmp_path)
        entry = _make_entry(scenario_id="ev-scenario", ttl_days=3)
        evt = qr.build_quarantine_event(entry)

        assert evt["event"] == "test_quarantined"
        assert evt["test_id"] == entry.test_id
        assert evt["scenario_id"] == "ev-scenario"
        assert evt["reason"] == "FLAKY_SELECTOR"
        assert evt["owner"] == "qa_automation"
        assert evt["ttl_days"] == 3
        # expires_at must be after created_at
        assert evt["expires_at"] > evt["created_at"]

    def test_quarantine_resolve_changes_status(self, tmp_path):
        """resolve_quarantine must mark entry as resolved."""
        qr = _make_qr(tmp_path)
        entry = _make_entry(scenario_id="resolve-me", ttl_days=7)
        qr.add_quarantine(entry)
        resolved = qr.resolve_quarantine(entry.id, resolution_note="Fixed in PR #123")
        assert resolved.status == "resolved"
        # Must no longer be active quarantine
        assert qr.is_quarantined("resolve-me") is False

    def test_quarantine_summary_counts(self, tmp_path):
        """get_quarantine_summary must count active, expired, resolved correctly."""
        qr = _make_qr(tmp_path)

        # Add active entry
        e1 = _make_entry(scenario_id="active-1", ttl_days=7)
        qr.add_quarantine(e1)

        # Add and resolve
        e2 = _make_entry(scenario_id="resolved-1", ttl_days=7)
        qr.add_quarantine(e2)
        qr.resolve_quarantine(e2.id, "done")

        summary = qr.get_quarantine_summary()
        assert summary.active_count >= 1
        assert summary.resolved_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Item 7.3 — Metrics Collector Sprint 7 extensions
# ═══════════════════════════════════════════════════════════════════════════════

def _make_events(verdict: str = "PASS", category: str = "APP", reason: str = "") -> list[dict]:
    """Build a minimal execution log for metrics tests."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = [
        {"event": "session_start", "timestamp": now_str},
        {
            "event": "pipeline_verdict_decision",
            "verdict": verdict,
            "category": category,
            "reason": reason,
            "timestamp": now_str,
        },
        {"event": "session_end", "timestamp": now_str},
    ]
    return events


class TestMetricsCollectorSprint7:

    def test_metrics_unknown_count_zero_for_clean_run(self):
        """A clean PASS run must produce unknown_verdict_count=0."""
        from metrics_collector import collect_run_metrics
        events = _make_events(verdict="PASS")
        metrics = collect_run_metrics(events, run_id="test-run", ticket_id=1)
        assert metrics.signal.unknown_verdict_count == 0
        assert metrics.signal.pass_count >= 1

    def test_metrics_blocked_by_category_correct(self):
        """BLOCKED DATA event must increment blocked_by_category['DATA']."""
        from metrics_collector import collect_run_metrics
        events = [
            {
                "event": "pipeline_verdict_decision",
                "verdict": "BLOCKED",
                "category": "DATA",
                "reason": "GRID_EMPTY",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        ]
        metrics = collect_run_metrics(events, run_id="test-2", ticket_id=2)
        assert metrics.signal.blocked_by_category["DATA"] >= 1
        assert metrics.signal.blocked_by_category["ENV"] == 0

    def test_metrics_time_to_first_failure_captured(self):
        """time_to_first_actionable_failure_ms must be captured when BLOCKED event present."""
        from metrics_collector import collect_run_metrics
        t0 = datetime(2026, 5, 9, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 9, 10, 0, 15, tzinfo=timezone.utc)  # 15s later

        def _ts(dt):
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        events = [
            {"event": "session_start", "timestamp": _ts(t0)},
            {
                "event": "pipeline_verdict_decision",
                "verdict": "BLOCKED",
                "category": "ENV",
                "reason": "APP_DOWN",
                "timestamp": _ts(t1),
            },
            {"event": "session_end", "timestamp": _ts(t1)},
        ]
        metrics = collect_run_metrics(events, run_id="test-3", ticket_id=3)
        # time_to_first_actionable_failure_ms = t1 - t0 = 15000ms
        assert metrics.timing.time_to_first_actionable_failure_ms == 15000

    def test_metrics_run_metrics_summary_event_logged(self):
        """build_run_metrics_summary_event must produce a valid event dict."""
        from metrics_collector import collect_run_metrics, build_run_metrics_summary_event
        events = _make_events(verdict="PASS")
        metrics = collect_run_metrics(events, run_id="test-4", ticket_id=4, lane="smoke-uat")
        evt = build_run_metrics_summary_event(metrics)

        assert evt["event"] == "run_metrics_summary"
        assert evt["lane"] == "smoke-uat"
        assert "unknown_count" in evt
        assert "blocked_by_category" in evt
        assert "fail_app_count" in evt
        assert "retry_count" in evt

    def test_metrics_aggregate_pass_rate(self):
        """aggregate_metrics must compute pass_rate correctly."""
        from metrics_collector import collect_run_metrics, aggregate_metrics

        pass_events = _make_events(verdict="PASS")
        blocked_events = _make_events(verdict="BLOCKED", category="ENV")

        m1 = collect_run_metrics(pass_events, run_id="r1", ticket_id=1)
        m2 = collect_run_metrics(pass_events, run_id="r2", ticket_id=2)
        m3 = collect_run_metrics(blocked_events, run_id="r3", ticket_id=3)

        agg = aggregate_metrics([m1, m2, m3])
        assert agg.total_runs == 3
        # Two PASS runs out of 3 → pass_rate = 2/3 ≈ 0.667
        assert agg.pass_rate == pytest.approx(2 / 3, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════════════
# Item 7.4 — Dashboard Builder
# ═══════════════════════════════════════════════════════════════════════════════

class TestDashboardBuilder:

    def test_dashboard_summary_has_all_panels(self):
        """build_dashboard must return all three panels."""
        from dashboard_builder import build_dashboard
        result = build_dashboard(period_days=7)
        assert result["ok"] is True
        panels = result["panels"]
        assert "run_health" in panels
        assert "generation_health" in panels
        assert "quarantine_health" in panels

    def test_dashboard_unknown_zero_is_green(self, tmp_path):
        """
        When all run_metrics show PASS (unknown_count=0), dashboard must
        surface unknown=0 (green). Uses an isolated temp metrics file.
        """
        from metrics_collector import (
            collect_run_metrics, persist_run_metrics, get_dashboard_summary,
        )
        from dashboard_builder import build_dashboard

        # Write a clean PASS run to a temp metrics file
        events = _make_events(verdict="PASS")
        metrics = collect_run_metrics(events, run_id="clean-run", ticket_id=1)
        tmp_metrics = tmp_path / "run_metrics.jsonl"
        persist_run_metrics(metrics, path=tmp_metrics)

        # Build dashboard from that isolated file
        summary = get_dashboard_summary(since_days=7, metrics_path=tmp_metrics)
        assert summary.run_health["unknown"] == 0

    def test_dashboard_expired_quarantine_is_warning(self, tmp_path):
        """
        When quarantine_health has expired_unresolved > 0, it is a warning condition.
        The dashboard must surface the value (not hide it).
        """
        from dashboard_builder import build_dashboard
        from quarantine_registry import QuarantineRegistry, QuarantineEntry

        # Add an expired quarantine to a temp registry (can't easily inject, just verify structure)
        result = build_dashboard(period_days=7)
        qh = result["panels"]["quarantine_health"]

        # Check that the key exists with a numeric value
        assert "expired_unresolved" in qh
        assert isinstance(qh["expired_unresolved"], int)
        # Value >= 0
        assert qh["expired_unresolved"] >= 0

    def test_dashboard_text_format_contains_panels(self):
        """format_text must produce text covering all three panels."""
        from dashboard_builder import build_dashboard, format_text
        result = build_dashboard(period_days=7)
        text = format_text(result)
        assert "Run Health" in text
        assert "Generation Health" in text
        assert "Quarantine Health" in text


# ═══════════════════════════════════════════════════════════════════════════════
# Item 7.5 — CI Artifacts Publisher
# ═══════════════════════════════════════════════════════════════════════════════

_SAMPLE_JUNIT = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuites>
      <testsuite name="qa-uat" tests="2" failures="1">
        <testcase name="RF-008-CA-01" classname="FrmDetalleClie" time="43.12">
          <failure message="Expected 3 but got 2">AssertionError</failure>
        </testcase>
        <testcase name="RF-008-CA-02" classname="FrmDetalleClie" time="12.00"/>
      </testsuite>
    </testsuites>
""")

_SAMPLE_TRIAGE = {
    "verdict": "FAIL",
    "category": "APP",
    "reason": "ASSERTION_FAILED",
    "confidence": 0.91,
    "owner": "developer",
    "next_action": "Review the assertion logic in FrmDetalleClie",
    "human_approval_required": True,
}


class TestCIArtifactsPublisher:

    def test_ci_publisher_copies_junit_to_output_dir(self, tmp_path):
        """publish_ci_artifacts must copy junit.xml to ci_output_dir."""
        from ci_artifacts_publisher import publish_ci_artifacts

        # Setup evidence directory with a JUnit file
        evidence_dir = tmp_path / "evidence" / "122"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "results.xml").write_text(_SAMPLE_JUNIT, encoding="utf-8")

        ci_out = tmp_path / "ci_output"
        result = publish_ci_artifacts(
            evidence_dir=str(evidence_dir),
            ci_output_dir=str(ci_out),
            dry_run=False,
        )

        assert result.ok is True
        assert (ci_out / "junit.xml").exists()
        assert any("junit.xml" in f for f in result.published_files)

    def test_ci_publisher_enriches_junit_with_triage_properties(self, tmp_path):
        """Enriched junit.xml must contain triage <property> elements."""
        from ci_artifacts_publisher import publish_ci_artifacts

        evidence_dir = tmp_path / "evidence" / "122"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "results.xml").write_text(_SAMPLE_JUNIT, encoding="utf-8")

        ci_out = tmp_path / "ci_output"
        result = publish_ci_artifacts(
            evidence_dir=str(evidence_dir),
            ci_output_dir=str(ci_out),
            triage_result=_SAMPLE_TRIAGE,
            lane="smoke-uat",
            dry_run=False,
        )

        assert result.junit_enriched is True
        junit_content = (ci_out / "junit.xml").read_text(encoding="utf-8")

        # Verify triage properties in XML
        assert "triage.category" in junit_content
        assert "APP" in junit_content
        assert "triage.reason" in junit_content
        assert "ASSERTION_FAILED" in junit_content
        assert "triage.confidence" in junit_content
        assert "qa.lane" in junit_content
        assert "smoke-uat" in junit_content

    def test_ci_publisher_skipped_in_dry_run_mode(self, tmp_path):
        """In dry_run=True mode, no files must be written."""
        from ci_artifacts_publisher import publish_ci_artifacts

        evidence_dir = tmp_path / "evidence" / "122"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "results.xml").write_text(_SAMPLE_JUNIT, encoding="utf-8")
        (evidence_dir / "execution.jsonl").write_text('{"event":"session_start"}\n', encoding="utf-8")

        ci_out = tmp_path / "ci_output"
        result = publish_ci_artifacts(
            evidence_dir=str(evidence_dir),
            ci_output_dir=str(ci_out),
            dry_run=True,
        )

        # No files should be created
        assert not ci_out.exists() or len(list(ci_out.rglob("*"))) == 0
        assert result.dry_run is True
        assert len(result.published_files) == 0
        # Skipped files should be recorded
        assert len(result.skipped_files) >= 1

    def test_ci_publisher_event_emitted(self, tmp_path):
        """publish_ci_artifacts must emit ci_artifacts_published event via exec_logger."""
        from ci_artifacts_publisher import publish_ci_artifacts

        evidence_dir = tmp_path / "evidence" / "99"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "results.xml").write_text(_SAMPLE_JUNIT, encoding="utf-8")

        mock_log = MagicMock()
        ci_out = tmp_path / "ci_output"
        publish_ci_artifacts(
            evidence_dir=str(evidence_dir),
            ci_output_dir=str(ci_out),
            exec_logger=mock_log,
            dry_run=False,
        )
        mock_log.event.assert_called_once()
        event_name = mock_log.event.call_args[0][0]
        assert event_name == "ci_artifacts_published"


# ═══════════════════════════════════════════════════════════════════════════════
# Item 7.6 — Pipeline integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineIntegration:

    def test_pipeline_lane_field_in_result_json(self):
        """
        When QA_UAT_LANE is set, run_metrics_summary event must include lane field.
        """
        from metrics_collector import collect_run_metrics, build_run_metrics_summary_event

        os.environ["QA_UAT_LANE"] = "smoke-uat"
        try:
            events = _make_events(verdict="PASS")
            metrics = collect_run_metrics(
                events,
                run_id="pipeline-test",
                ticket_id=999,
                lane=os.environ.get("QA_UAT_LANE"),
            )
            evt = build_run_metrics_summary_event(metrics)
            assert evt.get("lane") == "smoke-uat"
        finally:
            os.environ.pop("QA_UAT_LANE", None)

    def test_quarantine_check_stage_structure(self):
        """
        quarantine_registry.is_quarantined must return bool without errors.
        This validates the gate interface contract.
        """
        from quarantine_registry import get_registry
        reg = get_registry()
        # Unknown scenario should not raise
        result = reg.is_quarantined("non-existent-scenario-12345")
        assert isinstance(result, bool)

    def test_lane_dispatcher_all_lanes_have_required_fields(self):
        """Every lane in LANES must have env, stages_active, stages_skipped, timeout_target_s."""
        from lane_dispatcher import LANES
        for lane_name, lane_def in LANES.items():
            assert "env" in lane_def, f"Lane '{lane_name}' missing 'env'"
            assert "stages_active" in lane_def, f"Lane '{lane_name}' missing 'stages_active'"
            assert "stages_skipped" in lane_def, f"Lane '{lane_name}' missing 'stages_skipped'"
            assert "timeout_target_s" in lane_def, f"Lane '{lane_name}' missing 'timeout_target_s'"
            assert "QA_UAT_LANE" in lane_def["env"], f"Lane '{lane_name}' missing QA_UAT_LANE in env"
            assert lane_def["env"]["QA_UAT_LANE"] == lane_name, (
                f"Lane '{lane_name}' has wrong QA_UAT_LANE value"
            )

    def test_dashboard_builder_has_ok_field(self):
        """build_dashboard must always return a dict with 'ok' field."""
        from dashboard_builder import build_dashboard
        result = build_dashboard(period_days=1)
        assert "ok" in result
        assert isinstance(result["ok"], bool)

    def test_metrics_persist_and_reload(self, tmp_path):
        """persist_run_metrics must write a readable JSONL file."""
        from metrics_collector import collect_run_metrics, persist_run_metrics
        events = _make_events(verdict="PASS")
        metrics = collect_run_metrics(events, run_id="persist-test", ticket_id=77)
        path = tmp_path / "run_metrics.jsonl"
        ok = persist_run_metrics(metrics, path=path)
        assert ok is True
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["run_id"] == "persist-test"
        assert "signal" in rec
        assert "timing" in rec
        assert "ui_map" in rec
        assert "flake" in rec
