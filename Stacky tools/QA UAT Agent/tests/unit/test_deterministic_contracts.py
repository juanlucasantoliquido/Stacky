import json


def test_playwright_result_classifier_preserves_global_setup_error(tmp_path):
    from playwright_result_classifier import classify_playwright_results

    report = tmp_path / "playwright-results.json"
    report.write_text(
        json.dumps(
            {
                "suites": [],
                "errors": [
                    {
                        "message": (
                            "Error: globalSetup failed\n"
                            "TimeoutError: page.goto: Timeout 30000ms exceeded.\n"
                            "navigating to http://localhost:35017/AgendaWeb/FrmLogin.aspx"
                        )
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = classify_playwright_results(json_path=str(report))

    assert result.verdict == "BLOCKED"
    assert result.category == "ENV"
    assert result.reason == "LOGIN_PAGE_TIMEOUT"


def test_playwright_config_writer_defaults_zero_retries():
    from playwright_config_writer import generate_config, get_env_defaults

    defaults = get_env_defaults()
    assert defaults["QA_UAT_RETRIES"] == "0"

    result = generate_config(dry_run=True)
    assert result["ok"] is True
    assert "retries: Number(process.env.QA_UAT_RETRIES ?? 0)" in result["content"]


def test_navigation_plan_builder_emits_zero_retries_for_direct_plan():
    from navigation_plan_builder import build_navigation_plan

    plan = build_navigation_plan(
        decision={
            "strategy": "direct_entry",
            "ticket_id": 120,
            "scenario_id": "P01",
            "target_screen": "FrmBusqueda.aspx",
        },
        scenario={"scenario_id": "P01", "pantalla": "FrmBusqueda.aspx"},
    )

    assert plan["steps"][0]["retries"] == 0
