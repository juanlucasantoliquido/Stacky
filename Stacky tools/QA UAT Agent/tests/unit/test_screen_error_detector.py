"""Unit tests for screen_error_detector.py — Fase 4 in-flight UI error detector.

Coverage:
- DOM_ERROR_SELECTORS catalog is non-empty and contains the canonical
  ASP.NET / Bootstrap patterns the Agenda Web actually emits.
- render_dom_detector_js() returns syntactically plausible JS with the
  selectors and text patterns substituted.
- persist_error() creates a fresh file and appends to an existing one.
- _safe_parse_json() recovers from markdown fences and dirty payloads.
- analyze_screenshot() under mock backend returns a deterministic stub
  without making any HTTP call.
- Generator with detect_screen_errors=True embeds the helper + checkScreenAfterStep
  call after fill/click/select steps.
- Generator with detect_screen_errors=False produces specs identical
  in shape to the legacy template (no SCREEN_ERRORS, no helper).
- Failure analyzer reads screen_errors_<sid>.json and short-circuits to
  category=wrong_expected_in_ticket when validation text is present.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ── DOM heuristics catalog ────────────────────────────────────────────────────


def test_selectors_catalog_covers_canonical_patterns():
    import screen_error_detector as sed
    selectors = sed.DOM_ERROR_SELECTORS
    assert isinstance(selectors, list) and len(selectors) >= 8
    joined = " ".join(selectors)
    # ASP.NET validators
    assert "Error" in joined and "Validator" in joined
    # Bootstrap / role=alert
    assert "alert-danger" in joined
    assert "role='alert'" in joined or 'role="alert"' in joined
    # Field-level
    assert "field-validation-error" in joined or "error-message" in joined


def test_text_patterns_catalog_includes_required():
    import screen_error_detector as sed
    patterns = [p.lower() for p in sed.DOM_ERROR_TEXT_PATTERNS]
    # The exact phrase that broke ticket "compromiso de pago" was the
    # required-field validation text. Make sure it's covered.
    assert any("requerido" in p for p in patterns)
    assert any("obligatorio" in p for p in patterns)


def test_render_dom_detector_js_substitutes_constants():
    import screen_error_detector as sed
    js = sed.render_dom_detector_js()
    # Constants must be substituted, not left as placeholders.
    assert "__SELECTORS__" not in js
    assert "__TEXT_PATTERNS__" not in js
    # Function name must be present and exactly one declaration.
    assert js.count("async function __detectScreenErrors") == 1
    # Selectors are JSON-serialized; spot-check one canonical entry.
    assert "alert-danger" in js
    assert "es requerido" in js or "requerido" in js


# ── Persistence ───────────────────────────────────────────────────────────────


def test_persist_error_creates_and_appends(tmp_path):
    import screen_error_detector as sed
    entry = {
        "step_index": 3,
        "screenshot_path": "evidence/x/P01/step_03_after.png",
        "source": "dom",
        "errors": [{"text": "Proyectado es requerido", "source": "span#cError"}],
        "captured_at": "2026-05-05T00:00:00+00:00",
    }
    out = sed.persist_error(tmp_path, "P01", entry)
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["step_index"] == 3

    # Append a second entry — file must contain both.
    entry2 = dict(entry)
    entry2["step_index"] = 4
    sed.persist_error(tmp_path, "P01", entry2)
    data2 = json.loads(out.read_text(encoding="utf-8"))
    assert [d["step_index"] for d in data2] == [3, 4]


def test_persist_error_recovers_from_corrupt_file(tmp_path):
    import screen_error_detector as sed
    sid_dir = tmp_path / "P01"
    sid_dir.mkdir()
    # Pre-existing file with a non-list payload — must be overwritten cleanly.
    (sid_dir / "screen_errors_P01.json").write_text(
        '{"not": "a list"}', encoding="utf-8",
    )
    entry = {"step_index": 1, "screenshot_path": None, "source": "dom",
             "errors": [], "captured_at": "now"}
    out = sed.persist_error(tmp_path, "P01", entry)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1


# ── _safe_parse_json ──────────────────────────────────────────────────────────


def test_safe_parse_json_recovers_markdown_fence():
    import screen_error_detector as sed
    out = sed._safe_parse_json('```json\n{"has_error": true}\n```')
    assert out == {"has_error": True}


def test_safe_parse_json_recovers_text_around_braces():
    import screen_error_detector as sed
    out = sed._safe_parse_json('Sure! Here it is: {"has_error": false} — done.')
    assert out == {"has_error": False}


def test_safe_parse_json_returns_none_when_unrecoverable():
    import screen_error_detector as sed
    assert sed._safe_parse_json("not even close") is None
    assert sed._safe_parse_json("") is None


# ── Vision analyzer (mock backend) ────────────────────────────────────────────


def test_analyze_screenshot_under_mock_returns_no_error(monkeypatch):
    import screen_error_detector as sed
    monkeypatch.setenv("STACKY_LLM_BACKEND", "mock")
    verdict = sed.analyze_screenshot(b"fake-png-bytes", model="gpt-4o")
    assert isinstance(verdict, dict)
    # Mock backend returns has_error=False — no network was hit.
    assert verdict["has_error"] is False
    assert verdict["model"].startswith("mock")


# ── Generator integration ────────────────────────────────────────────────────


def _ui_map_path() -> Path:
    return FIXTURES / "ui_map_FrmAgenda.json"


def _scenarios_path() -> Path:
    return FIXTURES / "scenarios_70.json"


def test_generator_off_omits_detector(tmp_path):
    """Default behaviour (flag absent) must NOT change the spec output."""
    import playwright_test_generator as gen
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(_scenarios_path().read_text(encoding="utf-8"), encoding="utf-8")
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        _ui_map_path().read_text(encoding="utf-8"), encoding="utf-8",
    )
    out_dir = tmp_path / "tests"
    result = gen.run(
        scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir,
    )
    assert result["ok"] is True
    for spec in out_dir.glob("*.spec.ts"):
        text = spec.read_text(encoding="utf-8")
        assert "__detectScreenErrors" not in text, (
            f"{spec.name} contains detector helper but flag was OFF"
        )
        assert "SCREEN_ERRORS" not in text
        assert "__checkScreenAfterStep" not in text


def test_generator_on_emits_detector_and_postcheck(tmp_path):
    import playwright_test_generator as gen
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(_scenarios_path().read_text(encoding="utf-8"), encoding="utf-8")
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        _ui_map_path().read_text(encoding="utf-8"), encoding="utf-8",
    )
    out_dir = tmp_path / "tests"
    result = gen.run(
        scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir,
        detect_screen_errors=True,
    )
    assert result["ok"] is True
    specs = list(out_dir.glob("*.spec.ts"))
    assert specs
    for spec in specs:
        text = spec.read_text(encoding="utf-8")
        # Detector present
        assert "__detectScreenErrors" in text, (
            f"{spec.name} missing detector helper despite --detect-screen-errors"
        )
        # Persistence wired
        assert "SCREEN_ERRORS_OUT_PATH" in text
        assert "screen_errors_" in text
        # At least one post-step check (every fixture scenario has fill/click)
        assert "__checkScreenAfterStep" in text, (
            f"{spec.name} missing post-step __checkScreenAfterStep"
        )


def test_generator_vision_implies_dom(tmp_path):
    """Asking for vision must also enable DOM detection — they're additive."""
    import playwright_test_generator as gen
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(_scenarios_path().read_text(encoding="utf-8"), encoding="utf-8")
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        _ui_map_path().read_text(encoding="utf-8"), encoding="utf-8",
    )
    out_dir = tmp_path / "tests"
    result = gen.run(
        scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir,
        detect_screen_errors=True, detect_screen_errors_vision=True,
    )
    assert result["ok"] is True
    sample = next(out_dir.glob("*.spec.ts"))
    text = sample.read_text(encoding="utf-8")
    # DOM helper still there
    assert "__detectScreenErrors" in text
    # Vision branch wired
    assert "QA_UAT_VISION_DETECTOR_URL" in text
    assert "/analyze" in text


# ── Failure analyzer integration ─────────────────────────────────────────────


def test_failure_analyzer_short_circuits_on_screen_error(tmp_path):
    """When screen_errors_<sid>.json shows a validation message, the
    heuristic must classify as wrong_expected_in_ticket with high confidence
    instead of going through the legacy timeout/data_drift branches."""
    import uat_failure_analyzer as fa

    # Build minimal evaluations + runner_output reflecting a fail.
    scenario_id = "P01"
    scenario_dir = tmp_path / scenario_id
    scenario_dir.mkdir()

    # In-flight detection artefact: simulate the 'Proyectado es requerido'
    # bug from the original ticket.
    (scenario_dir / f"screen_errors_{scenario_id}.json").write_text(
        json.dumps({
            "scenario_id": scenario_id,
            "detector_version": "1.0.0",
            "entries": [
                {
                    "step_index": 5,
                    "screenshot_path": str(scenario_dir / "step_05_after.png"),
                    "source": "dom",
                    "errors": [
                        {"text": "Proyectado es requerido", "source": "span#cError"},
                    ],
                    "captured_at": "2026-05-05T00:00:00+00:00",
                }
            ],
        }),
        encoding="utf-8",
    )
    # Trace placeholder so artefacts.trace points into scenario_dir — that's
    # how _extract_screen_errors locates the JSON.
    (scenario_dir / "trace.zip").write_bytes(b"fake")

    evaluations = {
        "ok": True,
        "ticket_id": 999,
        "evaluations": [
            {
                "scenario_id": scenario_id,
                "status": "fail",
                "assertions": [
                    {
                        "oracle_id": 0,
                        "tipo": "page_contains_text",
                        "target": "body",
                        "expected": "guardado",
                        "actual": "Proyectado es requerido",
                        "status": "fail",
                    }
                ],
            }
        ],
    }
    runner = {
        "ok": True,
        "ticket_id": 999,
        "runs": [
            {
                "scenario_id": scenario_id,
                "spec_file": "evidence/999/tests/P01.spec.ts",
                "status": "fail",
                "duration_ms": 12345,
                "raw_stdout": "Error: Timed out 30000ms",
                "artifacts": {
                    "trace": str(scenario_dir / "trace.zip"),
                    "video": None,
                    "screenshots": [],
                    "console_log": None,
                    "network_log": None,
                    "error_context": None,
                },
            }
        ],
    }

    eval_path = tmp_path / "evaluations.json"
    eval_path.write_text(json.dumps(evaluations), encoding="utf-8")
    runner_path = tmp_path / "runner_output.json"
    runner_path.write_text(json.dumps(runner), encoding="utf-8")

    out = fa.run(evaluations_path=eval_path, runner_output_path=runner_path)
    assert out["ok"] is True
    assert len(out["analyses"]) == 1
    a = out["analyses"][0]
    assert a["scenario_id"] == scenario_id
    assert a["category"] == "wrong_expected_in_ticket"
    assert a["confidence"] == "high"
    assert a["classified_by"] == "heuristic"
    assert a["screen_errors_count"] == 1
    assert "Proyectado es requerido" in a["hypothesis_md"]


def test_failure_analyzer_no_screen_errors_falls_back(tmp_path):
    """When the artefact is missing, classification falls back to the
    pre-existing heuristics (timeout etc.)."""
    import uat_failure_analyzer as fa

    scenario_id = "P02"
    scenario_dir = tmp_path / scenario_id
    scenario_dir.mkdir()
    (scenario_dir / "trace.zip").write_bytes(b"fake")

    evaluations = {
        "ok": True, "ticket_id": 999,
        "evaluations": [{
            "scenario_id": scenario_id, "status": "fail",
            "assertions": [{
                "oracle_id": 0, "tipo": "visible", "target": "btn_x",
                "expected": True, "actual": None, "status": "fail",
            }],
        }],
    }
    runner = {
        "ok": True, "ticket_id": 999,
        "runs": [{
            "scenario_id": scenario_id,
            "spec_file": "x.spec.ts", "status": "fail", "duration_ms": 9000,
            "raw_stdout": "Error: Timed out 30000ms waiting for selector",
            "artifacts": {"trace": str(scenario_dir / "trace.zip"),
                          "video": None, "screenshots": [],
                          "console_log": None, "network_log": None,
                          "error_context": None},
        }],
    }

    eval_path = tmp_path / "evaluations.json"
    eval_path.write_text(json.dumps(evaluations), encoding="utf-8")
    runner_path = tmp_path / "runner_output.json"
    runner_path.write_text(json.dumps(runner), encoding="utf-8")

    out = fa.run(evaluations_path=eval_path, runner_output_path=runner_path)
    assert out["ok"] is True
    a = out["analyses"][0]
    assert a["screen_errors_count"] == 0
    # Pre-existing heuristic must still apply (missing_precondition / environment_issue).
    assert a["category"] in {"missing_precondition", "environment_issue", "ui_change"}
