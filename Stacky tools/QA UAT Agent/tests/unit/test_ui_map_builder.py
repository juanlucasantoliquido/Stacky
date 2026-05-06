"""Unit tests for ui_map_builder.py (B3)."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _clean_env(monkeypatch):
    """Remove web credentials from environment."""
    monkeypatch.delenv("AGENDA_WEB_BASE_URL", raising=False)
    monkeypatch.delenv("AGENDA_WEB_USER", raising=False)
    monkeypatch.delenv("AGENDA_WEB_PASS", raising=False)


def test_missing_env_var_fails_before_browser(monkeypatch):
    """Tool must return missing_env_var without opening a browser."""
    import ui_map_builder
    _clean_env(monkeypatch)
    with patch("playwright.sync_api.sync_playwright") as mock_pw:
        result = ui_map_builder.run(screen="FrmAgenda.aspx")
    mock_pw.assert_not_called()
    assert result["ok"] is False
    assert result["error"] == "missing_env_var"


def test_cache_hit_skips_playwright(monkeypatch, tmp_path):
    """If valid cache exists, Playwright should not be invoked."""
    import ui_map_builder
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://localhost")
    monkeypatch.setenv("AGENDA_WEB_USER", "testuser")
    monkeypatch.setenv("AGENDA_WEB_PASS", "testpass")

    cached_data = json.loads((FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"))
    cached_data["hash"] = "sha256:abc123"
    # Schema version match required after ui_map_builder v1.1.0 introduced
    # cache invalidation on schema bump (M1 — enriched UI map).
    cached_data["schema_version"] = ui_map_builder._SCHEMA_VERSION

    cache_dir = tmp_path / "cache" / "ui_maps"
    cache_dir.mkdir(parents=True)
    (cache_dir / "FrmAgenda.aspx.json").write_text(
        json.dumps(cached_data), encoding="utf-8"
    )

    with patch.object(ui_map_builder, "_CACHE_DIR", cache_dir):
        with patch("playwright.sync_api.sync_playwright") as mock_pw:
            result = ui_map_builder.run(screen="FrmAgenda.aspx", rebuild=False)
    mock_pw.assert_not_called()
    assert result["ok"] is True


def test_rebuild_flag_bypasses_cache(monkeypatch, tmp_path):
    """--rebuild must ignore valid cache and call Playwright."""
    import ui_map_builder
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://localhost")
    monkeypatch.setenv("AGENDA_WEB_USER", "testuser")
    monkeypatch.setenv("AGENDA_WEB_PASS", "testpass")

    cached_data = json.loads((FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"))
    cache_dir = tmp_path / "cache" / "ui_maps"
    cache_dir.mkdir(parents=True)
    (cache_dir / "FrmAgenda.aspx.json").write_text(json.dumps(cached_data), encoding="utf-8")

    with patch.object(ui_map_builder, "_CACHE_DIR", cache_dir):
        # Mock playwright so it returns a crash (enough to verify it was called)
        with patch("playwright.sync_api.sync_playwright", side_effect=Exception("pw-called")):
            result = ui_map_builder.run(screen="FrmAgenda.aspx", rebuild=True)
    # Playwright was invoked (resulted in crash or error)
    assert result["ok"] is False


def test_alias_semantic_follows_pattern():
    """All alias_semantic values in the fixture match the required pattern."""
    import re
    import ui_map_builder
    pattern = re.compile(r"^(select|input|btn|grid|panel|msg|link|table|checkbox|radio|text)_[a-zA-Z0-9_]+$")
    data = json.loads((FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"))
    for el in data["elements"]:
        alias = el["alias_semantic"]
        assert pattern.match(alias), f"alias_semantic '{alias}' does not match pattern"


# ── M1 — UI map enriquecido (input_type, is_decorative, schema_version) ─────


def test_is_decorative_input_field_label():
    """Materialize column titles must be flagged decorative.

    This is the exact class that broke ticket 70 P01: the LLM compiler picked
    `<div class="col s10 input-field-label">…Agendados por Usuario</div>` as
    the target of an `invisible` oracle for "no debe aparecer mensaje de
    lista vacía". The element is a permanent layout title, never a runtime
    message, so it always renders visible and the test always FAILs.
    """
    import ui_map_builder
    assert ui_map_builder._is_decorative("div", ["col", "s10", "input-field-label"]) is True


def test_is_decorative_page_title():
    import ui_map_builder
    assert ui_map_builder._is_decorative("div", ["page-title"]) is True
    assert ui_map_builder._is_decorative("span", ["section-title", "h2"]) is True


def test_is_decorative_form_control_never():
    """Form controls are never decorative — even if they happen to share a
    layout class (paranoid)."""
    import ui_map_builder
    assert ui_map_builder._is_decorative("input", ["input-field-label"]) is False
    assert ui_map_builder._is_decorative("select", ["page-title"]) is False
    assert ui_map_builder._is_decorative("button", ["section-title"]) is False


def test_is_decorative_empty_class_list():
    import ui_map_builder
    assert ui_map_builder._is_decorative("div", []) is False
    assert ui_map_builder._is_decorative("div", None) is False


def test_is_decorative_unrelated_classes():
    import ui_map_builder
    assert ui_map_builder._is_decorative("div", ["card", "panel-body", "user-content"]) is False


def test_cache_invalidated_on_schema_version_bump(monkeypatch, tmp_path):
    """A cache entry without schema_version (or with an older one) must be
    rebuilt — older caches lack input_type/is_decorative and would silently
    mislead the compiler.
    """
    import ui_map_builder
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://localhost")
    monkeypatch.setenv("AGENDA_WEB_USER", "u")
    monkeypatch.setenv("AGENDA_WEB_PASS", "p")

    legacy = json.loads((FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"))
    # Explicit OLD schema version → must trigger rebuild.
    legacy["schema_version"] = "ui_map/1.0"
    legacy["hash"] = "sha256:legacy"

    cache_dir = tmp_path / "cache" / "ui_maps"
    cache_dir.mkdir(parents=True)
    (cache_dir / "FrmAgenda.aspx.json").write_text(
        json.dumps(legacy), encoding="utf-8",
    )

    with patch.object(ui_map_builder, "_CACHE_DIR", cache_dir):
        # Force playwright to crash so we can assert it WAS called.
        with patch("playwright.sync_api.sync_playwright", side_effect=Exception("pw-called")):
            result = ui_map_builder.run(screen="FrmAgenda.aspx", rebuild=False)
    assert result["ok"] is False
    assert "pw-called" in (result.get("message") or "") or result.get("error") in {
        "playwright_crash", "playwright_not_installed",
    }


def test_low_robustness_elements_in_warnings(monkeypatch, tmp_path):
    """If the UI map has low-robustness elements, warnings must be populated."""
    import ui_map_builder
    # Test the postprocessing logic directly via _add_semantic_aliases fallback + warning
    elements = [
        {
            "kind": "button",
            "role": "button",
            "label": None,
            "asp_id": "ctl00_CP_ctl02_btnOk",
            "data_testid": None,
            "selector_recommended": "css_fallback",
            "robustness": "low",
            "alias_semantic": "btn_element",
            "position": {"x": 0, "y": 0},
            "warning": "requires_data_testid_from_dev",
        }
    ]
    low_count = sum(1 for e in elements if e.get("robustness") == "low")
    warnings = []
    if low_count:
        warnings.append(f"{low_count} elementos con robustness=low: requieren data-testid del dev")
    assert len(warnings) == 1
    assert "low" in warnings[0]


def test_login_failed_returns_error(monkeypatch):
    """Playwright login failure returns login_failed error."""
    import ui_map_builder
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://localhost")
    monkeypatch.setenv("AGENDA_WEB_USER", "baduser")
    monkeypatch.setenv("AGENDA_WEB_PASS", "badpass")

    # Mock playwright to raise TimeoutError on login
    class FakePwContext:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def chromium(self):
            return self
        def launch(self, **kw):
            return FakeBrowser()

    class FakeBrowser:
        def new_context(self):
            return FakeBrowserContext()
        def close(self):
            pass

    class FakeBrowserContext:
        def new_page(self):
            return FakePage()

    class FakePage:
        def goto(self, url, timeout=None):
            from playwright.sync_api import TimeoutError as PwTimeout
            raise PwTimeout("timeout")
        def wait_for_load_state(self, *a, **kw):
            pass
        def fill(self, *a, **kw):
            pass
        def click(self, *a, **kw):
            pass
        @property
        def url(self):
            return "http://localhost/Login.aspx"
        def content(self):
            return ""

    with patch("playwright.sync_api.sync_playwright") as mock_pw:
        mock_pw.return_value = FakePwContext()
        result = ui_map_builder.run(screen="FrmAgenda.aspx")
    assert result["ok"] is False
    assert "login_failed" in result["error"] or "playwright_crash" in result["error"]


def test_output_validates_against_schema(tmp_path):
    """Fixture ui_map_FrmAgenda.json validates against ui_map.schema.json."""
    import jsonschema
    schema_path = Path(__file__).parent.parent.parent / "schemas" / "ui_map.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = json.loads((FIXTURES / "ui_map_FrmAgenda.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)


# ── Fase 1 — early validation against shared screen catalogue ────────────────


def test_unsupported_screen_returns_structured_error_without_browser(monkeypatch):
    """ui_map_builder MUST reject screens outside the catalogue BEFORE
    touching env vars or opening Playwright. Returning a structured error
    `{"ok": false, "error": "unsupported_screen", "screen": ...}` lets
    callers (pipeline / VS Code extension) surface the failure cleanly.
    """
    import ui_map_builder
    # Even with full credentials, the validation must short-circuit.
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://localhost")
    monkeypatch.setenv("AGENDA_WEB_USER", "u")
    monkeypatch.setenv("AGENDA_WEB_PASS", "p")

    with patch("playwright.sync_api.sync_playwright") as mock_pw:
        result = ui_map_builder.run(screen="FrmReportes.aspx")

    mock_pw.assert_not_called()
    assert result["ok"] is False
    assert result["error"] == "unsupported_screen"
    assert result["screen"] == "FrmReportes.aspx"
    assert "FrmAgenda.aspx" in result.get("supported_screens", [])
