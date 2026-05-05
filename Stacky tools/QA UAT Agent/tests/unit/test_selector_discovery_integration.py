"""Unit tests for Fase 8 — discovered_selectors.json fallback in playwright_test_generator.

Covers:
  1. Discovered selector resolves a previously-BLOCKED scenario
  2. File absent → graceful degradation (still works, still blocks on unknown)
  3. UI-map selector wins over discovered (merge policy: UI map takes priority)
  4. meta.discovered_selectors_file is populated when file exists
  5. Selectors from screen B are NOT injected when processing screen A
  6. Malformed discovered_selectors file degrades gracefully
  7. discovered_selectors_used list is populated in result
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _scenarios_with_unknown_alias(tmp_path, alias: str = "btn_discovered_alias"):
    """Produce a scenarios.json where scenario P01 has an extra click on `alias`."""
    import playwright_test_generator  # noqa: F401 (ensure sys.path set up)
    base = json.loads((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"))
    base["scenarios"][0]["pasos"].append(
        {"accion": "click", "target": alias, "valor": None}
    )
    p = tmp_path / "scenarios.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return p


def _ui_maps_dir(tmp_path):
    d = tmp_path / "ui_maps"
    d.mkdir()
    (d / "FrmAgenda.aspx.json").write_text(
        (FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return d


def _discovered_selectors_file(tmp_path, by_screen: dict) -> Path:
    payload = {
        "schema_version": "1.0",
        "generated_at": "2026-05-05T00:00:00",
        "tool_version": "2.1.0",
        "description": "test fixture",
        "by_screen": by_screen,
    }
    p = tmp_path / "discovered_selectors.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_discovered_selector_resolves_blocked_scenario(tmp_path):
    """Scenario missing from UI map but present in discovered cache → generated."""
    import playwright_test_generator

    alias = "btn_discovered_alias"
    scenarios_file = _scenarios_with_unknown_alias(tmp_path, alias)
    ui_maps_dir = _ui_maps_dir(tmp_path)
    disc_file = _discovered_selectors_file(
        tmp_path,
        {"FrmAgenda.aspx": {alias: "#btnDiscoveredAlias"}},
    )
    out_dir = tmp_path / "out"
    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        discovered_selectors_path=disc_file,
    )
    assert result["ok"] is True, result
    # P01 should now be generated, not blocked
    blocked = [r for r in result["results"] if r["status"] == "blocked"]
    assert not any(alias in str(b.get("missing", [])) for b in blocked), (
        f"Alias {alias!r} should have been resolved from cache but was still blocked"
    )
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) >= 1


def test_discovered_selectors_file_absent_degrades_gracefully(tmp_path):
    """When discovered_selectors.json is absent, tool still works normally."""
    import playwright_test_generator

    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        (FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ui_maps_dir = _ui_maps_dir(tmp_path)
    non_existent = tmp_path / "no_such_file.json"
    out_dir = tmp_path / "out"

    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        discovered_selectors_path=non_existent,
    )
    assert result["ok"] is True, result
    # All 6 base scenarios should still generate
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 6


def test_ui_map_selector_wins_over_discovered(tmp_path):
    """Same alias in both UI map and discovered → UI map selector is used."""
    import playwright_test_generator

    # select_empresa is defined in ui_map_FrmAgenda.json as getByLabel('Empresa')
    # We put a different CSS selector in the discovered cache for the same alias
    alias = "select_empresa"
    disc_file = _discovered_selectors_file(
        tmp_path,
        {"FrmAgenda.aspx": {alias: "#ddlEmpresa_OVERRIDDEN"}},
    )
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        (FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ui_maps_dir = _ui_maps_dir(tmp_path)
    out_dir = tmp_path / "out"

    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        discovered_selectors_path=disc_file,
    )
    assert result["ok"] is True, result
    # Verify that generated spec files use the UI-map selector, not the override
    spec_files = list(out_dir.glob("*.spec.ts"))
    assert spec_files, "No spec files generated"
    for spec in spec_files:
        content = spec.read_text(encoding="utf-8")
        assert "#ddlEmpresa_OVERRIDDEN" not in content, (
            f"Discovered selector should NOT override UI-map selector in {spec.name}"
        )


def test_discovered_selectors_file_populated_in_meta(tmp_path):
    """meta.discovered_selectors_file is set to the file path when the file exists."""
    import playwright_test_generator

    disc_file = _discovered_selectors_file(
        tmp_path,
        {"FrmAgenda.aspx": {"btn_extra": "#btnExtra"}},
    )
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        (FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ui_maps_dir = _ui_maps_dir(tmp_path)
    out_dir = tmp_path / "out"

    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        discovered_selectors_path=disc_file,
    )
    assert result["ok"] is True, result
    meta = result.get("meta", {})
    assert meta.get("discovered_selectors_file") is not None, (
        "meta.discovered_selectors_file should be set when file exists"
    )
    assert "discovered_selectors" in meta["discovered_selectors_file"]


def test_discovered_selectors_file_null_in_meta_when_absent(tmp_path):
    """meta.discovered_selectors_file is None when file doesn't exist."""
    import playwright_test_generator

    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        (FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ui_maps_dir = _ui_maps_dir(tmp_path)
    out_dir = tmp_path / "out"

    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        discovered_selectors_path=tmp_path / "nonexistent.json",
    )
    assert result["ok"] is True, result
    meta = result.get("meta", {})
    assert meta.get("discovered_selectors_file") is None


def test_discovered_selectors_wrong_screen_not_injected(tmp_path):
    """Discovered selectors for screen B must NOT be injected when processing screen A."""
    import playwright_test_generator

    alias = "btn_only_on_screen_b"
    disc_file = _discovered_selectors_file(
        tmp_path,
        # Only defined for a DIFFERENT screen
        {"OtherScreen.aspx": {alias: "#btnOnlyOnScreenB"}},
    )
    scenarios_file = _scenarios_with_unknown_alias(tmp_path, alias)
    ui_maps_dir = _ui_maps_dir(tmp_path)
    out_dir = tmp_path / "out"

    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        discovered_selectors_path=disc_file,
    )
    assert result["ok"] is True, result
    # P01 should STILL be blocked — the alias is only for OtherScreen
    blocked = [r for r in result["results"] if r["status"] == "blocked"]
    assert any(alias in str(b.get("missing", [])) for b in blocked), (
        f"Alias {alias!r} from wrong screen should not have resolved the block"
    )


def test_discovered_selectors_malformed_degrades_gracefully(tmp_path):
    """Malformed JSON in discovered_selectors.json is ignored; tool still works."""
    import playwright_test_generator

    disc_file = tmp_path / "bad_discovered.json"
    disc_file.write_text("{ this is not valid json }", encoding="utf-8")

    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(
        (FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ui_maps_dir = _ui_maps_dir(tmp_path)
    out_dir = tmp_path / "out"

    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        discovered_selectors_path=disc_file,
    )
    assert result["ok"] is True, result
    generated = [r for r in result["results"] if r["status"] == "generated"]
    assert len(generated) == 6


def test_discovered_selectors_used_list_populated_in_result(tmp_path):
    """discovered_selectors_used list in result contains resolved alias names."""
    import playwright_test_generator

    alias = "btn_cache_resolved"
    disc_file = _discovered_selectors_file(
        tmp_path,
        {"FrmAgenda.aspx": {alias: "#btnCacheResolved"}},
    )
    scenarios_file = _scenarios_with_unknown_alias(tmp_path, alias)
    ui_maps_dir = _ui_maps_dir(tmp_path)
    out_dir = tmp_path / "out"

    result = playwright_test_generator.run(
        scenarios_path=scenarios_file,
        ui_maps_dir=ui_maps_dir,
        out_dir=out_dir,
        discovered_selectors_path=disc_file,
    )
    assert result["ok"] is True, result
    generated_results = [r for r in result["results"] if r["status"] == "generated"]
    assert generated_results, "Expected at least one generated scenario"
    # The first scenario (P01) used the discovered selector
    p01 = next((r for r in generated_results if "P01" in r.get("scenario_id", "")), None)
    assert p01 is not None, "P01 not found in results"
    assert alias in p01.get("discovered_selectors_used", []), (
        f"Expected {alias!r} in discovered_selectors_used, got {p01.get('discovered_selectors_used')}"
    )
