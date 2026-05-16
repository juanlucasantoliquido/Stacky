"""Sprint N5-02 — navigation_plan_validator.

Bundles the four mandatory tests from roadmap §5.2.5:

    * test_nav_plan_validator_valid
    * test_nav_plan_validator_missing_selector
    * test_nav_plan_validator_direct_goto_violation
    * test_nav_plan_validator_data_binding_missing

Plus a few extra cases to lock down the surrounding rules so regressions
in the validator surface immediately.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _baseline_plan() -> dict:
    """A well-formed plan that should pass every rule by default."""
    return {
        "plan_version": "1.0",
        "ticket_id": 120,
        "scenario_id": "P02",
        "target_screen": "FrmDetalleClie.aspx",
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
            {
                "step_index": 2,
                "method": "fill",
                "description": "Enter CLCOD in the search field",
                "selector": "#c_abfCliente",
                "data_bindings": {"value": "CLCOD"},
                "timeout_ms": 5000,
                "retries": 1,
            },
            {
                "step_index": 3,
                "method": "button_click",
                "description": "Click Search",
                "selector": "#c_btnBuscar",
                "wait_url_contains": "FrmBusqueda",
                "timeout_ms": 30000,
                "retries": 2,
            },
            {
                "step_index": 4,
                "method": "row_click",
                "description": "Click first matching row",
                "selector": "#c_gvClientes tbody tr:nth-child(1) td",
                "wait_url_contains": "FrmDetalleClie",
                "timeout_ms": 45000,
                "retries": 3,
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
            {
                "assertion_id": "url_contains_detalle",
                "type": "url_contains",
                "expected_value": "FrmDetalleClie",
                "description": "URL contains FrmDetalleClie",
                "severity": "hard",
                "category_on_fail": "NAV",
            },
            {
                "assertion_id": "no_login_redirect",
                "type": "no_login_redirect",
                "description": "No login redirect",
                "severity": "hard",
                "category_on_fail": "ENV",
            },
        ],
        "session_requirements": {
            "require_valid_storagestate": True,
            "storagestate_max_age_minutes": 120,
        },
    }


def _contracts() -> dict:
    """In-memory navigation_contracts equivalent used for R8."""
    return {
        "_meta": {"version": "1.0"},
        "FrmBusqueda.aspx": {
            "screen_type": "list",
            "direct_entry_allowed": True,
            "deeplink_allowed": False,
        },
        "FrmDetalleClie.aspx": {
            "screen_type": "detail",
            "direct_entry_allowed": False,
            "deeplink_allowed": True,
        },
    }


# ── 1. valid plan ────────────────────────────────────────────────────────────

def test_nav_plan_validator_valid():
    import navigation_plan_validator as v
    plan = _baseline_plan()
    res = v.validate(
        navigation_plan=plan,
        available_data={"CLCOD": "12345"},
        contracts=_contracts(),
    )
    assert res["ok"] is True, res
    assert res["plan_id"] == "120_P02"
    assert res["steps_validated"] == 4
    assert res["assertions_declared"] == 3
    assert res["data_bindings_resolved"]["CLCOD"] == "12345"


# ── 2. R3 — fill step missing selector ───────────────────────────────────────

def test_nav_plan_validator_missing_selector():
    import navigation_plan_validator as v
    plan = _baseline_plan()
    # Wipe the selector on the fill step (step 2).
    plan["steps"][1]["selector"] = ""
    res = v.validate(
        navigation_plan=plan,
        available_data={"CLCOD": "12345"},
        contracts=_contracts(),
    )
    assert res["ok"] is False
    assert res["verdict"] == "BLOCKED"
    assert res["category"] == "PIP"
    assert res["reason"] == "INVALID_NAV_PLAN"
    rules = {e["rule"] for e in res["plan_errors"]}
    assert "R3_FILL_MISSING_SELECTOR" in rules, res["plan_errors"]
    assert res["failed_validation"].startswith("step_index_2_")


# ── 3. R8 — goto_direct against direct_entry_allowed: false ──────────────────

def test_nav_plan_validator_direct_goto_violation():
    import navigation_plan_validator as v
    plan = _baseline_plan()
    # Replace step 1 with an illegal direct goto to FrmDetalleClie.
    plan["steps"][0] = {
        "step_index": 1,
        "method": "goto_direct",
        "description": "Illegal direct entry",
        "target_url": "FrmDetalleClie.aspx",
        "wait_url_contains": "FrmDetalleClie",
        "timeout_ms": 20000,
    }
    res = v.validate(
        navigation_plan=plan,
        available_data={"CLCOD": "12345"},
        contracts=_contracts(),
    )
    assert res["ok"] is False, res
    rules = {e["rule"] for e in res["plan_errors"]}
    assert "R8_DIRECT_GOTO_FORBIDDEN" in rules, res["plan_errors"]
    offending = next(e for e in res["plan_errors"] if e["rule"] == "R8_DIRECT_GOTO_FORBIDDEN")
    assert offending["screen"] == "FrmDetalleClie.aspx"


# ── 4. R7 — data_binding missing in available_data ───────────────────────────

def test_nav_plan_validator_data_binding_missing():
    import navigation_plan_validator as v
    plan = _baseline_plan()
    res = v.validate(
        navigation_plan=plan,
        available_data={},  # CLCOD intentionally missing
        contracts=_contracts(),
    )
    assert res["ok"] is False
    rules = {e["rule"] for e in res["plan_errors"]}
    assert "R7_DATA_BINDING_MISSING" in rules, res["plan_errors"]
    miss = next(e for e in res["plan_errors"] if e["rule"] == "R7_DATA_BINDING_MISSING")
    assert miss["data_key"] == "CLCOD"
    assert miss["step_index"] == 2


# ── Extra coverage — small regression net for the surrounding rules ──────────

def test_nav_plan_validator_rejects_empty_steps():
    import navigation_plan_validator as v
    plan = _baseline_plan()
    plan["steps"] = []
    res = v.validate(
        navigation_plan=plan,
        available_data={"CLCOD": "12345"},
        contracts=_contracts(),
    )
    assert res["ok"] is False
    # Either jsonschema rejects via minItems, or R1 fires — both are fine.
    rules_or_paths = {(e.get("rule"), e.get("path")) for e in res["plan_errors"]}
    assert any(
        rule == "R1_AT_LEAST_ONE_STEP" or (path and "steps" in path)
        for (rule, path) in rules_or_paths
    ), res["plan_errors"]


def test_nav_plan_validator_rejects_incomplete_arrival_assertions():
    import navigation_plan_validator as v
    plan = _baseline_plan()
    # Drop url_contains — leave only no_aspnet_error.
    plan["arrival_assertions"] = [plan["arrival_assertions"][0]]
    res = v.validate(
        navigation_plan=plan,
        available_data={"CLCOD": "12345"},
        contracts=_contracts(),
    )
    assert res["ok"] is False
    rules = {e["rule"] for e in res["plan_errors"]}
    assert "R6_ARRIVAL_ASSERTIONS_INCOMPLETE" in rules


def test_nav_plan_validator_form_submit_missing_fields():
    import navigation_plan_validator as v
    plan = _baseline_plan()
    plan["steps"].append({
        "step_index": 5,
        "method": "form_submit",
        "description": "Submit",
        # eventtarget + wait_url_contains intentionally absent
    })
    res = v.validate(
        navigation_plan=plan,
        available_data={"CLCOD": "12345"},
        contracts=_contracts(),
    )
    assert res["ok"] is False
    rules = {e["rule"] for e in res["plan_errors"]}
    assert "R4_FORM_SUBMIT_MISSING_EVENTTARGET" in rules
    assert "R4_FORM_SUBMIT_MISSING_WAIT_URL" in rules


def test_nav_plan_validator_uses_file_contracts(tmp_path):
    import navigation_plan_validator as v
    contracts_file = tmp_path / "navigation_contracts.yml"
    contracts_file.write_text(
        """
FrmBusqueda.aspx:
  direct_entry_allowed: true
FrmDetalleClie.aspx:
  direct_entry_allowed: false
""".strip(),
        encoding="utf-8",
    )
    plan = _baseline_plan()
    plan["steps"][0]["target_url"] = "FrmDetalleClie.aspx"
    res = v.validate(
        navigation_plan=plan,
        available_data={"CLCOD": "12345"},
        contracts_path=contracts_file,
    )
    assert res["ok"] is False
    assert any(e["rule"] == "R8_DIRECT_GOTO_FORBIDDEN" for e in res["plan_errors"])
