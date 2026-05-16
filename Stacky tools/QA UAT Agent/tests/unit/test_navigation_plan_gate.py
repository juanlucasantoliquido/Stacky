"""Sprint N5-01 — playwright_test_generator navigation_plan gate.

Covers the three acceptance tests called out in the FIFTH-PART roadmap:

    * tests/unit/test_template_no_direct_goto.py
    * tests/unit/test_generator_blocks_without_nav_plan.py
    * tests/unit/test_generator_allows_direct_entry.py

Bundled into one module because they share the same fixture plumbing
(scenario JSON + ui_map JSON + navigation_contracts.yml in tmp_path).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
# Fase 3: tests that exercise the UI-map fallback path must disable the
# global QA_UAT_REQUIRE_PLAYBOOK gate.
os.environ.setdefault("QA_UAT_REQUIRE_PLAYBOOK", "false")

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_minimal_contracts(path: Path) -> None:
    """Minimal navigation_contracts.yml — only what the gate needs to see."""
    path.write_text(
        """
_meta:
  version: "1.0"

FrmBusqueda.aspx:
  screen_type: list
  direct_entry_allowed: true
  deeplink_allowed: false
  human_path_required_for_uat: false

FrmDetalleClie.aspx:
  screen_type: detail
  direct_entry_allowed: false
  deeplink_allowed: true
  human_path_required_for_uat: true
""".strip(),
        encoding="utf-8",
    )


def _write_ui_map(path: Path, screen: str) -> None:
    """Tiny ui_map covering the click target used by the scenarios below."""
    path.write_text(
        json.dumps({
            "screen": screen,
            "elements": [
                {
                    "alias_semantic": "btn_buscar",
                    "selector_recommended": "#c_btnBuscar",
                    "fallback_selectors": ["#c_btnBuscar"],
                },
            ],
        }),
        encoding="utf-8",
    )


def _write_scenarios(path: Path, ticket_id: int, scenario_id: str, screen: str) -> None:
    path.write_text(
        json.dumps({
            "ok": True,
            "ticket_id": ticket_id,
            "scenarios": [
                {
                    "scenario_id": scenario_id,
                    "ticket_id": ticket_id,
                    "pantalla": screen,
                    "titulo": f"Sprint N5-01 fixture {scenario_id}",
                    "precondiciones": [],
                    "pasos": [
                        {"accion": "click", "target": "btn_buscar", "valor": None},
                    ],
                    "oraculos": [],
                    "datos_requeridos": [],
                },
            ],
        }),
        encoding="utf-8",
    )


def _build_minimal_nav_plan(ticket_id: int, scenario_id: str, screen: str) -> dict:
    """Synthesize a NavigationPlan good enough for the template to render."""
    return {
        "plan_version": "1.0",
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "target_screen": screen,
        "lane": "uat_human",
        "strategy": "human_path",
        "path_id": "open_from_busqueda",
        "entrypoint": "FrmBusqueda.aspx",
        "steps": [
            {
                "step_index": 1,
                "method": "goto_direct",
                "description": "Navigate to FrmBusqueda.aspx",
                "target_url": "FrmBusqueda.aspx",
                "wait_url_contains": "FrmBusqueda",
                "timeout_ms": 20000,
                "retries": 2,
            },
        ],
        "arrival_assertions": [
            {
                "assertion_id": "no_aspnet_error",
                "type": "no_aspnet_error",
                "description": "No YSOD",
                "severity": "hard",
                "category_on_fail": "ENV",
            },
        ],
        "session_requirements": {
            "require_valid_storagestate": True,
            "storagestate_max_age_minutes": 120,
        },
    }


# ── 1. test_template_no_direct_goto ──────────────────────────────────────────

def test_template_no_direct_goto_when_nav_plan_provided(tmp_path):
    """Acceptance: with a NavigationPlan, the rendered template does NOT
    contain `page.goto(${BASE_URL}FrmDetalleClie.aspx)` in setup."""
    import playwright_test_generator as gen

    ticket_id = 120
    sid = "P02"
    screen = "FrmDetalleClie.aspx"

    contracts = tmp_path / "navigation_contracts.yml"
    _write_minimal_contracts(contracts)

    scenarios = tmp_path / "scenarios.json"
    _write_scenarios(scenarios, ticket_id, sid, screen)

    ui_maps = tmp_path / "ui_maps"
    ui_maps.mkdir()
    _write_ui_map(ui_maps / f"{screen}.json", screen)

    plans = {sid: _build_minimal_nav_plan(ticket_id, sid, screen)}

    out = tmp_path / "tests"
    result = gen.run(
        scenarios_path=scenarios,
        ui_maps_dir=ui_maps,
        out_dir=out,
        navigation_plans=plans,
        navigation_contracts_path=contracts,
    )

    assert result["ok"] is True, result
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 1, result

    spec_text = Path(generated[0]["path"]).read_text(encoding="utf-8")
    # AP-01/AP-02: no raw goto to a session screen.
    assert "page.goto(`${BASE_URL}FrmDetalleClie.aspx`" not in spec_text
    # The new helper IS wired into the spec.
    assert "executeNavigationPlan(page, NAVIGATION_PLAN" in spec_text
    assert "verifyStorageStateValid(120)" in spec_text
    # The NavigationPlan constant is encoded inline.
    assert "const NAVIGATION_PLAN" in spec_text
    assert '"strategy"' in spec_text and "human_path" in spec_text


# ── 2. test_generator_blocks_without_nav_plan ────────────────────────────────

def test_generator_blocks_without_nav_plan_for_session_screen(tmp_path):
    """Acceptance: when a scenario targets a screen with
    direct_entry_allowed: false and no NavigationPlan is supplied, the
    generator must BLOCK with reason=NAVIGATION_PLAN_MISSING."""
    import playwright_test_generator as gen

    ticket_id = 120
    sid = "P02"
    screen = "FrmDetalleClie.aspx"

    contracts = tmp_path / "navigation_contracts.yml"
    _write_minimal_contracts(contracts)

    scenarios = tmp_path / "scenarios.json"
    _write_scenarios(scenarios, ticket_id, sid, screen)

    ui_maps = tmp_path / "ui_maps"
    ui_maps.mkdir()
    _write_ui_map(ui_maps / f"{screen}.json", screen)

    out = tmp_path / "tests"
    result = gen.run(
        scenarios_path=scenarios,
        ui_maps_dir=ui_maps,
        out_dir=out,
        # Note: no navigation_plans passed.
        navigation_contracts_path=contracts,
    )

    assert result["ok"] is True
    assert result["generated"] == 0
    assert result["blocked"] >= 1
    blocked = [r for r in result["results"] if r["status"] == "blocked"]
    assert any(r["reason"] == "NAVIGATION_PLAN_MISSING" for r in blocked), blocked
    block = next(r for r in blocked if r["reason"] == "NAVIGATION_PLAN_MISSING")
    assert block.get("category") == "GEN"
    assert block.get("screen") == screen
    assert "human_action_required" in block


# ── 3. test_generator_allows_direct_entry ────────────────────────────────────

def test_generator_allows_direct_entry_when_screen_permits(tmp_path):
    """Acceptance: for a screen with direct_entry_allowed: true and no plan,
    the legacy goto-based path is still emitted (backwards-compat)."""
    import playwright_test_generator as gen

    ticket_id = 70
    sid = "P01"
    screen = "FrmBusqueda.aspx"

    contracts = tmp_path / "navigation_contracts.yml"
    _write_minimal_contracts(contracts)

    scenarios = tmp_path / "scenarios.json"
    _write_scenarios(scenarios, ticket_id, sid, screen)

    ui_maps = tmp_path / "ui_maps"
    ui_maps.mkdir()
    _write_ui_map(ui_maps / f"{screen}.json", screen)

    out = tmp_path / "tests"
    result = gen.run(
        scenarios_path=scenarios,
        ui_maps_dir=ui_maps,
        out_dir=out,
        navigation_contracts_path=contracts,
    )

    assert result["ok"] is True, result
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 1, result

    spec_text = Path(generated[0]["path"]).read_text(encoding="utf-8")
    # Direct entry screens keep the legacy goto.
    assert "page.goto(`${BASE_URL}${TARGET_SCREEN}`" in spec_text
    # And do NOT contain the new helper imports.
    assert "executeNavigationPlan" not in spec_text
    assert "verifyStorageStateValid" not in spec_text
    assert "const NAVIGATION_PLAN" not in spec_text
