"""
tests/unit/test_navigation_strategy_resolver.py — Unit tests for navigation strategy resolver.

Covers:
  - test_navigation_strategy_required_for_every_scenario (via INVALID_DIRECT_NAV)
  - test_frm_detalle_clie_deeplink_contract_requires_clcod
  - test_uat_human_rejects_deeplink_strategy
  - test_smoke_deeplink_allows_deeplink_strategy
  - test_navigation_resolver_returns_human_path_for_uat
  - test_navigation_resolver_returns_deeplink_for_smoke
  - test_navigation_resolver_blocks_missing_clcod
  - test_nav_contract_missing_blocks_human_lane
  - test_nav_contract_missing_allows_non_human_lane
  - test_direct_entry_allowed_screen_uses_direct
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

# Add parent directory to path so we can import the module
_AGENT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_AGENT_DIR))

from navigation_strategy_resolver import (
    resolve_navigation_strategy,
    _load_contracts,
    get_screen_contract,
)

_CONTRACTS_PATH = _AGENT_DIR / "navigation_contracts.yml"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve(
    screen: str,
    lane: str = "uat_human",
    data: dict = None,
    allow_override: bool = False,
) -> dict:
    return resolve_navigation_strategy(
        ticket_id=120,
        scenario_id="TEST",
        target_screen=screen,
        lane=lane,
        available_data=data or {},
        contracts_path=_CONTRACTS_PATH,
        allow_deeplink_override=allow_override,
    )


# ── Contract loading tests ─────────────────────────────────────────────────────

def test_contracts_file_exists():
    """navigation_contracts.yml must exist in the agent directory."""
    assert _CONTRACTS_PATH.is_file(), (
        f"navigation_contracts.yml not found at {_CONTRACTS_PATH}"
    )


def test_frm_detalle_clie_contract_loaded():
    """FrmDetalleClie.aspx must have a contract with deeplink_allowed=True."""
    contracts = _load_contracts(_CONTRACTS_PATH)
    contract = get_screen_contract("FrmDetalleClie.aspx", contracts)
    assert contract is not None, "FrmDetalleClie.aspx must have a navigation contract"
    assert contract.get("deeplink_allowed") is True
    assert contract.get("direct_entry_allowed") is False
    assert contract.get("human_path_required_for_uat") is True


def test_frm_busqueda_contract_direct_entry():
    """FrmBusqueda.aspx should allow direct_entry (it's an entrypoint/list screen)."""
    contracts = _load_contracts(_CONTRACTS_PATH)
    contract = get_screen_contract("FrmBusqueda.aspx", contracts)
    assert contract is not None
    assert contract.get("direct_entry_allowed") is True


def test_frm_detalle_clie_deeplink_contract_requires_clcod():
    """FrmDetalleClie.aspx deeplink contract must require CLCOD param."""
    contracts = _load_contracts(_CONTRACTS_PATH)
    contract = get_screen_contract("FrmDetalleClie.aspx", contracts)
    assert contract is not None
    deeplink_cfg = contract.get("deeplink", {})
    assert "CLCOD" in deeplink_cfg.get("required_params", []), (
        "FrmDetalleClie.aspx deeplink must require CLCOD param"
    )
    assert "uat_human" in deeplink_cfg.get("forbidden_lanes", []), (
        "FrmDetalleClie.aspx deeplink must forbid uat_human lane"
    )
    assert "smoke_deeplink" in deeplink_cfg.get("allowed_lanes", []), (
        "FrmDetalleClie.aspx deeplink must allow smoke_deeplink lane"
    )


# ── Navigation strategy resolution tests ──────────────────────────────────────

def test_uat_human_rejects_deeplink_strategy():
    """uat_human lane must NOT resolve to deeplink for FrmDetalleClie.aspx."""
    result = _resolve("FrmDetalleClie.aspx", lane="uat_human", data={"CLCOD": "12345"})
    assert result["decision"] == "ALLOW_GENERATION"
    assert result["strategy"] == "human_path", (
        "uat_human must use human_path, not deeplink"
    )
    assert result.get("deeplink_rejected_reason") == "lane_requires_human_simulation"


def test_smoke_deeplink_allows_deeplink_strategy():
    """smoke_deeplink lane must resolve to deeplink for FrmDetalleClie.aspx."""
    result = _resolve("FrmDetalleClie.aspx", lane="smoke_deeplink", data={"CLCOD": "12345"})
    assert result["decision"] == "ALLOW_GENERATION"
    assert result["strategy"] == "deeplink", (
        "smoke_deeplink lane must use deeplink for FrmDetalleClie.aspx"
    )
    assert "12345" in result.get("url", ""), "Deeplink URL must contain CLCOD value"


def test_navigation_resolver_returns_human_path_for_uat():
    """Full-UAT lane resolves to human_path with path_id open_from_busqueda."""
    result = _resolve("FrmDetalleClie.aspx", lane="uat_human", data={"CLCOD": "99999"})
    assert result["decision"] == "ALLOW_GENERATION"
    assert result["strategy"] == "human_path"
    assert result.get("path_id") == "open_from_busqueda"
    assert result.get("entrypoint") == "FrmBusqueda.aspx"


def test_navigation_resolver_returns_deeplink_for_smoke():
    """smoke_deeplink lane resolves to deeplink with correct URL for FrmDetalleClie.aspx."""
    result = _resolve("FrmDetalleClie.aspx", lane="smoke_deeplink", data={"CLCOD": "12345"})
    assert result["decision"] == "ALLOW_GENERATION"
    assert result["strategy"] == "deeplink"
    url = result.get("url", "")
    assert "FrmDetalleClie.aspx" in url
    assert "clcod" in url.lower() or "12345" in url


def test_navigation_resolver_blocks_missing_clcod_human():
    """uat_human lane without CLCOD must be BLOCKED / DATA / NAVIGATION_DATA_MISSING."""
    result = _resolve("FrmDetalleClie.aspx", lane="uat_human", data={})
    assert result["decision"] == "BLOCKED"
    assert result["category"] == "DATA"
    assert result["reason"] == "NAVIGATION_DATA_MISSING"
    assert "CLCOD" in result.get("missing_data", [])


def test_navigation_resolver_blocks_missing_clcod_deeplink():
    """smoke_deeplink lane without CLCOD must be BLOCKED / DATA / DEEPLINK_PARAM_MISSING."""
    result = _resolve("FrmDetalleClie.aspx", lane="smoke_deeplink", data={})
    assert result["decision"] == "BLOCKED"
    assert result["category"] == "DATA"
    assert result["reason"] == "DEEPLINK_PARAM_MISSING"


def test_nav_contract_missing_blocks_human_lane():
    """Human lane for unknown screen must be BLOCKED / NAV / NAV_CONTRACT_MISSING."""
    result = _resolve("FrmUnknownScreen.aspx", lane="uat_human", data={})
    assert result["decision"] == "BLOCKED"
    assert result["category"] == "NAV"
    assert result["reason"] == "NAV_CONTRACT_MISSING"


def test_nav_contract_missing_allows_non_human_lane():
    """Non-human lane for unknown screen gets direct_entry fallback (with warning)."""
    result = _resolve("FrmUnknownScreen.aspx", lane="diagnostic", data={})
    # Should be ALLOW_GENERATION with direct_entry strategy and a warning
    assert result["decision"] == "ALLOW_GENERATION"
    assert result["strategy"] == "direct_entry"


def test_direct_entry_allowed_screen_resolves_direct_entry():
    """FrmBusqueda.aspx in any lane resolves to direct_entry (it's an entrypoint)."""
    result = _resolve("FrmBusqueda.aspx", lane="smoke_deeplink", data={})
    assert result["decision"] == "ALLOW_GENERATION"
    assert result["strategy"] == "direct_entry"


def test_frm_detalle_clie_direct_entry_blocked_any_human_lane():
    """FrmDetalleClie.aspx in uat_human without nav data is DATA/NAVIGATION_DATA_MISSING."""
    result = _resolve("FrmDetalleClie.aspx", lane="full-uat", data={})
    assert result["decision"] == "BLOCKED"
    assert result["category"] == "DATA"


def test_diagnostic_lane_allows_deeplink_with_clcod():
    """diagnostic lane allows deeplink for FrmDetalleClie.aspx."""
    result = _resolve("FrmDetalleClie.aspx", lane="diagnostic", data={"CLCOD": "99999"})
    assert result["decision"] == "ALLOW_GENERATION"
    assert result["strategy"] == "deeplink"


def test_forensic_rerun_lane_allows_deeplink_with_clcod():
    """forensic_rerun lane allows deeplink for FrmDetalleClie.aspx."""
    result = _resolve("FrmDetalleClie.aspx", lane="forensic_rerun", data={"CLCOD": "12345"})
    assert result["decision"] == "ALLOW_GENERATION"
    assert result["strategy"] == "deeplink"


def test_uat_human_with_override_allows_deeplink():
    """With allow_deeplink_override=True, even uat_human can use deeplink."""
    result = _resolve(
        "FrmDetalleClie.aspx", lane="uat_human",
        data={"CLCOD": "12345"}, allow_override=True,
    )
    assert result["decision"] == "ALLOW_GENERATION"
    assert result["strategy"] == "deeplink"


def test_human_path_has_required_assertions():
    """human_path result must include required_assertions for post-nav validation."""
    result = _resolve("FrmDetalleClie.aspx", lane="uat_human", data={"CLCOD": "12345"})
    assert result["decision"] == "ALLOW_GENERATION"
    assertions = result.get("required_assertions", [])
    assert len(assertions) > 0, "human_path must declare required_assertions"
    assert "detalle_cliente_visible" in assertions or "selected_client_loaded" in assertions


def test_deeplink_has_required_context_assertions():
    """deeplink result must include required_context_assertions."""
    result = _resolve("FrmDetalleClie.aspx", lane="smoke_deeplink", data={"CLCOD": "12345"})
    assert result["decision"] == "ALLOW_GENERATION"
    assertions = result.get("required_context_assertions", [])
    assert len(assertions) > 0, "deeplink must declare required_context_assertions"
