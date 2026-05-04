"""Unit tests for playwright_test_generator.py (B5)."""
import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"
TOOL_DIR = Path(__file__).parent.parent.parent


def _scenarios_data():
    return json.loads((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"))


def test_6_scenarios_generate_6_spec_files(tmp_path):
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios_70.json"
    scenarios_file.write_text((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"), encoding="utf-8")

    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        (FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    out_dir = tmp_path / "tests"
    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
    )
    assert result["ok"] is True, result
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 6, f"Expected 6 generated, got {len(generated)}"
    spec_files = list(out_dir.glob("*.spec.ts"))
    assert len(spec_files) == 6


def test_missing_selector_blocks_scenario(tmp_path):
    import playwright_test_generator
    # Inject a scenario with an unknown target alias
    scenarios_data = _scenarios_data()
    scenarios_data["scenarios"][0]["pasos"].append(
        {"accion": "click", "target": "btn_nonexistent_xyz", "valor": None}
    )
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(json.dumps(scenarios_data), encoding="utf-8")

    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        (FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    out_dir = tmp_path / "tests"
    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
    )
    # P01 should be blocked due to missing selector
    blocked = [r for r in result["results"] if r["status"] == "blocked"]
    assert len(blocked) >= 1
    assert any("btn_nonexistent_xyz" in str(b.get("missing", [])) for b in blocked)


def test_no_hardcoded_credentials_in_output(tmp_path):
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios_70.json"
    scenarios_file.write_text((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"), encoding="utf-8")
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        (FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    out_dir = tmp_path / "tests"
    playwright_test_generator.run(scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir)

    cred_pattern = re.compile(r'(?i)(password\s*=\s*["\'][^"\']{3,}["\']|PABLO)', re.IGNORECASE)
    for spec in out_dir.glob("*.spec.ts"):
        content = spec.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "process.env" in line or line.strip().startswith("//"):
                continue
            assert not cred_pattern.search(line), f"Hardcoded credential in {spec.name}: {line}"


def test_generated_files_have_required_sections(tmp_path):
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios_70.json"
    scenarios_file.write_text((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"), encoding="utf-8")
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        (FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    out_dir = tmp_path / "tests"
    playwright_test_generator.run(scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir)

    for spec in out_dir.glob("*.spec.ts"):
        content = spec.read_text(encoding="utf-8")
        # Must import from @playwright/test
        assert "@playwright/test" in content, f"Missing @playwright/test import in {spec.name}"
        # Must reference process.env for credentials
        assert "process.env.AGENDA_WEB_" in content, f"Missing process.env in {spec.name}"
        # Must have at least one expect()
        assert "expect(" in content, f"Missing assertions in {spec.name}"


def test_blocked_scenario_no_file_generated(tmp_path):
    """A scenario with missing UI map must not generate a .spec.ts file."""
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios_70.json"
    scenarios_file.write_text((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"), encoding="utf-8")
    # Don't copy any UI maps — all scenarios should be blocked
    ui_maps_dir = tmp_path / "ui_maps_empty"
    ui_maps_dir.mkdir()
    out_dir = tmp_path / "tests"

    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
    )
    spec_files = list(out_dir.glob("*.spec.ts")) if out_dir.exists() else []
    assert len(spec_files) == 0, "No .spec.ts should be generated when UI maps are missing"
    blocked = [r for r in result.get("results", []) if r["status"] == "blocked"]
    assert len(blocked) == 6


# ── M3 — input value formatting (date / number / time …) ───────────────────


def _ui_map_with_date_input() -> dict:
    """UI map with an `input_fecha_desde` of HTML5 type=date — exact shape
    the bug from ticket 70 P04 was hitting."""
    base = json.loads((FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"))
    for el in base["elements"]:
        if el.get("alias_semantic") == "input_fecha_desde":
            el["input_type"] = "date"
            break
    return base


def _scenario_with_fill(target: str, valor) -> dict:
    return {
        "ok": True,
        "ticket_id": 70,
        "scenarios": [{
            "scenario_id": "P_DATE",
            "ticket_id": 70,
            "pantalla": "FrmAgenda.aspx",
            "titulo": f"Test fecha desde con {valor}",
            "precondiciones": [],
            "pasos": [
                {"accion": "navigate", "target": "FrmAgenda.aspx", "valor": None},
                {"accion": "fill", "target": target, "valor": valor},
            ],
            "oraculos": [{"tipo": "page_contains_text", "target": "body",
                          "valor": "Buscar"}],
            "datos_requeridos": [],
            "origen": {"ticket_section": "plan_pruebas", "item_id": "P_DATE"},
        }],
    }


def test_fill_value_reformatted_to_yyyy_mm_dd(tmp_path):
    """Ticket 70 P04 regression: fill('19000101') against type=date must
    become fill('1900-01-01') in the rendered spec, not blow up at runtime."""
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        json.dumps(_scenario_with_fill("input_fecha_desde", "19000101")),
        encoding="utf-8",
    )
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        json.dumps(_ui_map_with_date_input()), encoding="utf-8",
    )
    out_dir = tmp_path / "tests"
    result = playwright_test_generator.run(
        scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir,
    )
    assert result["ok"] is True
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 1, result
    rendered = (out_dir / generated[0]["path"]).read_text(encoding="utf-8") \
        if Path(generated[0]["path"]).is_absolute() else \
        Path(generated[0]["path"]).read_text(encoding="utf-8")
    assert "fill('1900-01-01')" in rendered, (
        f"Expected reformatted date in rendered spec, got:\n{rendered[1500:2500]}"
    )
    assert "fill('19000101')" not in rendered


def test_fill_value_human_format_reformatted(tmp_path):
    """01/01/2026 (Spanish) → 2026-01-01."""
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        json.dumps(_scenario_with_fill("input_fecha_desde", "01/01/2026")),
        encoding="utf-8",
    )
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        json.dumps(_ui_map_with_date_input()), encoding="utf-8",
    )
    out_dir = tmp_path / "tests"
    result = playwright_test_generator.run(
        scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir,
    )
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 1
    spec_path = Path(generated[0]["path"])
    assert "fill('2026-01-01')" in spec_path.read_text(encoding="utf-8")


def test_fill_value_unparseable_blocks_scenario(tmp_path):
    """Unparseable date value must mark the scenario blocked with a
    structured reason — never reach the runner."""
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        json.dumps(_scenario_with_fill("input_fecha_desde", "tomorrow")),
        encoding="utf-8",
    )
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        json.dumps(_ui_map_with_date_input()), encoding="utf-8",
    )
    out_dir = tmp_path / "tests"
    result = playwright_test_generator.run(
        scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir,
    )
    blocked = [r for r in result["results"] if r["status"] == "blocked"]
    assert len(blocked) == 1
    assert "input_value_unparseable_for_type" in blocked[0]["reason"]
    spec_files = list(out_dir.glob("*.spec.ts")) if out_dir.exists() else []
    assert len(spec_files) == 0, (
        "Unparseable-value scenario MUST NOT generate a .spec.ts — "
        "running it would falsely look like a product defect."
    )


def test_legacy_ui_map_without_input_type_passes_through(tmp_path):
    """Backwards compat: pre-1.1 UI maps lack input_type. The generator must
    fall back to identity formatting (don't break existing flows)."""
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        json.dumps(_scenario_with_fill("input_fecha_desde", "anything")),
        encoding="utf-8",
    )
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    # NOT enriched — no input_type fields.
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        (FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"), encoding="utf-8",
    )
    out_dir = tmp_path / "tests"
    result = playwright_test_generator.run(
        scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir,
    )
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 1, result


# ── M4 — assertions_<sid>.json wired into the spec template ─────────────────


def test_template_emits_oracle_probes_constant(tmp_path):
    """Each spec MUST embed an ORACLE_PROBES TS constant carrying the
    oracle list, plus a fs.writeFileSync block in test.afterEach. Without
    this, uat_assertion_evaluator.py has no `actual` to compare against
    and every oracle defaults to status=review (the bug behind ticket 70's
    `evaluations.json: all review`).
    """
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios_70.json"
    scenarios_file.write_text((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"), encoding="utf-8")
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        (FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"), encoding="utf-8",
    )
    out_dir = tmp_path / "tests"
    playwright_test_generator.run(
        scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir,
    )
    for spec in out_dir.glob("*.spec.ts"):
        content = spec.read_text(encoding="utf-8")
        assert "ORACLE_PROBES" in content, f"{spec.name} missing ORACLE_PROBES constant"
        assert "ASSERTIONS_OUT_PATH" in content, f"{spec.name} missing assertions output path"
        assert "fs.writeFileSync" in content, f"{spec.name} missing fs.writeFileSync — afterEach won't persist evidence"
        assert "test.afterEach" in content


def test_output_validates_against_schema(tmp_path):
    """The result dict has required fields for the generator output."""
    import playwright_test_generator
    scenarios_file = tmp_path / "scenarios_70.json"
    scenarios_file.write_text((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"), encoding="utf-8")
    ui_maps_dir = tmp_path / "ui_maps"
    ui_maps_dir.mkdir()
    (ui_maps_dir / "FrmAgenda.aspx.json").write_text(
        (FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    out_dir = tmp_path / "tests"
    result = playwright_test_generator.run(scenarios_path=scenarios_file, ui_maps_dir=ui_maps_dir, out_dir=out_dir)
    assert "ok" in result
    assert "generated" in result
    assert "blocked" in result
    assert "results" in result
    for r in result["results"]:
        assert "scenario_id" in r
        assert "status" in r
