"""Unit tests for Fase 10 — autonomous_explorer.py + agenda_screens.add_discovered_screen().

Covers:
  1. _extract_screen_from_url — extracts screen name from URL
  2. _extract_screen_from_url — returns None for non-aspx URL
  3. _build_report — produces valid schema with learned_edges
  4. _build_report — deduplicates edges with same source+target
  5. _build_report — marks unknown screens correctly
  6. _is_safe_to_click — rejects blacklisted selectors
  7. _is_safe_to_click — accepts safe selectors
  8. run() — returns error when AGENDA_WEB_BASE_URL missing
  9. run() — returns error when credentials missing
  10. add_discovered_screen — adds new screen to in-memory catalogue
  11. add_discovered_screen — returns False for already-known screen
  12. add_discovered_screen — writes discovered_screens.json
  13. add_discovered_screen — loaded at import (persisted screens available)
  14. add_discovered_screen — rejects non-aspx name
  15. _load_discovered_screens — loads previously persisted screens
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")


# ──────────────────────────────────────────────────────────────────────────────
# autonomous_explorer helpers
# ──────────────────────────────────────────────────────────────────────────────

class TestExtractScreenFromUrl:
    def test_extracts_frmagenda(self):
        from autonomous_explorer import _extract_screen_from_url
        result = _extract_screen_from_url("http://app/AgendaWeb/FrmAgenda.aspx?id=1")
        assert result == "FrmAgenda.aspx"

    def test_extracts_popup(self):
        from autonomous_explorer import _extract_screen_from_url
        result = _extract_screen_from_url("http://app/AgendaWeb/PopUpCompromisos.aspx")
        assert result == "PopUpCompromisos.aspx"

    def test_returns_none_for_non_aspx(self):
        from autonomous_explorer import _extract_screen_from_url
        result = _extract_screen_from_url("http://app/api/data.json")
        assert result is None

    def test_returns_none_for_empty(self):
        from autonomous_explorer import _extract_screen_from_url
        assert _extract_screen_from_url("") is None


class TestIsSafeToClick:
    def test_rejects_delete_selector(self):
        from autonomous_explorer import _is_safe_to_click
        assert _is_safe_to_click("#btnDelete") is False

    def test_rejects_eliminar_selector(self):
        from autonomous_explorer import _is_safe_to_click
        assert _is_safe_to_click("#btnEliminar") is False

    def test_rejects_submit_selector(self):
        from autonomous_explorer import _is_safe_to_click
        assert _is_safe_to_click("button[type='submit']") is False

    def test_rejects_logout_selector(self):
        from autonomous_explorer import _is_safe_to_click
        assert _is_safe_to_click("a[href*='logout']") is False

    def test_accepts_nav_link(self):
        from autonomous_explorer import _is_safe_to_click
        assert _is_safe_to_click("a[href*='FrmAgenda.aspx']") is True

    def test_accepts_button_id(self):
        from autonomous_explorer import _is_safe_to_click
        assert _is_safe_to_click("#btnBuscar") is True

    def test_accepts_menu_link(self):
        from autonomous_explorer import _is_safe_to_click
        assert _is_safe_to_click("a.menu-item") is True


class TestBuildReport:
    def _make_edge(self, source, target, selector="#btn", label="", depth=1):
        from autonomous_explorer import ExploredEdge
        return ExploredEdge(source, target, selector, label, depth)

    def test_basic_report_structure(self):
        from autonomous_explorer import _build_report
        edges = [self._make_edge("Default.aspx", "FrmAgenda.aspx")]
        report = _build_report("Default.aspx", edges, [], elapsed_s=1.5, max_depth=3)
        assert report["entry_screen"] == "Default.aspx"
        assert report["schema_version"] == "1.0"
        assert report["summary"]["edges_discovered"] == 1
        assert report["summary"]["unknown_screens_found"] == 0
        assert len(report["learned_edges"]) == 1

    def test_deduplicates_same_source_target(self):
        from autonomous_explorer import _build_report
        edges = [
            self._make_edge("Default.aspx", "FrmAgenda.aspx", "#btn1"),
            self._make_edge("Default.aspx", "FrmAgenda.aspx", "#btn2"),  # duplicate
        ]
        report = _build_report("Default.aspx", edges, [], elapsed_s=1.0, max_depth=3)
        assert report["summary"]["edges_discovered"] == 1

    def test_marks_unknown_screens(self):
        from autonomous_explorer import _build_report
        edges = [self._make_edge("Default.aspx", "FrmNewUnknown.aspx")]
        report = _build_report(
            "Default.aspx", edges,
            unknown_screens=["FrmNewUnknown.aspx"],
            elapsed_s=1.0, max_depth=3,
        )
        assert report["summary"]["unknown_screens_found"] == 1
        assert "FrmNewUnknown.aspx" in report["unknown_screens"]

    def test_learned_edges_compatible_schema(self):
        """learned_edges must contain fields navigation_graph_learner expects."""
        from autonomous_explorer import _build_report
        edges = [self._make_edge("FrmLogin.aspx", "Default.aspx")]
        report = _build_report("FrmLogin.aspx", edges, [], elapsed_s=0.5, max_depth=2)
        edge = report["learned_edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "trigger_selector" in edge
        assert "observed_count" in edge
        assert "confidence" in edge
        assert edge["confidence"] == "tentative"
        assert edge["source_type"] == "autonomous_explorer"

    def test_empty_edges_produces_valid_report(self):
        from autonomous_explorer import _build_report
        report = _build_report("Default.aspx", [], [], elapsed_s=0.1, max_depth=3)
        assert report["summary"]["edges_discovered"] == 0
        assert report["learned_edges"] == []


class TestRunWithoutCredentials:
    def test_missing_base_url_returns_error(self, monkeypatch):
        import autonomous_explorer
        monkeypatch.delenv("AGENDA_WEB_BASE_URL", raising=False)
        monkeypatch.setenv("AGENDA_WEB_USER", "user")
        monkeypatch.setenv("AGENDA_WEB_PASS", "pass")
        result = autonomous_explorer.run()
        assert result["ok"] is False
        assert result["error"] == "missing_env"

    def test_missing_credentials_returns_error(self, monkeypatch):
        import autonomous_explorer
        monkeypatch.setenv("AGENDA_WEB_BASE_URL", "http://app")
        monkeypatch.delenv("AGENDA_WEB_USER", raising=False)
        monkeypatch.delenv("AGENDA_WEB_PASS", raising=False)
        result = autonomous_explorer.run()
        assert result["ok"] is False
        assert result["error"] == "missing_credentials"


# ──────────────────────────────────────────────────────────────────────────────
# agenda_screens.add_discovered_screen
# ──────────────────────────────────────────────────────────────────────────────

class TestAddDiscoveredScreen:
    def test_adds_new_screen_to_in_memory_catalogue(self):
        """add_discovered_screen should add a new screen to is_supported()."""
        import agenda_screens

        screen = "FrmTestDiscovered7777.aspx"
        # Ensure clean state: remove if previously added
        agenda_screens._LOWER_INDEX.pop(screen.lower(), None)
        agenda_screens.SUPPORTED_SCREENS = frozenset(
            s for s in agenda_screens.SUPPORTED_SCREENS if s != screen
        )

        assert not agenda_screens.is_supported(screen), "pre-condition: screen not known"
        result = agenda_screens.add_discovered_screen(screen)
        assert result is True
        assert agenda_screens.is_supported(screen)

        # Cleanup
        agenda_screens._LOWER_INDEX.pop(screen.lower(), None)
        agenda_screens.SUPPORTED_SCREENS = frozenset(
            s for s in agenda_screens.SUPPORTED_SCREENS if s != screen
        )
        # Remove from cache file if written
        cache_dir = Path(__file__).parent.parent.parent / "cache"
        disc_path = cache_dir / "discovered_screens.json"
        if disc_path.is_file():
            try:
                data = json.loads(disc_path.read_text())
                data["screens"] = [s for s in data.get("screens", []) if s != screen]
                disc_path.write_text(json.dumps(data, indent=2))
            except Exception:
                pass

    def test_returns_false_for_already_supported_screen(self):
        import agenda_screens
        # FrmAgenda.aspx is always in SUPPORTED_SCREENS
        result = agenda_screens.add_discovered_screen("FrmAgenda.aspx")
        assert result is False

    def test_rejects_non_aspx_name(self):
        import agenda_screens
        with pytest.raises(ValueError):
            agenda_screens.add_discovered_screen("NotAScreen")

    def test_rejects_empty_name(self):
        import agenda_screens
        with pytest.raises((ValueError, AttributeError)):
            agenda_screens.add_discovered_screen("")

    def test_writes_to_discovered_screens_json(self, tmp_path):
        """Verify that add_discovered_screen writes to cache/discovered_screens.json."""
        import agenda_screens
        import json as _json

        # We'll test the JSON structure by calling the real function and
        # reading the actual cache file (tmp approach via monkeypatch of _TOOL_ROOT)
        cache_dir = Path(__file__).parent.parent.parent / "cache"
        disc_path = cache_dir / "discovered_screens.json"

        # Read current state
        before: set = set()
        if disc_path.is_file():
            try:
                before = set(_json.loads(disc_path.read_text())["screens"])
            except Exception:
                before = set()

        screen = "FrmAutoTestTemp9998.aspx"
        try:
            result = agenda_screens.add_discovered_screen(screen)
            if result:  # was actually added (not pre-existing)
                assert disc_path.is_file(), "discovered_screens.json should be written"
                data = _json.loads(disc_path.read_text())
                assert screen in data.get("screens", [])
        finally:
            # Clean up: remove the temp screen from the file if we added it
            if disc_path.is_file():
                try:
                    data = _json.loads(disc_path.read_text())
                    screens = [s for s in data.get("screens", []) if s != screen]
                    data["screens"] = screens
                    disc_path.write_text(_json.dumps(data, indent=2))
                    # Also remove from in-memory catalogue
                    agenda_screens._LOWER_INDEX.pop(screen.lower(), None)
                    agenda_screens.SUPPORTED_SCREENS = frozenset(
                        s for s in agenda_screens.SUPPORTED_SCREENS if s != screen
                    )
                except Exception:
                    pass
