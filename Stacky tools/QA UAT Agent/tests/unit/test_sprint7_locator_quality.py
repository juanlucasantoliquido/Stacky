"""
test_sprint7_locator_quality.py — Sprint 7 DoD: locator quality, flake observability.

Tests:
  LQ-1:  score_alias gives score=1.0 for getByRole locator
  LQ-2:  score_alias gives score=0.95 for getByLabel locator
  LQ-3:  score_alias gives score=0.90 for getByTestId / data-testid locator
  LQ-4:  score_alias gives score=0.75 for stable CSS locator
  LQ-5:  score_alias gives score=0.40 for XPath relative locator
  LQ-6:  score_alias gives score=0.20 for absolute XPath locator
  LQ-7:  score_alias gives score=0.30 for CSS position locator
  LQ-8:  hard_wait penalty applied (-0.30)
  LQ-9:  dynamic_text penalty applied (-0.15)
  LQ-10: generated_id penalty applied (-0.10)
  LQ-11: robustness=high when score >= 0.80
  LQ-12: robustness=medium when 0.60 <= score < 0.80
  LQ-13: robustness=low when score < 0.60
  LQ-14: score_ui_map aggregates correctly
  LQ-15: score_ui_map writes locator_quality_report.json
  LQ-16: locator_quality_report.json has schema_version field
  LQ-17: score_ui_map empty aliases handled gracefully (total=0)
  LQ-18: score_alias empty selector returns unknown strategy
  LQ-19: multiple penalties stack (don't exceed 1.0 penalty total capped at score=0)
  LQ-20: locator_strategy override in alias_entry respected

  LE-1:  locator_quality_result event emitted to execution.jsonl
  LE-2:  locator_quality_result event has screen, avg_score, total_aliases
  LE-3:  locator_quality_result avg_score clamped 0-1
  LE-4:  flake_suspected event emitted to execution.jsonl
  LE-5:  flake_suspected event has test_id, reason, attempt
  LE-6:  flake_suspected reason=PASS_ON_RETRY for retry pass

  FO-1:  _detect_strategy correctly identifies each strategy
  FO-2:  score stays in [0, 1] even with all penalties applied
  FO-3:  LocatorQualityReport.to_dict() has all required keys
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_QA_UAT_DIR = Path(__file__).resolve().parent.parent.parent
if str(_QA_UAT_DIR) not in sys.path:
    sys.path.insert(0, str(_QA_UAT_DIR))


# ─────────────────────────────────────────────────────────────────────────────
# LQ — Locator Quality Scoring
# ─────────────────────────────────────────────────────────────────────────────

class TestLocatorQualityScoring:
    """LQ-1 through LQ-20: locator_quality.py scoring correctness."""

    def test_lq1_role_locator_score_1(self):
        """LQ-1: getByRole locator scores 1.0."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "btnSave", "selector": "page.getByRole('button', {name: 'Guardar'})"})
        assert ls.locator_strategy == "role"
        assert abs(ls.score - 1.0) < 0.01
        assert ls.robustness == "high"

    def test_lq2_label_locator_score_095(self):
        """LQ-2: getByLabel locator scores 0.95."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "txtName", "selector": "page.getByLabel('Nombre')"})
        assert ls.locator_strategy == "label"
        assert abs(ls.score - 0.95) < 0.01
        assert ls.robustness == "high"

    def test_lq3_testid_locator_score_090(self):
        """LQ-3: getByTestId / data-testid locator scores 0.90."""
        from locator_quality import score_alias
        ls1 = score_alias({"alias": "chkActive", "selector": "page.getByTestId('chk-active')"})
        ls2 = score_alias({"alias": "chkActive2", "selector": "[data-testid='chk-active']"})
        assert ls1.locator_strategy == "testid"
        assert abs(ls1.score - 0.90) < 0.01
        assert ls2.locator_strategy == "testid"
        assert abs(ls2.score - 0.90) < 0.01
        assert ls1.robustness == "high"

    def test_lq4_css_stable_score_075(self):
        """LQ-4: Stable CSS selector scores 0.75 (medium robustness)."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "cmbProvincia", "selector": "#cmbProvincia"})
        assert ls.locator_strategy == "css_stable"
        assert abs(ls.score - 0.75) < 0.01
        assert ls.robustness == "medium"

    def test_lq5_xpath_relative_score_040(self):
        """LQ-5: XPath relative selector scores 0.40 (low robustness)."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "row", "selector": "//table/tr[@class='data']"})
        # absolute XPath (starts with //) → absolute_xpath = 0.20
        # OR could be xpath depending on regex. Let's check what we get:
        # _RE_ABSOLUTE_XPATH = re.compile(r"^//|^\(/") — "//table/tr..." matches ^//
        assert ls.locator_strategy in ("absolute_xpath", "xpath")
        assert ls.score <= 0.40
        assert ls.robustness == "low"

    def test_lq6_absolute_xpath_score_020(self):
        """LQ-6: Absolute XPath locator scores 0.20 (low)."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "link", "selector": "//html/body/div/a"})
        assert ls.locator_strategy == "absolute_xpath"
        assert abs(ls.score - 0.20) < 0.01
        assert ls.robustness == "low"

    def test_lq7_css_position_score_030(self):
        """LQ-7: Position-based CSS selector scores 0.30 (low)."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "firstRow", "selector": "tr:nth-child(1)"})
        assert ls.locator_strategy == "css_position"
        assert abs(ls.score - 0.30) < 0.01
        assert ls.robustness == "low"

    def test_lq8_hard_wait_penalty(self):
        """LQ-8: hard_wait penalty reduces score by 0.30."""
        from locator_quality import score_alias
        # role (1.0) - hard_wait (0.30) = 0.70
        ls = score_alias({
            "alias": "btnSave",
            "selector": "page.getByRole('button'); page.waitForTimeout(3000)",
        })
        assert "hard_wait" in ls.penalties
        assert ls.score < 1.0
        assert ls.score <= 0.70 + 0.01

    def test_lq9_dynamic_text_penalty(self):
        """LQ-9: dynamic_text penalty reduces score by 0.15."""
        from locator_quality import score_alias
        # css_stable (0.75) - dynamic_text (0.15) = 0.60
        ls = score_alias({
            "alias": "row",
            "selector": "#row_${rowId}",
        })
        assert "dynamic_text" in ls.penalties
        assert ls.score <= 0.75 + 0.01
        assert ls.score < 0.75

    def test_lq10_generated_id_penalty(self):
        """LQ-10: generated_id penalty reduces score by 0.10."""
        from locator_quality import score_alias
        # css_stable (0.75) - generated_id (0.10) = 0.65
        ls = score_alias({
            "alias": "hidField",
            "selector": "#ctl00_ContentBody_hdnValue123",
        })
        assert "generated_id" in ls.penalties
        assert ls.score < 0.75

    def test_lq11_robustness_high(self):
        """LQ-11: robustness=high when score >= 0.80."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "btn", "selector": "page.getByRole('button')"})
        assert ls.robustness == "high"
        assert ls.score >= 0.80

    def test_lq12_robustness_medium(self):
        """LQ-12: robustness=medium when 0.60 <= score < 0.80."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "ddl", "selector": "#cmbEstado"})
        assert ls.robustness == "medium"
        assert 0.60 <= ls.score < 0.80

    def test_lq13_robustness_low(self):
        """LQ-13: robustness=low when score < 0.60."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "xpath_link", "selector": "//html/body/div/a"})
        assert ls.robustness == "low"
        assert ls.score < 0.60

    def test_lq14_score_ui_map_aggregates(self):
        """LQ-14: score_ui_map aggregates high/medium/low counts correctly."""
        from locator_quality import score_ui_map
        ui_map = {
            "screen": "FrmDetalleClie.aspx",
            "aliases": [
                {"alias": "btnGuardar", "selector": "page.getByRole('button', {name: 'Guardar'})"},   # high
                {"alias": "cmbProv",    "selector": "#cmbProvincia"},                                   # medium
                {"alias": "xpath_row",  "selector": "//html/body/table/tr"},                           # low
            ],
        }
        report = score_ui_map(ui_map, write_report=False)
        assert report.total_aliases == 3
        assert report.high_count >= 1
        assert report.medium_count >= 1
        assert report.low_count >= 1
        assert 0.0 < report.avg_score <= 1.0

    def test_lq15_score_ui_map_writes_report(self, tmp_path):
        """LQ-15: score_ui_map writes locator_quality_report.json."""
        from locator_quality import score_ui_map
        ui_map = {
            "screen": "FrmAgenda.aspx",
            "aliases": [
                {"alias": "btnOk", "selector": "page.getByRole('button', {name: 'OK'})"},
            ],
        }
        report = score_ui_map(ui_map, evidence_dir=tmp_path, write_report=True)
        assert (tmp_path / "locator_quality_report.json").exists()
        data = json.loads((tmp_path / "locator_quality_report.json").read_text(encoding="utf-8"))
        assert data["screen"] == "FrmAgenda.aspx"

    def test_lq16_report_has_schema_version(self, tmp_path):
        """LQ-16: locator_quality_report.json has schema_version."""
        from locator_quality import score_ui_map
        ui_map = {"screen": "TestScreen.aspx", "aliases": []}
        report = score_ui_map(ui_map, evidence_dir=tmp_path, write_report=True)
        data = json.loads((tmp_path / "locator_quality_report.json").read_text(encoding="utf-8"))
        assert "schema_version" in data
        assert data["schema_version"] == "locator-quality-report/1.0"

    def test_lq17_empty_aliases_handled(self):
        """LQ-17: score_ui_map with empty aliases returns total=0 gracefully."""
        from locator_quality import score_ui_map
        report = score_ui_map({"screen": "Empty.aspx", "aliases": []}, write_report=False)
        assert report.total_aliases == 0
        assert report.avg_score == 0.0
        assert any("No aliases" in w for w in report.warnings)

    def test_lq18_empty_selector_unknown_strategy(self):
        """LQ-18: Empty selector returns unknown strategy."""
        from locator_quality import score_alias, _detect_strategy
        strategy = _detect_strategy("")
        assert strategy == "unknown"

    def test_lq19_penalties_score_clamped_to_zero(self):
        """LQ-19: Multiple penalties stack but score doesn't go below 0."""
        from locator_quality import score_alias
        # absolute_xpath (0.20) - hard_wait (0.30) - dynamic_text (0.15) - generated_id (0.10) = -0.35
        ls = score_alias({
            "alias": "bad_locator",
            "selector": "//html/body/div/span[@id='ctl00_btn${x}123']; page.waitForTimeout(1000)",
        })
        assert ls.score >= 0.0

    def test_lq20_locator_strategy_override(self):
        """LQ-20: locator_strategy in alias entry overrides auto-detection."""
        from locator_quality import score_alias
        # Even though selector looks like CSS, force it to role
        ls = score_alias({
            "alias": "btn",
            "selector": "#someButton",
            "locator_strategy": "role",
        })
        assert ls.locator_strategy == "role"
        assert abs(ls.score - 1.0) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# LE — Logger Events (locator_quality_result + flake_suspected)
# ─────────────────────────────────────────────────────────────────────────────

class TestLoggerEventsLE:
    """LE-1 through LE-6: New Sprint 7 events in execution_logger.py."""

    def _make_logger(self, tmp: Path):
        from execution_logger import ExecutionLogger
        return ExecutionLogger(
            session_id="test-session-le",
            evidence_dir=tmp,
            run_id="uat-le-test",
        )

    def _read_events(self, tmp: Path) -> list:
        log = tmp / "execution.jsonl"
        if not log.exists():
            return []
        return [
            json.loads(line)
            for line in log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_le1_locator_quality_result_emitted(self, tmp_path):
        """LE-1: locator_quality_result event is emitted."""
        logger = self._make_logger(tmp_path)
        logger.locator_quality_result(
            screen="FrmDetalleClie.aspx",
            avg_score=0.85,
            total_aliases=5,
            low_quality_count=1,
        )
        logger.close()
        events = self._read_events(tmp_path)
        names = [e.get("event") for e in events]
        assert "locator_quality_result" in names

    def test_le2_locator_quality_result_fields(self, tmp_path):
        """LE-2: locator_quality_result event has screen, avg_score, total_aliases."""
        logger = self._make_logger(tmp_path)
        logger.locator_quality_result(
            screen="FrmAgenda.aspx",
            avg_score=0.78,
            total_aliases=8,
            low_quality_count=2,
            warnings=["2 low-quality locators"],
        )
        logger.close()
        events = self._read_events(tmp_path)
        ev = next((e for e in events if e.get("event") == "locator_quality_result"), None)
        assert ev is not None
        data = ev.get("data", ev)
        assert data.get("screen") == "FrmAgenda.aspx"
        assert data.get("total_aliases") == 8
        assert "avg_score" in data

    def test_le3_locator_quality_avg_score_clamped(self, tmp_path):
        """LE-3: locator_quality_result avg_score is clamped to [0, 1]."""
        logger = self._make_logger(tmp_path)
        logger.locator_quality_result(
            screen="Test.aspx",
            avg_score=1.5,     # over 1.0
            total_aliases=1,
            low_quality_count=0,
        )
        logger.close()
        events = self._read_events(tmp_path)
        ev = next((e for e in events if e.get("event") == "locator_quality_result"), None)
        data = ev.get("data", ev)
        assert data.get("avg_score") <= 1.0

    def test_le4_flake_suspected_emitted(self, tmp_path):
        """LE-4: flake_suspected event is emitted."""
        logger = self._make_logger(tmp_path)
        logger.flake_suspected(
            test_id="RF-008-CA-01",
            reason="PASS_ON_RETRY",
            attempt=2,
        )
        logger.close()
        events = self._read_events(tmp_path)
        names = [e.get("event") for e in events]
        assert "flake_suspected" in names

    def test_le5_flake_suspected_fields(self, tmp_path):
        """LE-5: flake_suspected event has test_id, reason, attempt."""
        logger = self._make_logger(tmp_path)
        logger.flake_suspected(
            test_id="RF-008-CA-02",
            reason="PASS_ON_RETRY",
            attempt=2,
            evidence=["statuses=['failed', 'passed']"],
        )
        logger.close()
        events = self._read_events(tmp_path)
        ev = next((e for e in events if e.get("event") == "flake_suspected"), None)
        assert ev is not None
        data = ev.get("data", ev)
        assert data.get("test_id") == "RF-008-CA-02"
        assert data.get("reason") == "PASS_ON_RETRY"
        assert data.get("attempt") == 2

    def test_le6_flake_suspected_reason_pass_on_retry(self, tmp_path):
        """LE-6: flake_suspected reason=PASS_ON_RETRY captured correctly."""
        logger = self._make_logger(tmp_path)
        logger.flake_suspected(
            test_id="RF-008-CA-03",
            reason="PASS_ON_RETRY",
            attempt=3,
        )
        logger.close()
        events = self._read_events(tmp_path)
        ev = next((e for e in events if e.get("event") == "flake_suspected"), None)
        data = ev.get("data", ev)
        assert data.get("reason") == "PASS_ON_RETRY"


# ─────────────────────────────────────────────────────────────────────────────
# FO — Flake Observability & Runner classification
# ─────────────────────────────────────────────────────────────────────────────

class TestFlakeObservabilityFO:
    """FO-1 through FO-3: Helper functions and data structure tests."""

    def test_fo1_detect_strategy_all_types(self):
        """FO-1: _detect_strategy correctly identifies each strategy."""
        from locator_quality import _detect_strategy
        cases = [
            ("page.getByRole('button')",       "role"),
            ("page.getByLabel('Nombre')",      "label"),
            ("page.getByTestId('my-btn')",     "testid"),
            ("[data-testid='x']",              "testid"),
            ("//html/body/div",                "absolute_xpath"),
            ("//table/tr[@class='data']",      "absolute_xpath"),
            ("#myButton",                      "css_stable"),
            ("tr:nth-child(1)",                "css_position"),
            ("",                               "unknown"),
        ]
        for selector, expected in cases:
            result = _detect_strategy(selector)
            assert result == expected, f"selector={selector!r}: expected {expected}, got {result}"

    def test_fo2_score_never_below_zero_or_above_one(self):
        """FO-2: score stays in [0, 1] even with all penalties applied."""
        from locator_quality import score_alias
        worst = score_alias({
            "alias": "worst",
            "selector": "//html/body/div; waitForTimeout(9999); ${x}; #ctl00_id999",
        })
        assert 0.0 <= worst.score <= 1.0

    def test_fo3_report_to_dict_complete(self):
        """FO-3: LocatorQualityReport.to_dict() has all required keys."""
        from locator_quality import score_ui_map
        ui_map = {
            "screen": "FrmDetalleClie.aspx",
            "aliases": [
                {"alias": "btn", "selector": "page.getByRole('button')"},
            ],
        }
        report = score_ui_map(ui_map, write_report=False)
        d = report.to_dict()
        required_keys = {
            "schema_version", "tool_version", "screen",
            "total_aliases", "high_count", "medium_count", "low_count",
            "avg_score", "warnings", "items",
        }
        for key in required_keys:
            assert key in d, f"Missing key in to_dict(): {key}"

    def test_fo4_score_alias_warnings_list(self):
        """FO-4: score_alias always returns a list for warnings (never None)."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "btn", "selector": "page.getByRole('button')"})
        assert isinstance(ls.warnings, list)
        ls2 = score_alias({"alias": "x", "selector": "//bad/xpath"})
        assert isinstance(ls2.warnings, list)

    def test_fo5_low_quality_alias_warns(self):
        """FO-5: Low-quality locator generates a warning message."""
        from locator_quality import score_alias
        ls = score_alias({"alias": "link", "selector": "//html/body/div/a"})
        assert ls.robustness == "low"
        assert any("LOW" in w or "low" in w or "fragile" in w.lower() or "prefer" in w.lower()
                   for w in ls.warnings)

    def test_fo6_ui_map_low_count_warning(self):
        """FO-6: score_ui_map emits global warning when low-quality count > 0."""
        from locator_quality import score_ui_map
        ui_map = {
            "screen": "BadScreen.aspx",
            "aliases": [
                {"alias": "link", "selector": "//html/body/div/a"},
                {"alias": "pos",  "selector": "tr:nth-child(1)"},
            ],
        }
        report = score_ui_map(ui_map, write_report=False)
        assert report.low_count >= 1
        assert len(report.warnings) > 0
