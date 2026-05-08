"""
Unit tests — Fase 3 Dossier Quality

Covers:
  - _compute_verdict: PARTIAL_PASS when not_tested > 0 and no fails
  - _compute_verdict: PASS when all pass, FAIL / BLOCKED / MIXED unchanged
  - _load_precondition_gaps: reads precondition_gap.json files
  - _format_coverage_gaps: builds coverage_gaps list from not_tested runs + gap data
  - uat_assertion_evaluator: evaluated_at timestamp present in output
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ──────────────────────────────────────────────────────────────────────────────
# 1. _compute_verdict: PARTIAL_PASS
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeVerdictFase3:

    def _runs(self, statuses: list[str]) -> list[dict]:
        return [{"scenario_id": f"SC-{i:02d}", "status": s} for i, s in enumerate(statuses)]

    def test_all_pass_returns_pass(self):
        from uat_dossier_builder import _compute_verdict
        assert _compute_verdict(self._runs(["pass", "pass", "pass"])) == "PASS"

    def test_partial_pass_when_some_not_tested(self):
        from uat_dossier_builder import _compute_verdict
        verdict = _compute_verdict(self._runs(["pass", "pass", "not_tested"]))
        assert verdict == "PARTIAL_PASS", f"Expected PARTIAL_PASS, got {verdict}"

    def test_partial_pass_when_most_not_tested(self):
        from uat_dossier_builder import _compute_verdict
        verdict = _compute_verdict(self._runs(["pass", "not_tested", "not_tested"]))
        assert verdict == "PARTIAL_PASS"

    def test_not_partial_pass_when_also_fail(self):
        """FAIL + not_tested → MIXED, not PARTIAL_PASS."""
        from uat_dossier_builder import _compute_verdict
        verdict = _compute_verdict(self._runs(["pass", "fail", "not_tested"]))
        assert verdict == "MIXED", f"Expected MIXED, got {verdict}"

    def test_fail_verdict(self):
        from uat_dossier_builder import _compute_verdict
        verdict = _compute_verdict(self._runs(["pass", "fail"]))
        assert verdict == "FAIL"

    def test_blocked_when_no_pass_no_fail(self):
        from uat_dossier_builder import _compute_verdict
        verdict = _compute_verdict(self._runs(["blocked", "blocked"]))
        assert verdict == "BLOCKED"

    def test_mixed_fail_and_blocked(self):
        from uat_dossier_builder import _compute_verdict
        verdict = _compute_verdict(self._runs(["pass", "fail", "blocked"]))
        assert verdict == "MIXED"

    def test_empty_runs_returns_blocked(self):
        from uat_dossier_builder import _compute_verdict
        assert _compute_verdict([]) == "BLOCKED"

    def test_all_not_tested_returns_blocked(self):
        """All not_tested with NO passing → BLOCKED (nothing confirmed working)."""
        from uat_dossier_builder import _compute_verdict
        verdict = _compute_verdict(self._runs(["not_tested", "not_tested"]))
        # pass_count == 0 → not PARTIAL_PASS
        assert verdict == "BLOCKED", f"Expected BLOCKED, got {verdict}"


# ──────────────────────────────────────────────────────────────────────────────
# 2. _load_precondition_gaps
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadPreconditionGaps:

    def test_loads_gap_file_in_subdirectory(self, tmp_path):
        from uat_dossier_builder import _load_precondition_gaps
        sid_dir = tmp_path / "SC-01"
        sid_dir.mkdir()
        gap_data = {"scenario_id": "SC-01", "unresolved": ["corredor_sin_datos"]}
        (sid_dir / "precondition_gap.json").write_text(json.dumps(gap_data), encoding="utf-8")

        gaps = _load_precondition_gaps(tmp_path)
        assert len(gaps) == 1
        assert gaps[0]["scenario_id"] == "SC-01"
        assert any(g.get("term") == "corredor_sin_datos" for g in gaps[0]["gaps"])

    def test_loads_gap_file_at_root_level(self, tmp_path):
        from uat_dossier_builder import _load_precondition_gaps
        gap_data = {"scenario_id": "SC-99", "gaps": [{"term": "riesgo", "reason": "no_data"}]}
        (tmp_path / "precondition_gap.json").write_text(json.dumps(gap_data), encoding="utf-8")

        gaps = _load_precondition_gaps(tmp_path)
        assert any(g["scenario_id"] == "SC-99" for g in gaps)

    def test_returns_empty_when_no_gap_files(self, tmp_path):
        from uat_dossier_builder import _load_precondition_gaps
        gaps = _load_precondition_gaps(tmp_path)
        assert gaps == []

    def test_ignores_malformed_gap_file(self, tmp_path):
        from uat_dossier_builder import _load_precondition_gaps
        (tmp_path / "precondition_gap.json").write_text("this is not json", encoding="utf-8")
        gaps = _load_precondition_gaps(tmp_path)
        assert gaps == []


# ──────────────────────────────────────────────────────────────────────────────
# 3. _format_coverage_gaps
# ──────────────────────────────────────────────────────────────────────────────

class TestFormatCoverageGaps:

    def test_empty_when_no_not_tested(self):
        from uat_dossier_builder import _format_coverage_gaps
        gaps = _format_coverage_gaps([], [])
        assert gaps == []

    def test_not_tested_without_gap_data(self):
        from uat_dossier_builder import _format_coverage_gaps
        runs = [{"scenario_id": "SC-05", "status": "not_tested", "reason": "PRECONDITION_MISSING_DATA"}]
        gaps = _format_coverage_gaps(runs, [])
        assert len(gaps) == 1
        assert gaps[0]["scenario_id"] == "SC-05"
        assert gaps[0]["precondition_term"] is None

    def test_not_tested_with_gap_data(self):
        from uat_dossier_builder import _format_coverage_gaps
        runs = [{"scenario_id": "SC-05", "status": "not_tested", "reason": "PRECONDITION_MISSING_DATA"}]
        precondition_gaps = [
            {
                "scenario_id": "SC-05",
                "gaps": [{"term": "corredor", "reason": "no_client_without_corredor"}],
            }
        ]
        gaps = _format_coverage_gaps(runs, precondition_gaps)
        assert len(gaps) == 1
        assert gaps[0]["precondition_term"] == "corredor"

    def test_multiple_gaps_per_scenario(self):
        from uat_dossier_builder import _format_coverage_gaps
        runs = [{"scenario_id": "SC-08", "status": "not_tested", "reason": "MISSING_DATA"}]
        precondition_gaps = [
            {
                "scenario_id": "SC-08",
                "gaps": [
                    {"term": "riesgo", "reason": "no_client_without_riesgo"},
                    {"term": "corredor", "reason": "no_client_without_corredor"},
                ],
            }
        ]
        gaps = _format_coverage_gaps(runs, precondition_gaps)
        assert len(gaps) == 2
        terms = [g["precondition_term"] for g in gaps]
        assert "riesgo" in terms
        assert "corredor" in terms


# ──────────────────────────────────────────────────────────────────────────────
# 4. uat_assertion_evaluator: evaluated_at timestamp
# ──────────────────────────────────────────────────────────────────────────────

class TestAssertionEvaluatorTimestamps:

    def _minimal_runner_output(self, tmp_path) -> Path:
        scenarios = {
            "ok": True,
            "ticket_id": 119,
            "scenarios": [
                {
                    "scenario_id": "P04",
                    "titulo": "Corredor Principal",
                    "oraculos": [
                        {"tipo": "equals", "target": "field_corredor", "valor": "Corredor 1"}
                    ],
                }
            ],
        }
        runner_output = {
            "ok": True,
            "ticket_id": 119,
            "runs": [
                {
                    "scenario_id": "P04",
                    "status": "pass",
                    "spec_file": "P04_corredor.spec.ts",
                }
            ],
        }
        sc_path = tmp_path / "scenarios.json"
        sc_path.write_text(json.dumps(scenarios), encoding="utf-8")
        ro_path = tmp_path / "runner_output.json"
        ro_path.write_text(json.dumps(runner_output), encoding="utf-8")
        return ro_path

    def test_evaluated_at_present_in_evaluation(self, tmp_path):
        from uat_assertion_evaluator import run
        ro_path = self._minimal_runner_output(tmp_path)
        sc_path = tmp_path / "scenarios.json"
        result = run(
            scenarios_path=sc_path,
            runner_output_path=ro_path,
            verbose=False,
        )
        assert result["ok"]
        eval0 = result["evaluations"][0]
        assert "evaluated_at" in eval0, "evaluated_at missing from evaluation"

    def test_evaluated_at_format_is_iso(self, tmp_path):
        from uat_assertion_evaluator import run
        import re
        ro_path = self._minimal_runner_output(tmp_path)
        sc_path = tmp_path / "scenarios.json"
        result = run(
            scenarios_path=sc_path,
            runner_output_path=ro_path,
            verbose=False,
        )
        ts = result["evaluations"][0]["evaluated_at"]
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts), f"Bad ISO format: {ts}"
