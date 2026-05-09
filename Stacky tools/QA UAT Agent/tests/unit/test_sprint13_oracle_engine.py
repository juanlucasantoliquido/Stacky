"""
tests/unit/test_sprint13_oracle_engine.py — Sprint 13 tests.

Tests:
  oracle_engine.py
    1.  test_evaluate_no_scenarios_no_contracts_returns_ok
    2.  test_evaluate_scenario_no_contract_no_oracle
    3.  test_evaluate_p0_scenario_no_contract_is_blocking
    4.  test_evaluate_non_p0_no_contract_not_blocking
    5.  test_evaluate_ui_oracle_pass_on_matching_assertion
    6.  test_evaluate_ui_oracle_fail_on_non_matching
    7.  test_evaluate_skips_unimplemented_oracle_types
    8.  test_evaluate_writes_oracle_result_artifact
    9.  test_evaluate_result_to_dict_has_schema_version
    10. test_load_oracle_contracts_empty_dir_returns_empty
    11. test_load_oracle_contracts_loads_valid_contract
    12. test_oracle_result_publish_blocked_when_p0_no_oracle
    13. test_oracle_result_not_blocked_when_non_p0_no_oracle
    14. test_oracle_result_weak_only_verdict_when_no_strong

  weak_assertion_detector.py
    15. test_detect_empty_file_list_returns_ok
    16. test_detect_in_file_no_expect_returns_none_strength
    17. test_detect_in_file_visible_only_returns_weak
    18. test_detect_in_file_to_have_text_returns_strong
    19. test_detect_in_file_to_equal_returns_strong
    20. test_detect_in_file_trivially_true_returns_trivial
    21. test_detect_with_files_writes_evidence_artifact
    22. test_report_to_dict_has_schema_version
    23. test_not_blocked_when_some_strong_tests

  GET /api/qa-uat/oracle-result (Flask)
    24. test_oracle_result_endpoint_missing_params_400
    25. test_oracle_result_endpoint_empty_when_no_files
    26. test_oracle_result_endpoint_returns_artifact_when_exists

  POST /api/qa-uat/oracle-result/evaluate (Flask)
    27. test_oracle_evaluate_endpoint_missing_run_id_400
    28. test_oracle_evaluate_endpoint_missing_ticket_id_400
    29. test_oracle_evaluate_endpoint_returns_ok_result

  GET /api/qa-uat/oracle-result/weak-assertions (Flask)
    30. test_weak_assertions_endpoint_missing_params_400
    31. test_weak_assertions_endpoint_no_report_returns_ok_null

All tests run without DB or network.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(TOOL_DIR))

BACKEND_DIR = TOOL_DIR.parent.parent / "Stacky Agents" / "backend"


# ─────────────────────────────────────────────────────────────────────────────
# oracle_engine — unit tests
# ─────────────────────────────────────────────────────────────────────────────

from oracle_engine import (  # noqa: E402
    evaluate,
    load_oracle_contracts,
    OracleVerdict,
    OracleStrength,
    OracleType,
    OracleContract,
    OracleEvaluationResult,
)


class TestOracleEngine:

    def _make_scenarios_json(self, tmp_path: Path, scenarios: list[dict]) -> Path:
        p = tmp_path / "scenarios.json"
        p.write_text(json.dumps({"scenarios": scenarios}), encoding="utf-8")
        return p

    def _make_oracle_contract_file(self, dir_path: Path, contracts: list[dict]) -> Path:
        p = dir_path / "oracle_contract_test.json"
        p.write_text(json.dumps(contracts), encoding="utf-8")
        return p

    def test_evaluate_no_scenarios_no_contracts_returns_ok(self, tmp_path):
        """evaluate with no scenarios and no contracts → ok=True, total=0"""
        result = evaluate(
            scenarios_path=None,
            runner_output_path=None,
            oracle_contracts_dir=None,
            evidence_dir=tmp_path,
            run_id="run-1",
            ticket_id=1,
        )
        assert isinstance(result, OracleEvaluationResult)
        assert result.ok is True
        assert result.total_scenarios == 0
        assert result.publish_blocked is False

    def test_evaluate_scenario_no_contract_no_oracle(self, tmp_path):
        """scenario without contract → oracle_verdict=NO_ORACLE"""
        scenarios_path = self._make_scenarios_json(tmp_path, [
            {"scenario_id": "SC-001", "priority": 1},
        ])
        result = evaluate(
            scenarios_path=scenarios_path,
            runner_output_path=None,
            oracle_contracts_dir=None,
            evidence_dir=tmp_path,
            run_id="run-1",
            ticket_id=1,
        )
        assert result.total_scenarios == 1
        assert result.no_oracle_count == 1
        sc = result.scenario_results[0]
        assert sc.oracle_verdict == OracleVerdict.NO_ORACLE

    def test_evaluate_p0_scenario_no_contract_is_blocking(self, tmp_path):
        """P0 scenario without contract → blocking=True, publish_blocked=True"""
        scenarios_path = self._make_scenarios_json(tmp_path, [
            {"scenario_id": "SC-P0", "priority": 0},  # is_p0 = True
        ])
        result = evaluate(
            scenarios_path=scenarios_path,
            runner_output_path=None,
            oracle_contracts_dir=None,
            evidence_dir=tmp_path,
            run_id="run-p0",
            ticket_id=1,
        )
        assert result.p0_blocked_count == 1
        assert result.publish_blocked is True
        assert result.ok is False
        sc = result.scenario_results[0]
        assert sc.blocking is True
        assert sc.is_p0 is True

    def test_evaluate_non_p0_no_contract_not_blocking(self, tmp_path):
        """Non-P0 scenario without contract → not blocking, publish not blocked"""
        scenarios_path = self._make_scenarios_json(tmp_path, [
            {"scenario_id": "SC-P1", "priority": 1},
        ])
        result = evaluate(
            scenarios_path=scenarios_path,
            runner_output_path=None,
            oracle_contracts_dir=None,
            evidence_dir=tmp_path,
            run_id="run-np0",
            ticket_id=1,
        )
        assert result.publish_blocked is False
        assert result.p0_blocked_count == 0
        sc = result.scenario_results[0]
        assert sc.blocking is False

    def test_evaluate_ui_oracle_pass_on_matching_assertion(self, tmp_path):
        """UI oracle with count_gt assertion → PASS when actual matches"""
        contracts_dir = tmp_path / "oracle_contracts"
        contracts_dir.mkdir()
        self._make_oracle_contract_file(contracts_dir, [{
            "oracle_id": "OR-001",
            "scenario_id": "SC-001",
            "oracle_type": "UI",
            "strength": "P0",
            "description": "Grid has rows",
            "check": {
                "locator": "table.data tbody tr",
                "assertion": "count_gt",
                "expected": 0,
            },
        }])
        scenarios_path = self._make_scenarios_json(tmp_path, [
            {"scenario_id": "SC-001", "priority": 0},
        ])
        runner_output = tmp_path / "runner_output.json"
        runner_output.write_text(json.dumps({
            "events": [
                {"type": "assertion", "scenario_id": "SC-001",
                 "locator": "table.data tbody tr", "actual": 5},
            ]
        }), encoding="utf-8")

        result = evaluate(
            scenarios_path=scenarios_path,
            runner_output_path=runner_output,
            oracle_contracts_dir=contracts_dir,
            evidence_dir=tmp_path,
            run_id="run-ui",
            ticket_id=1,
        )
        assert result.pass_count == 1
        sc = result.scenario_results[0]
        assert sc.oracle_verdict == OracleVerdict.PASS
        assert sc.pass_count == 1

    def test_evaluate_ui_oracle_fail_on_non_matching(self, tmp_path):
        """UI oracle with count_gt → FAIL when actual is 0"""
        contracts_dir = tmp_path / "oracle_contracts"
        contracts_dir.mkdir()
        self._make_oracle_contract_file(contracts_dir, [{
            "oracle_id": "OR-002",
            "scenario_id": "SC-002",
            "oracle_type": "UI",
            "strength": "P0",
            "description": "Grid has rows",
            "check": {
                "locator": "table.data tbody tr",
                "assertion": "count_gt",
                "expected": 0,
            },
        }])
        scenarios_path = self._make_scenarios_json(tmp_path, [
            {"scenario_id": "SC-002", "priority": 0},
        ])
        runner_output = tmp_path / "runner_output.json"
        runner_output.write_text(json.dumps({
            "events": [
                {"type": "assertion", "scenario_id": "SC-002",
                 "locator": "table.data tbody tr", "actual": 0},
            ]
        }), encoding="utf-8")

        result = evaluate(
            scenarios_path=scenarios_path,
            runner_output_path=runner_output,
            oracle_contracts_dir=contracts_dir,
            evidence_dir=tmp_path,
            run_id="run-fail",
            ticket_id=1,
        )
        assert result.fail_count == 1
        sc = result.scenario_results[0]
        assert sc.oracle_verdict == OracleVerdict.FAIL

    def test_evaluate_skips_unimplemented_oracle_types(self, tmp_path):
        """DB oracle type (not implemented) → SKIP verdict"""
        contracts_dir = tmp_path / "oracle_contracts"
        contracts_dir.mkdir()
        self._make_oracle_contract_file(contracts_dir, [{
            "oracle_id": "OR-DB-001",
            "scenario_id": "SC-DB",
            "oracle_type": "DB",
            "strength": "P1",
            "description": "Row exists",
            "check": {"sql": "SELECT 1"},
        }])
        scenarios_path = self._make_scenarios_json(tmp_path, [
            {"scenario_id": "SC-DB", "priority": 1},
        ])
        result = evaluate(
            scenarios_path=scenarios_path,
            runner_output_path=None,
            oracle_contracts_dir=contracts_dir,
            evidence_dir=tmp_path,
            run_id="run-db",
            ticket_id=1,
        )
        sc = result.scenario_results[0]
        # DB oracle is SKIP since not implemented
        assert sc.oracle_verdict in (OracleVerdict.SKIP, OracleVerdict.WEAK_ONLY, OracleVerdict.NO_ORACLE)

    def test_evaluate_writes_oracle_result_artifact(self, tmp_path):
        """evaluate → oracle_result.json written in evidence_dir/ticket_id/run_id/"""
        result = evaluate(
            scenarios_path=None,
            runner_output_path=None,
            oracle_contracts_dir=None,
            evidence_dir=tmp_path,
            run_id="run-art",
            ticket_id=99,
        )
        artifact = tmp_path / "99" / "run-art" / "oracle_result.json"
        assert artifact.is_file()
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["run_id"] == "run-art"
        assert data["ticket_id"] == 99
        assert "schema_version" in data

    def test_evaluate_result_to_dict_has_schema_version(self, tmp_path):
        """OracleEvaluationResult.to_dict() includes schema_version"""
        result = evaluate(
            scenarios_path=None,
            runner_output_path=None,
            oracle_contracts_dir=None,
            evidence_dir=tmp_path,
            run_id="run-dict",
            ticket_id=1,
        )
        d = result.to_dict()
        assert "schema_version" in d
        assert d["schema_version"].startswith("oracle_result/")

    def test_load_oracle_contracts_empty_dir_returns_empty(self, tmp_path):
        """load_oracle_contracts on empty dir → {}"""
        result = load_oracle_contracts(tmp_path)
        assert result == {}

    def test_load_oracle_contracts_loads_valid_contract(self, tmp_path):
        """load_oracle_contracts loads a valid contract file"""
        (tmp_path / "oracle_contract_rf007.json").write_text(json.dumps([{
            "oracle_id": "OR-RF007-001",
            "scenario_id": "RF-007-CA-01",
            "oracle_type": "UI",
            "strength": "P0",
            "description": "Grid has rows",
            "check": {"locator": "tr", "assertion": "count_gt", "expected": 0},
        }]), encoding="utf-8")
        result = load_oracle_contracts(tmp_path)
        assert "RF-007-CA-01" in result
        contracts = result["RF-007-CA-01"]
        assert len(contracts) == 1
        assert contracts[0].oracle_id == "OR-RF007-001"
        assert contracts[0].strength == "P0"

    def test_oracle_result_publish_blocked_when_p0_no_oracle(self, tmp_path):
        """publish_blocked=True when any P0 scenario has NO_ORACLE"""
        scenarios_path = self._make_scenarios_json(tmp_path, [
            {"scenario_id": "SC-P0-BLOCK", "priority": "P0"},
        ])
        result = evaluate(
            scenarios_path=scenarios_path,
            runner_output_path=None,
            oracle_contracts_dir=None,
            evidence_dir=tmp_path,
            run_id="run-blk",
            ticket_id=1,
        )
        assert result.publish_blocked is True

    def test_oracle_result_not_blocked_when_non_p0_no_oracle(self, tmp_path):
        """publish_blocked=False when only non-P0 scenarios have NO_ORACLE"""
        scenarios_path = self._make_scenarios_json(tmp_path, [
            {"scenario_id": "SC-P2-OK", "priority": 2},
        ])
        result = evaluate(
            scenarios_path=scenarios_path,
            runner_output_path=None,
            oracle_contracts_dir=None,
            evidence_dir=tmp_path,
            run_id="run-ok",
            ticket_id=1,
        )
        assert result.publish_blocked is False

    def test_oracle_result_weak_only_verdict_when_no_strong(self, tmp_path):
        """Scenario with only P2/WEAK oracle contracts → WEAK_ONLY or SKIP verdict"""
        contracts_dir = tmp_path / "oracle_contracts"
        contracts_dir.mkdir()
        self._make_oracle_contract_file(contracts_dir, [{
            "oracle_id": "OR-WEAK",
            "scenario_id": "SC-WEAK",
            "oracle_type": "UI",
            "strength": "P2",  # WEAK
            "description": "Cosmetic check",
            "check": {
                "locator": ".footer",
                "assertion": "visible",
                "expected": True,
            },
        }])
        scenarios_path = self._make_scenarios_json(tmp_path, [
            {"scenario_id": "SC-WEAK", "priority": 1},
        ])
        runner_output = tmp_path / "runner_output.json"
        runner_output.write_text(json.dumps({
            "events": [
                {"type": "assertion", "scenario_id": "SC-WEAK",
                 "locator": ".footer", "actual": True},
            ]
        }), encoding="utf-8")
        result = evaluate(
            scenarios_path=scenarios_path,
            runner_output_path=runner_output,
            oracle_contracts_dir=contracts_dir,
            evidence_dir=tmp_path,
            run_id="run-weak",
            ticket_id=1,
        )
        sc = result.scenario_results[0]
        assert sc.strong_count == 0
        # verdict should be WEAK_ONLY or PASS (P2 oracle can still PASS)
        assert sc.oracle_verdict in (OracleVerdict.WEAK_ONLY, OracleVerdict.PASS)


# ─────────────────────────────────────────────────────────────────────────────
# weak_assertion_detector — unit tests
# ─────────────────────────────────────────────────────────────────────────────

from weak_assertion_detector import (  # noqa: E402
    detect,
    detect_in_file,
    classify_assertion_strength,
    AssertionStrength,
    WeakAssertionReport,
)


class TestWeakAssertionDetector:

    def _make_spec_file(self, tmp_path: Path, name: str, content: str) -> Path:
        p = tmp_path / name
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p

    def test_detect_empty_file_list_returns_ok(self, tmp_path):
        """detect with empty list → ok=True, files_analyzed=0"""
        report = detect(
            spec_files=[],
            evidence_dir=tmp_path,
            run_id="run-1",
            ticket_id=1,
        )
        assert isinstance(report, WeakAssertionReport)
        assert report.ok is True
        assert report.files_analyzed == 0
        assert report.total_tests == 0

    def test_detect_in_file_no_expect_returns_none_strength(self, tmp_path):
        """Test file with no expect() calls → NONE strength"""
        spec = self._make_spec_file(tmp_path, "no_expect.spec.ts", """
            test('opens page', async ({ page }) => {
                await page.goto('/agenda');
                await page.waitForLoadState('networkidle');
            });
        """)
        analysis = detect_in_file(spec)
        assert analysis.total_tests == 1
        assert analysis.no_assertion_tests == 1
        assert analysis.strong_tests == 0
        t = analysis.test_results[0]
        assert t.assertion_strength == AssertionStrength.NONE
        assert t.is_weak is True

    def test_detect_in_file_visible_only_returns_weak(self, tmp_path):
        """Test with only toBeVisible() → WEAK strength"""
        spec = self._make_spec_file(tmp_path, "visible_only.spec.ts", """
            test('grid visible', async ({ page }) => {
                await page.goto('/agenda');
                await expect(page.locator('table')).toBeVisible();
            });
        """)
        analysis = detect_in_file(spec)
        assert analysis.total_tests == 1
        assert analysis.weak_tests == 1
        assert analysis.strong_tests == 0
        t = analysis.test_results[0]
        assert t.assertion_strength == AssertionStrength.WEAK
        assert t.is_weak is True

    def test_detect_in_file_to_have_text_returns_strong(self, tmp_path):
        """Test with toHaveText() → STRONG strength"""
        spec = self._make_spec_file(tmp_path, "strong_text.spec.ts", """
            test('shows obligation name', async ({ page }) => {
                await page.goto('/obligaciones');
                const cell = page.locator('td.nombre').first();
                await expect(cell).toHaveText('Crédito Hipotecario');
            });
        """)
        analysis = detect_in_file(spec)
        assert analysis.total_tests == 1
        assert analysis.strong_tests == 1
        assert analysis.weak_tests == 0
        t = analysis.test_results[0]
        assert t.assertion_strength == AssertionStrength.STRONG
        assert t.is_weak is False

    def test_detect_in_file_to_equal_returns_strong(self, tmp_path):
        """Test with toEqual() → STRONG strength"""
        spec = self._make_spec_file(tmp_path, "strong_equal.spec.ts", """
            test('row count correct', async ({ page }) => {
                await page.goto('/agenda');
                const rows = await page.locator('tbody tr').count();
                expect(rows).toEqual(5);
            });
        """)
        analysis = detect_in_file(spec)
        assert analysis.total_tests == 1
        assert analysis.strong_tests == 1

    def test_detect_in_file_trivially_true_returns_trivial(self, tmp_path):
        """Test with expect(true).toBe(true) → TRIVIAL strength"""
        spec = self._make_spec_file(tmp_path, "trivial.spec.ts", """
            test('always passes', async ({ page }) => {
                await page.goto('/test');
                expect(true).toBe(true);
            });
        """)
        analysis = detect_in_file(spec)
        assert analysis.total_tests == 1
        assert analysis.trivial_tests == 1
        t = analysis.test_results[0]
        assert t.assertion_strength == AssertionStrength.TRIVIAL
        assert t.is_weak is True

    def test_detect_with_files_writes_evidence_artifact(self, tmp_path):
        """detect with spec files → weak_assertion_report.json written"""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        spec = self._make_spec_file(specs_dir, "test.spec.ts", """
            test('no assertions', async ({ page }) => {
                await page.goto('/');
            });
        """)
        report = detect(
            spec_files=[spec],
            evidence_dir=tmp_path,
            run_id="run-art",
            ticket_id=55,
        )
        artifact = tmp_path / "55" / "run-art" / "weak_assertion_report.json"
        assert artifact.is_file()
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["run_id"] == "run-art"
        assert data["ticket_id"] == 55
        assert "schema_version" in data

    def test_report_to_dict_has_schema_version(self, tmp_path):
        """WeakAssertionReport.to_dict() includes schema_version"""
        report = detect(
            spec_files=[],
            evidence_dir=tmp_path,
            run_id="run-dict",
            ticket_id=1,
        )
        d = report.to_dict()
        assert "schema_version" in d
        assert d["schema_version"].startswith("weak_assertion_report/")

    def test_not_blocked_when_some_strong_tests(self, tmp_path):
        """publish_blocked=False when at least one strong test exists"""
        spec_strong = self._make_spec_file(tmp_path, "strong.spec.ts", """
            test('strong assertion', async ({ page }) => {
                await page.goto('/');
                await expect(page.locator('h1')).toHaveText('Agenda');
            });
        """)
        spec_weak = self._make_spec_file(tmp_path, "weak.spec.ts", """
            test('weak assertion', async ({ page }) => {
                await page.goto('/');
                await expect(page.locator('body')).toBeVisible();
            });
        """)
        report = detect(
            spec_files=[spec_strong, spec_weak],
            evidence_dir=tmp_path,
            run_id="run-mix",
            ticket_id=1,
            block_on_no_strong=True,
        )
        # Has one strong test → not blocked
        assert report.strong_tests >= 1
        assert report.publish_blocked is False


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


class TestOracleResultEndpoint:

    def test_oracle_result_endpoint_missing_params_400(self, client):
        c, _ = client
        resp = c.get("/api/qa-uat/oracle-result")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False
        assert "missing_params" in data["error"]

    def test_oracle_result_endpoint_missing_ticket_id_400(self, client):
        c, _ = client
        resp = c.get("/api/qa-uat/oracle-result?run_id=run-1")
        assert resp.status_code == 400

    def test_oracle_result_endpoint_empty_when_no_files(self, client):
        c, tmp = client
        resp = c.get("/api/qa-uat/oracle-result?run_id=run-1&ticket_id=99")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["results"] == []
        assert data["total"] == 0

    def test_oracle_result_endpoint_returns_artifact_when_exists(self, client):
        c, tmp = client
        artifact_dir = tmp / "evidence" / "99" / "run-art"
        artifact_dir.mkdir(parents=True)
        artifact = artifact_dir / "oracle_result.json"
        artifact.write_text(json.dumps({
            "schema_version": "oracle_result/1.0",
            "ok": True,
            "run_id": "run-art",
            "ticket_id": 99,
            "total_scenarios": 1,
            "evaluated_scenarios": 0,
            "pass_count": 0,
            "fail_count": 0,
            "no_oracle_count": 1,
            "weak_only_count": 0,
            "p0_blocked_count": 0,
            "publish_blocked": False,
            "scenario_results": [],
        }), encoding="utf-8")
        resp = c.get("/api/qa-uat/oracle-result?run_id=run-art&ticket_id=99")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["total"] == 1
        assert data["results"][0]["run_id"] == "run-art"


class TestOracleEvaluateEndpoint:

    def test_oracle_evaluate_endpoint_missing_run_id_400(self, client):
        c, _ = client
        resp = c.post(
            "/api/qa-uat/oracle-result/evaluate",
            json={"ticket_id": 99},
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_oracle_evaluate_endpoint_missing_ticket_id_400(self, client):
        c, _ = client
        resp = c.post(
            "/api/qa-uat/oracle-result/evaluate",
            json={"run_id": "run-1"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_oracle_evaluate_endpoint_returns_ok_result(self, client):
        c, tmp = client
        (tmp / "evidence" / "99" / "run-eval").mkdir(parents=True, exist_ok=True)
        resp = c.post(
            "/api/qa-uat/oracle-result/evaluate",
            json={"run_id": "run-eval", "ticket_id": 99},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "result" in data
        assert data["result"]["run_id"] == "run-eval"


class TestWeakAssertionsEndpoint:

    def test_weak_assertions_endpoint_missing_params_400(self, client):
        c, _ = client
        resp = c.get("/api/qa-uat/oracle-result/weak-assertions")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_weak_assertions_endpoint_no_report_returns_ok_null(self, client):
        c, tmp = client
        resp = c.get("/api/qa-uat/oracle-result/weak-assertions?run_id=run-1&ticket_id=99")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["report"] is None
