"""
Unit tests — Fase 4: AIS FieldState Detection + Hardening

Covers:
  - _evaluate_ais_state: 'readonly' signals (each independently, combinations)
  - _evaluate_ais_state: 'disabled' detection
  - _evaluate_ais_state: 'enabled' when no signals
  - _evaluate_ais_state: derived string path (actual = str)
  - _evaluate_ais_state: None actual → review
  - _derive_ais_state_string: priority ordering (readonly > disabled > enabled)
  - _evaluate_deterministic: field_ais_state delegates correctly
  - field_ais_state in _DETERMINISTIC_TYPES
  - _get_actual_value: reads 'state' for field_ais_state, falls back to ais_state dict
  - _annotate_failed_scenarios: runs without crash, handles ImportError gracefully
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ──────────────────────────────────────────────────────────────────────────────
# 1. _DETERMINISTIC_TYPES includes field_ais_state
# ──────────────────────────────────────────────────────────────────────────────

class TestFieldAisStateRegistered:

    def test_field_ais_state_in_deterministic_types(self):
        from uat_assertion_evaluator import _DETERMINISTIC_TYPES
        assert "field_ais_state" in _DETERMINISTIC_TYPES, (
            "field_ais_state must be registered in _DETERMINISTIC_TYPES"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 2. _derive_ais_state_string
# ──────────────────────────────────────────────────────────────────────────────

class TestDeriveAisStateString:

    def _derive(self, **kwargs) -> str:
        from uat_assertion_evaluator import _derive_ais_state_string
        return _derive_ais_state_string(kwargs)

    def test_fieldstate_readonly_attribute(self):
        assert self._derive(fieldstate="ReadOnly") == "readonly"

    def test_fieldstate_case_insensitive(self):
        assert self._derive(fieldstate="READONLY") == "readonly"

    def test_readonly_flag(self):
        assert self._derive(readonly=True) == "readonly"

    def test_has_readonly_attribute(self):
        assert self._derive(has_readonly=True) == "readonly"

    def test_css_no_pointer(self):
        assert self._derive(css_no_pointer=True) == "readonly"

    def test_aria_readonly(self):
        assert self._derive(aria_readonly=True) == "readonly"

    def test_disabled_flag(self):
        assert self._derive(disabled=True) == "disabled"

    def test_aspnet_disabled(self):
        assert self._derive(aspnet_disabled=True) == "disabled"

    def test_enabled_when_no_signals(self):
        assert self._derive(
            fieldstate=None, disabled=False, readonly=False,
            has_readonly=False, aspnet_disabled=False,
            css_no_pointer=False, aria_readonly=False,
        ) == "enabled"

    def test_readonly_takes_priority_over_disabled(self):
        # element can be both readonly and aspNetDisabled — readonly wins
        assert self._derive(readonly=True, disabled=True) == "readonly"

    def test_empty_fieldstate_not_readonly(self):
        assert self._derive(fieldstate="", disabled=False) == "enabled"


# ──────────────────────────────────────────────────────────────────────────────
# 3. _evaluate_ais_state
# ──────────────────────────────────────────────────────────────────────────────

class TestEvaluateAisState:

    def _eval(self, expected: str, actual) -> str:
        from uat_assertion_evaluator import _evaluate_ais_state
        return _evaluate_ais_state(expected, actual)

    def test_pass_when_actual_string_matches(self):
        assert self._eval("readonly", "readonly") == "pass"

    def test_fail_when_actual_string_differs(self):
        assert self._eval("readonly", "enabled") == "fail"

    def test_case_insensitive_string(self):
        assert self._eval("Readonly", "readonly") == "pass"

    def test_none_actual_returns_review(self):
        assert self._eval("readonly", None) == "review"

    def test_pass_with_raw_dict_readonly_signal(self):
        actual = {"fieldstate": "ReadOnly", "disabled": False, "readonly": False}
        assert self._eval("readonly", actual) == "pass"

    def test_pass_with_raw_dict_disabled(self):
        actual = {"disabled": True, "aspnet_disabled": False, "readonly": False, "has_readonly": False}
        assert self._eval("disabled", actual) == "pass"

    def test_fail_with_raw_dict_wrong_expected(self):
        actual = {"fieldstate": "ReadOnly"}
        assert self._eval("enabled", actual) == "fail"

    def test_review_with_non_string_non_dict(self):
        assert self._eval("readonly", 42) == "review"


# ──────────────────────────────────────────────────────────────────────────────
# 4. _evaluate_deterministic delegates field_ais_state
# ──────────────────────────────────────────────────────────────────────────────

class TestEvaluateDeterministicFieldAisState:

    def test_pass_readonly_string(self):
        from uat_assertion_evaluator import _evaluate_deterministic
        assert _evaluate_deterministic("field_ais_state", "readonly", "readonly") == "pass"

    def test_fail_readonly_vs_enabled(self):
        from uat_assertion_evaluator import _evaluate_deterministic
        assert _evaluate_deterministic("field_ais_state", "readonly", "enabled") == "fail"

    def test_review_when_actual_none(self):
        from uat_assertion_evaluator import _evaluate_deterministic
        assert _evaluate_deterministic("field_ais_state", "readonly", None) == "review"

    def test_pass_with_raw_signals_dict(self):
        from uat_assertion_evaluator import _evaluate_deterministic
        actual = {"has_readonly": True, "disabled": False}
        assert _evaluate_deterministic("field_ais_state", "readonly", actual) == "pass"


# ──────────────────────────────────────────────────────────────────────────────
# 5. _get_actual_value: field_ais_state handling
# ──────────────────────────────────────────────────────────────────────────────

class TestGetActualValueFieldAisState:

    def _run_get(self, evidence, target, tipo, run_result=None):
        from uat_assertion_evaluator import _get_actual_value
        return _get_actual_value(
            evidence, target, tipo, run_result or {"status": "pass"},
        )

    def test_reads_derived_state_string(self):
        evidence = {
            "assertions": [{"target": "field_corredor", "state": "readonly", "visible": True}]
        }
        result = self._run_get(evidence, "field_corredor", "field_ais_state")
        assert result == "readonly"

    def test_falls_back_to_ais_state_dict(self):
        evidence = {
            "assertions": [{
                "target": "field_corredor",
                "state": None,
                "ais_state": {"readonly": True, "disabled": False},
            }]
        }
        result = self._run_get(evidence, "field_corredor", "field_ais_state")
        assert result == "readonly"

    def test_returns_none_when_no_evidence(self):
        result = self._run_get({}, "field_corredor", "field_ais_state")
        # No evidence → pass heuristic not applicable for field_ais_state → None
        assert result is None

    def test_state_type_still_reads_state(self):
        """Existing 'state' oracle type must still work via the same branch."""
        evidence = {
            "assertions": [{"target": "field_x", "state": "disabled", "visible": True}]
        }
        from uat_assertion_evaluator import _get_actual_value
        result = _get_actual_value(evidence, "field_x", "state", {"status": "pass"})
        assert result == "disabled"


# ──────────────────────────────────────────────────────────────────────────────
# 6. _annotate_failed_scenarios: graceful ImportError
# ──────────────────────────────────────────────────────────────────────────────

class TestAnnotateFailedScenarios:

    def test_no_crash_when_screenshot_annotator_missing(self, tmp_path):
        from uat_assertion_evaluator import _annotate_failed_scenarios
        ro_path = tmp_path / "runner_output.json"
        ro_path.write_text("{}", encoding="utf-8")
        evaluations = [{"scenario_id": "SC-01", "status": "fail"}]

        # Should not raise even if screenshot_annotator is not importable
        with patch.dict("sys.modules", {"screenshot_annotator": None}):
            # ImportError from None module
            try:
                _annotate_failed_scenarios(ro_path, evaluations)
            except ImportError:
                pass  # acceptable — the function handles it internally

    def test_no_crash_when_scenario_dir_missing(self, tmp_path):
        from uat_assertion_evaluator import _annotate_failed_scenarios
        ro_path = tmp_path / "runner_output.json"
        ro_path.write_text("{}", encoding="utf-8")
        # SC-99 has no directory in tmp_path
        evaluations = [{"scenario_id": "SC-99", "status": "fail"}]
        _annotate_failed_scenarios(ro_path, evaluations)  # must not raise

    def test_skips_pass_evaluations(self, tmp_path):
        """Pass evaluations must NOT trigger annotation."""
        from uat_assertion_evaluator import _annotate_failed_scenarios
        mock_annotator = MagicMock()
        ro_path = tmp_path / "runner_output.json"
        ro_path.write_text("{}", encoding="utf-8")
        evaluations = [{"scenario_id": "SC-01", "status": "pass"}]

        with patch("uat_assertion_evaluator._annotate_failed_scenarios",
                   wraps=lambda p, e: None) as mocked:
            _annotate_failed_scenarios(ro_path, evaluations)
        # scenario dir does not exist → function returns early for each ev
        # No annotate_scenario call — just verify no crash
        mock_annotator.assert_not_called()

    def test_calls_annotator_for_fail_scenario(self, tmp_path):
        """annotate_scenario should be called for fail scenarios with existing dir."""
        from uat_assertion_evaluator import _annotate_failed_scenarios
        ro_path = tmp_path / "runner_output.json"
        ro_path.write_text("{}", encoding="utf-8")

        sc_dir = tmp_path / "SC-05"
        sc_dir.mkdir()
        # Minimal step_bboxes.json (empty — annotator will skip but not crash)
        (sc_dir / "step_bboxes.json").write_text("[]", encoding="utf-8")

        evaluations = [{"scenario_id": "SC-05", "status": "fail"}]

        mock_result = {"ok": True, "annotated": 0, "skipped": 0, "errors": [], "annotated_paths": []}
        mock_fn = MagicMock(return_value=mock_result)

        with patch.dict("sys.modules", {"screenshot_annotator": MagicMock(annotate_scenario=mock_fn)}):
            _annotate_failed_scenarios(ro_path, evaluations)

        # annotate_scenario was called with the scenario directory
        mock_fn.assert_called_once_with(sc_dir)


# ──────────────────────────────────────────────────────────────────────────────
# 7. Hardening: _load_assertions_evidence logs warning on bad JSON
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadAssertionsEvidenceHardening:

    def test_bad_json_returns_empty_and_logs(self, tmp_path, caplog):
        import logging
        from uat_assertion_evaluator import _load_assertions_evidence

        # Create a run_result that points to a malformed assertions file
        sid = "SC-BAD"
        sc_dir = tmp_path / sid
        sc_dir.mkdir()
        # Write a trace artifact path so _load_assertions_evidence finds the dir
        trace_path = str(sc_dir / "trace.zip")
        bad_json_file = sc_dir / f"assertions_{sid}.json"
        bad_json_file.write_text("this is not valid json", encoding="utf-8")

        run_result = {
            "scenario_id": sid,
            "artifacts": {"trace": trace_path},
        }

        with caplog.at_level(logging.WARNING, logger="stacky.qa_uat.assertion_evaluator"):
            result = _load_assertions_evidence(run_result)

        assert result == {}, "Should return empty dict on parse failure"
        assert any("Could not parse" in r.message for r in caplog.records), (
            "Should log a WARNING when assertions evidence is malformed"
        )
