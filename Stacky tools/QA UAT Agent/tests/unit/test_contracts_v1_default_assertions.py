from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_contracts_v1_default_assertions_include_login_guard():
    from navigation_plan_builder import build_navigation_plan, default_arrival_assertions_for_screen

    defaults = default_arrival_assertions_for_screen("FrmReportes.aspx")
    assert {a["type"] for a in defaults} == {"no_aspnet_error", "no_login_redirect", "url_contains"}

    plan = build_navigation_plan(
        decision={
            "decision": "ALLOW_GENERATION",
            "strategy": "direct_entry",
            "target_screen": "FrmReportes.aspx",
            "lane": "smoke_deeplink",
        },
        scenario={"ticket_id": 99, "scenario_id": "S01", "pantalla": "FrmReportes.aspx"},
        contracts={
            "_meta": {"version": "2.0", "schema": "NavigationContracts/2.0"},
            "FrmReportes.aspx": {
                "screen_type": "list",
                "direct_entry_allowed": True,
                "deeplink_allowed": False,
            },
        },
        lane="smoke_deeplink",
    )

    types = {a["type"] for a in plan["arrival_assertions"]}
    assert {"no_aspnet_error", "no_login_redirect", "url_contains"} <= types
    assert any(
        a["type"] == "url_contains" and a["expected_value"] == "FrmReportes"
        for a in plan["arrival_assertions"]
    )
