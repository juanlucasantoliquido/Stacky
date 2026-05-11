"""
tests/regression/test_ticket_120_navigation.py — Regression tests for ticket 120
navigation failures.

Validates that:
1. Direct goto to FrmDetalleClie.aspx (when login succeeded) is classified as
   NAV/INVALID_DIRECT_NAVIGATION (not ENV/PAGE_LOAD_FAILED).
2. Deeplink via FrmDetalleClie.aspx?clcod=12345 in smoke_deeplink lane is ALLOW_GENERATION.
3. Human path navigation in uat_human lane is ALLOW_GENERATION with open_from_busqueda.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_AGENT_DIR = Path(__file__).resolve().parent.parent.parent
_FIXTURES_DIR = _AGENT_DIR / "fixtures" / "ticket_120"
sys.path.insert(0, str(_AGENT_DIR))

from navigation_strategy_resolver import resolve_navigation_strategy
from failure_triage import _determine_category_reason


# ── Fixture loader ────────────────────────────────────────────────────────────

def _load_fixture(fixture_id: str) -> dict:
    fixture_path = _FIXTURES_DIR / fixture_id / "fixture.json"
    assert fixture_path.is_file(), f"Fixture not found: {fixture_path}"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


# ── Regression test: direct_goto_frm_detalle_crashes_iis ──────────────────────

class TestDirectGotoFrmDetalleRegressionFixture:
    """Ticket 120: login OK + direct goto + crash → should be NAV not ENV."""

    def test_fixture_exists(self):
        fixture = _load_fixture("direct_goto_frm_detalle_crashes_iis")
        assert fixture["_meta"]["ticket_id"] == 120

    def test_triage_classifies_as_nav_not_env(self):
        """
        REGRESSION: ticket 120 was previously diagnosed as ENV/PAGE_LOAD_FAILED.
        With causal chain analysis, it must be NAV/INVALID_DIRECT_NAVIGATION.
        """
        fixture = _load_fixture("direct_goto_frm_detalle_crashes_iis")
        inp = fixture["input"]
        expected = fixture["expected"]

        category, reason, confidence, evidence = _determine_category_reason(
            result_json=inp["result_json"],
            execution_log=inp["execution_log"],
            runner_classification=inp.get("runner_classification"),
            verdict=inp["result_json"]["verdict"],
        )

        assert category == expected["primary_category"], (
            f"REGRESSION FAIL: expected category={expected['primary_category']} "
            f"but got {category}. Evidence: {evidence}"
        )
        assert reason == expected["primary_reason"], (
            f"REGRESSION FAIL: expected reason={expected['primary_reason']} "
            f"but got {reason}. Evidence: {evidence}"
        )

    def test_triage_evidence_documents_causal_chain(self):
        """Triage evidence must explicitly mention the causal chain."""
        fixture = _load_fixture("direct_goto_frm_detalle_crashes_iis")
        inp = fixture["input"]

        _, _, _, evidence = _determine_category_reason(
            result_json=inp["result_json"],
            execution_log=inp["execution_log"],
            runner_classification=inp.get("runner_classification"),
            verdict=inp["result_json"]["verdict"],
        )

        causal_evidence = [e for e in evidence if "CAUSAL" in e.upper() or "login" in e.lower()]
        assert len(causal_evidence) > 0, (
            f"Evidence must document causal chain reasoning. Got evidence: {evidence}"
        )

    def test_triage_rerun_not_recommended(self):
        """Navigation structural failures must NOT recommend rerun."""
        from failure_triage import _should_rerun
        assert not _should_rerun(
            verdict="BLOCKED",
            category="NAV",
            reason="INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN",
        )


# ── Regression test: deeplink_valid ──────────────────────────────────────────

class TestDeeplinkValidRegressionFixture:
    """Ticket 120: deeplink via smoke_deeplink lane should resolve to ALLOW_GENERATION."""

    def test_fixture_exists(self):
        fixture = _load_fixture("deeplink_valid")
        assert fixture["_meta"]["ticket_id"] == 120

    def test_deeplink_resolves_to_allow_generation(self):
        fixture = _load_fixture("deeplink_valid")
        inp = fixture["input"]
        expected = fixture["expected"]

        result = resolve_navigation_strategy(
            ticket_id=120,
            scenario_id=inp["scenario_id"],
            target_screen=inp["target_screen"],
            lane=inp["lane"],
            available_data=inp["available_data"],
            contracts_path=_AGENT_DIR / "navigation_contracts.yml",
        )

        assert result["decision"] == expected["decision"], (
            f"Expected {expected['decision']} but got {result['decision']}. "
            f"Full result: {result}"
        )
        assert result.get("strategy") == expected["navigation_strategy"], (
            f"Expected strategy={expected['navigation_strategy']} but got {result.get('strategy')}"
        )

    def test_deeplink_url_contains_clcod(self):
        fixture = _load_fixture("deeplink_valid")
        inp = fixture["input"]

        result = resolve_navigation_strategy(
            ticket_id=120,
            scenario_id=inp["scenario_id"],
            target_screen=inp["target_screen"],
            lane=inp["lane"],
            available_data=inp["available_data"],
            contracts_path=_AGENT_DIR / "navigation_contracts.yml",
        )

        assert result["decision"] == "ALLOW_GENERATION"
        url = result.get("url", "")
        assert "12345" in url, f"Deeplink URL must contain CLCOD value '12345'. Got: {url}"
        assert "FrmDetalleClie.aspx" in url, f"URL must reference FrmDetalleClie.aspx. Got: {url}"

    def test_direct_goto_not_used_in_deeplink(self):
        fixture = _load_fixture("deeplink_valid")
        inp = fixture["input"]

        result = resolve_navigation_strategy(
            ticket_id=120,
            scenario_id=inp["scenario_id"],
            target_screen=inp["target_screen"],
            lane=inp["lane"],
            available_data=inp["available_data"],
            contracts_path=_AGENT_DIR / "navigation_contracts.yml",
        )

        # direct_goto is false even for deeplink (deeplink != unguarded direct goto)
        assert result.get("direct_goto_allowed") is False, (
            "deeplink strategy must NOT set direct_goto_allowed=True"
        )


# ── Regression test: uat_human_valid ─────────────────────────────────────────

class TestUatHumanValidRegressionFixture:
    """Ticket 120: uat_human lane with CLCOD should resolve to human_path."""

    def test_fixture_exists(self):
        fixture = _load_fixture("uat_human_valid")
        assert fixture["_meta"]["ticket_id"] == 120

    def test_uat_human_resolves_to_human_path(self):
        fixture = _load_fixture("uat_human_valid")
        inp = fixture["input"]
        expected = fixture["expected"]

        result = resolve_navigation_strategy(
            ticket_id=120,
            scenario_id=inp["scenario_id"],
            target_screen=inp["target_screen"],
            lane=inp["lane"],
            available_data=inp["available_data"],
            contracts_path=_AGENT_DIR / "navigation_contracts.yml",
        )

        assert result["decision"] == expected["decision"], (
            f"Expected {expected['decision']} but got {result['decision']}. Result: {result}"
        )
        assert result.get("strategy") == expected["navigation_strategy"], (
            f"Expected strategy={expected['navigation_strategy']} but got {result.get('strategy')}"
        )
        assert result.get("path_id") == expected["path_id"], (
            f"Expected path_id={expected['path_id']} but got {result.get('path_id')}"
        )

    def test_uat_human_uses_frm_busqueda_entrypoint(self):
        fixture = _load_fixture("uat_human_valid")
        inp = fixture["input"]
        expected = fixture["expected"]

        result = resolve_navigation_strategy(
            ticket_id=120,
            scenario_id=inp["scenario_id"],
            target_screen=inp["target_screen"],
            lane=inp["lane"],
            available_data=inp["available_data"],
            contracts_path=_AGENT_DIR / "navigation_contracts.yml",
        )

        assert result.get("entrypoint") == expected["entrypoint"], (
            f"Expected entrypoint=FrmBusqueda.aspx but got {result.get('entrypoint')}"
        )

    def test_uat_human_rejects_deeplink(self):
        fixture = _load_fixture("uat_human_valid")
        inp = fixture["input"]

        result = resolve_navigation_strategy(
            ticket_id=120,
            scenario_id=inp["scenario_id"],
            target_screen=inp["target_screen"],
            lane=inp["lane"],
            available_data=inp["available_data"],
            contracts_path=_AGENT_DIR / "navigation_contracts.yml",
        )

        assert result.get("deeplink_rejected_reason") == "lane_requires_human_simulation", (
            f"deeplink_rejected_reason must be 'lane_requires_human_simulation'. "
            f"Got: {result.get('deeplink_rejected_reason')}"
        )
        assert result.get("direct_goto_allowed") is False
