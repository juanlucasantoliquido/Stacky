from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_triage_includes_navigation_blame_from_step_results(tmp_path: Path):
    from failure_triage import run_failure_triage

    (tmp_path / "navigation_step_results.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "ticket_id": 120,
            "scenario_id": "P02",
            "target_screen": "FrmDetalleClie.aspx",
            "strategy": "human_path",
            "navigation_ok": False,
            "elapsed_ms_total": 1200,
            "failed_step": 4,
            "error_code": "NAV_SERVER_ERROR",
            "category": "ENV",
            "reason": "ASPNET_APPPOOL_ERROR",
            "is_terminal": True,
            "steps": [
                {
                    "step_index": 4,
                    "method": "row_click",
                    "description": "Click first client row",
                    "ok": False,
                    "attempts": 1,
                    "elapsed_ms": 1200,
                    "url_before": "FrmBusqueda.aspx",
                    "url_after": "FrmDetalleClie.aspx",
                    "intermediate_assertions_passed": [],
                    "intermediate_assertions_failed": [],
                    "screenshots": ["nav_step_04_failed.png"],
                    "error_code": "NAV_SERVER_ERROR",
                    "category": "ENV",
                    "reason": "ASPNET_APPPOOL_ERROR",
                    "is_terminal": True,
                    "detail": "page title contains Runtime Error",
                }
            ],
        }),
        encoding="utf-8",
    )

    triage = run_failure_triage(
        ticket_id=120,
        run_id="uat-120-test",
        result_json={"ok": False, "verdict": "BLOCKED", "category": "APP", "reason": "ASSERTION_FAILED"},
        execution_log=[],
        runner_classification=None,
        evidence_dir=str(tmp_path),
    )

    assert triage.category == "ENV"
    assert triage.reason == "ASPNET_APPPOOL_ERROR"
    assert triage.navigation_blame is not None
    assert triage.navigation_blame["step_index"] == 4
    assert triage.navigation_blame["method"] == "row_click"
    assert triage.publish_recommended is False

    artifact = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
    assert artifact["navigation_blame"]["error_code"] == "NAV_SERVER_ERROR"
    assert any("navigation_step_4 failed" in item for item in artifact["evidence"])
