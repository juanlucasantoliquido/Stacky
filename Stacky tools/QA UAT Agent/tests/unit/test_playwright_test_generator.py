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
