"""Sprint N5-05 — End-to-end navigation pipeline integration tests.

Three mandatory tests from roadmap §5.5.4:

  * test_pipeline_detalleclie_human_path
    — Full pipeline for ticket 120/P02 against FrmDetalleClie.aspx.
      Verifies the generated spec contains executeNavigationPlan and does
      NOT contain a raw goto to FrmDetalleClie.aspx in setup.

  * test_pipeline_detalleclie_no_clcod
    — Without CLCOD, the pipeline returns BLOCKED DATA NAVIGATION_DATA_MISSING.

  * test_pipeline_busqueda_direct
    — FrmBusqueda.aspx gets a goto_direct plan and a valid spec.

Tests are self-contained — they spin up scratch fixtures (scenarios, ui_maps,
navigation_contracts.yml) under tmp_path so they never read or mutate the
live cache. Required real artifacts (the N5-04 playbooks) are referenced
through the production playbooks dir to verify true end-to-end routing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_REQUIRE_PLAYBOOK", "false")

REAL_PLAYBOOKS = ROOT / "cache" / "playbooks"


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _contracts_yaml() -> str:
    return """
_meta:
  version: "1.0"

FrmLogin.aspx:
  screen_type: entrypoint
  direct_entry_allowed: true
  deeplink_allowed: false
  human_path_required_for_uat: false

FrmBusqueda.aspx:
  screen_type: list
  direct_entry_allowed: true
  deeplink_allowed: false
  human_path_required_for_uat: false
  human_paths:
    open_direct:
      entrypoint: FrmBusqueda.aspx
      steps:
        - "Navigate directly to FrmBusqueda.aspx"
      required_data: []

FrmDetalleClie.aspx:
  screen_type: detail
  direct_entry_allowed: false
  deeplink_allowed: true
  human_path_required_for_uat: true
  deeplink:
    pattern: "FrmDetalleClie.aspx?clcod={CLCOD}"
    required_params: [CLCOD]
    forbidden_lanes: [uat_human, uat_human_simulation]
  human_paths:
    open_from_busqueda:
      entrypoint: FrmBusqueda.aspx
      steps:
        - "Navigate to FrmBusqueda.aspx"
        - "Fill CLCOD"
        - "Click Buscar"
        - "Click row"
      required_data: [CLCOD]
""".strip()


def _scenario_detalleclie(ticket_id: int = 120, sid: str = "P02") -> dict:
    return {
        "scenario_id": sid,
        "ticket_id": ticket_id,
        "pantalla": "FrmDetalleClie.aspx",
        "titulo": "Abrir detalle de cliente y validar datos",
        "precondiciones": ["Login OK"],
        "pasos": [
            {"accion": "click", "target": "btn_buscar", "valor": None},
        ],
        "oraculos": [],
        "datos_requeridos": [],
    }


def _scenario_busqueda(ticket_id: int = 200, sid: str = "S01") -> dict:
    return {
        "scenario_id": sid,
        "ticket_id": ticket_id,
        "pantalla": "FrmBusqueda.aspx",
        "titulo": "smoke abrir busqueda directa",
        "precondiciones": [],
        "pasos": [
            {"accion": "click", "target": "btn_buscar", "valor": None},
        ],
        "oraculos": [],
        "datos_requeridos": [],
    }


def _ui_map(screen: str) -> dict:
    return {
        "screen": screen,
        "elements": [
            {"alias_semantic": "btn_buscar", "selector_recommended": "#c_btnBuscar", "fallback_selectors": ["#c_btnBuscar"]},
        ],
    }


def _write_workspace(tmp_path: Path, scenarios: list[dict], screens: list[str]) -> tuple[Path, Path, Path]:
    contracts = tmp_path / "navigation_contracts.yml"
    contracts.write_text(_contracts_yaml(), encoding="utf-8")
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        json.dumps({"ok": True, "ticket_id": scenarios[0]["ticket_id"], "scenarios": scenarios}),
        encoding="utf-8",
    )
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    for s in screens:
        (ui_maps_dir / f"{s}.json").write_text(json.dumps(_ui_map(s)), encoding="utf-8")
    return contracts, scenarios_file, ui_maps_dir


# ── 1. Detalle cliente — human_path happy path ──────────────────────────────

def test_pipeline_detalleclie_human_path(tmp_path):
    import navigation_pipeline as pipe
    import playwright_test_generator as gen

    sc = _scenario_detalleclie(ticket_id=120, sid="P02")
    contracts, scenarios_file, ui_maps_dir = _write_workspace(
        tmp_path, [sc], ["FrmDetalleClie.aspx"],
    )

    plans_out = pipe.build_navigation_plans_for_scenarios(
        scenarios=[sc],
        lane="uat_human",
        available_data={"CLCOD": "12345"},
        contracts_path=contracts,
        playbooks_dir=REAL_PLAYBOOKS,
    )
    assert plans_out["ok"] is True, plans_out
    assert "P02" in plans_out["plans"], plans_out
    plan = plans_out["plans"]["P02"]
    # The router must have selected the Sprint N5-04 playbook for FrmDetalleClie.
    assert plan["strategy"] == "human_path"
    assert plan["playbook_id"] == "open_detalle_cliente_from_busqueda", plan["playbook_id"]
    assert len(plan["steps"]) >= 4
    # No step does a goto_direct to FrmDetalleClie (R8).
    for step in plan["steps"]:
        if step.get("method") == "goto_direct":
            assert "FrmDetalleClie" not in (step.get("target_url") or ""), step

    out_dir = tmp_path / "tests"
    result = gen.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        navigation_plans=plans_out["plans"],
        navigation_contracts_path=contracts,
    )
    assert result["ok"] is True, result
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 1, result
    spec_text = Path(generated[0]["path"]).read_text(encoding="utf-8")

    # AP-01/AP-02 — no raw goto to FrmDetalleClie in setup/beforeEach.
    assert "page.goto(`${BASE_URL}FrmDetalleClie.aspx`" not in spec_text
    assert "page.goto(`${BASE_URL}${TARGET_SCREEN}`" not in spec_text
    # The new helper IS wired.
    assert "executeNavigationPlan(page, NAVIGATION_PLAN" in spec_text
    assert '"strategy": "human_path"' in spec_text or "'strategy': 'human_path'" in spec_text
    # Summary event scaffolding is callable
    assert any(s["scenario_id"] == "P02" and s["plan_steps"] >= 4
               for s in plans_out["summaries"]), plans_out["summaries"]


# ── 2. Detalle cliente — missing CLCOD blocks early ─────────────────────────

def test_pipeline_detalleclie_no_clcod(tmp_path):
    import navigation_pipeline as pipe

    sc = _scenario_detalleclie(ticket_id=120, sid="P02")
    contracts, _, _ = _write_workspace(tmp_path, [sc], ["FrmDetalleClie.aspx"])

    out = pipe.build_navigation_plans_for_scenarios(
        scenarios=[sc],
        lane="uat_human",
        available_data={},  # CLCOD missing
        contracts_path=contracts,
        playbooks_dir=REAL_PLAYBOOKS,
    )
    assert out["ok"] is False
    assert "P02" not in out["plans"]
    assert out["blocked"], out
    block = out["blocked"][0]
    assert block["stage"] == "resolver", block
    assert block["category"] == "DATA"
    assert block["reason"] == "NAVIGATION_DATA_MISSING"
    # And the human action message references CLCOD for triage.
    assert "CLCOD" in (block.get("human_action_required") or "") or \
           "CLCOD" in str(block.get("missing_data"))


# ── 3. FrmBusqueda — direct_entry happy path ────────────────────────────────

def test_pipeline_busqueda_direct(tmp_path):
    import navigation_pipeline as pipe
    import playwright_test_generator as gen

    sc = _scenario_busqueda(ticket_id=200, sid="S01")
    contracts, scenarios_file, ui_maps_dir = _write_workspace(
        tmp_path, [sc], ["FrmBusqueda.aspx"],
    )

    plans_out = pipe.build_navigation_plans_for_scenarios(
        scenarios=[sc],
        lane="smoke_deeplink",
        available_data={},
        contracts_path=contracts,
        playbooks_dir=REAL_PLAYBOOKS,
    )
    assert plans_out["ok"] is True, plans_out
    plan = plans_out["plans"]["S01"]
    assert plan["strategy"] == "direct_entry"
    assert plan["steps"][0]["method"] == "goto_direct"
    assert plan["steps"][0]["target_url"] == "FrmBusqueda.aspx"

    # Generator should render the plan-aware spec for direct entry too.
    out_dir = tmp_path / "tests"
    result = gen.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        navigation_plans=plans_out["plans"],
        navigation_contracts_path=contracts,
    )
    assert result["ok"] is True, result
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 1, result
    spec_text = Path(generated[0]["path"]).read_text(encoding="utf-8")
    # The plan is encoded inline; helper is wired.
    assert "const NAVIGATION_PLAN" in spec_text
    assert "executeNavigationPlan(page, NAVIGATION_PLAN" in spec_text
    assert '"strategy": "direct_entry"' in spec_text or "'strategy': 'direct_entry'" in spec_text


# ── 4. Sanity — summary event payload shape ─────────────────────────────────

def test_navigation_pipeline_summary_event_shape(tmp_path):
    import navigation_pipeline as pipe

    sc = _scenario_detalleclie(ticket_id=120, sid="P02")
    contracts, _, _ = _write_workspace(tmp_path, [sc], ["FrmDetalleClie.aspx"])
    out = pipe.build_navigation_plans_for_scenarios(
        scenarios=[sc],
        lane="uat_human",
        available_data={"CLCOD": "12345"},
        contracts_path=contracts,
        playbooks_dir=REAL_PLAYBOOKS,
    )

    captured: list[dict] = []

    class _Logger:
        def event(self, name: str, payload: dict) -> None:
            captured.append({"name": name, "payload": payload})

    pipe.write_navigation_pipeline_summary(
        _Logger(), out["summaries"], spec_paths={"P02": "evidence/120/tests/P02.spec.ts"},
    )
    assert captured, "expected at least one event"
    ev = captured[0]
    assert ev["name"] == "navigation_pipeline_summary"
    p = ev["payload"]
    for key in (
        "scenario_id", "resolver_decision", "strategy", "playbook_used",
        "plan_validated", "plan_steps", "plan_arrival_assertions",
        "spec_generated", "spec_path",
    ):
        assert key in p, f"missing key: {key}"
    assert p["scenario_id"] == "P02"
    assert p["spec_generated"] is True
