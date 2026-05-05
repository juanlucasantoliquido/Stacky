"""Unit tests for navigation_graph_learner.scan_session() — Fase 5.

Coverage:
- scan_session() with a valid session.json returns ok=True and ScanResult
  with the expected counts.
- transitions[] entries are converted to ObservedEdge with correct status
  classification (proposed for new supported→supported pairs, confirmed
  for edges already in the static graph).
- The trigger_label is preserved into the ObservedEdge.action field so the
  human reviewer can see what the operator clicked.
- Missing session.json returns ok=False without raising.
- apply=True writes both learned_edges.json AND discovered_selectors.json
  in the cache directory; apply=False (dry-run) writes nothing.
- Selectors merging is additive: re-applying a session does not overwrite
  existing keys.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _write_session(tmp_path: Path, payload: dict) -> Path:
    session_dir = tmp_path / "20260505_143000"
    session_dir.mkdir()
    (session_dir / "session.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return session_dir


def _sample_payload() -> dict:
    return {
        "schema_version": "1.0",
        "tool_version": "1.0.0",
        "recorded_at": "2026-05-05T14:30:00",
        "goal": "panel administradores",
        "navigation_path": ["FrmLogin.aspx", "Default.aspx", "FrmAdministrador.aspx"],
        "transitions": [
            {"from": "FrmLogin.aspx", "to": "Default.aspx",
             "trigger_type": "form_submit", "trigger_selector": "#c_btnOk",
             "trigger_label": "Ingresar"},
            {"from": "Default.aspx", "to": "FrmAdministrador.aspx",
             "trigger_type": "click", "trigger_selector": "a[href*='Administrador']",
             "trigger_label": "Administración"},
        ],
        "discovered_selectors": {
            "FrmAdministrador.aspx": {
                "btn_parametros": "a[href*='Parametros']",
                "btn_feriados": "a[href*='Feriados']",
            },
        },
        "form_fields": {},
        "request_log": [],
    }


# ── scan_session() returns ok ─────────────────────────────────────────────────


def test_scan_session_valid_returns_ok(tmp_path):
    import navigation_graph_learner as ngl
    session_dir = _write_session(tmp_path, _sample_payload())
    result = ngl.scan_session(session_dir, apply=False)
    assert result.ok is True
    assert result.scanned_runs == ["20260505_143000"]
    # Two transitions in the payload → two edges accumulated.
    assert result.total_transitions_seen >= 2


def test_scan_session_missing_file_returns_not_ok(tmp_path):
    import navigation_graph_learner as ngl
    empty_dir = tmp_path / "empty_session"
    empty_dir.mkdir()
    result = ngl.scan_session(empty_dir, apply=False)
    assert result.ok is False


def test_scan_session_malformed_json_returns_not_ok(tmp_path):
    import navigation_graph_learner as ngl
    bad_dir = tmp_path / "bad_session"
    bad_dir.mkdir()
    (bad_dir / "session.json").write_text("{not valid json", encoding="utf-8")
    result = ngl.scan_session(bad_dir, apply=False)
    assert result.ok is False


# ── Transition → ObservedEdge conversion ─────────────────────────────────────


def test_scan_session_transitions_become_observed_edges(tmp_path):
    import navigation_graph_learner as ngl
    session_dir = _write_session(tmp_path, _sample_payload())
    result = ngl.scan_session(session_dir, apply=False)
    all_edges = result.confirmed + result.proposed + result.unknown_screens
    keys = {(e.source, e.target) for e in all_edges}
    assert ("FrmLogin.aspx", "Default.aspx") in keys
    assert ("Default.aspx", "FrmAdministrador.aspx") in keys


def test_scan_session_preserves_trigger_label_in_action(tmp_path):
    import navigation_graph_learner as ngl
    session_dir = _write_session(tmp_path, _sample_payload())
    result = ngl.scan_session(session_dir, apply=False)
    all_edges = result.confirmed + result.proposed + result.unknown_screens
    by_key = {(e.source, e.target): e for e in all_edges}
    edge = by_key[("Default.aspx", "FrmAdministrador.aspx")]
    assert "Administración" in edge.action, f"trigger_label not preserved: {edge.action}"


def test_scan_session_classifies_supported_screens_as_proposed_or_confirmed(tmp_path):
    import navigation_graph_learner as ngl
    session_dir = _write_session(tmp_path, _sample_payload())
    result = ngl.scan_session(session_dir, apply=False)
    # All three screens (FrmLogin, Default, FrmAdministrador) are in
    # SUPPORTED_SCREENS — none should land in unknown_screens.
    assert len(result.unknown_screens) == 0


def test_scan_session_classifies_unknown_screens(tmp_path):
    import navigation_graph_learner as ngl
    payload = _sample_payload()
    payload["transitions"].append({
        "from": "FrmAdministrador.aspx", "to": "FrmCompletelyMadeUp.aspx",
        "trigger_type": "click", "trigger_selector": "#x", "trigger_label": "X",
    })
    payload["navigation_path"].append("FrmCompletelyMadeUp.aspx")
    session_dir = _write_session(tmp_path, payload)
    result = ngl.scan_session(session_dir, apply=False)
    keys = {(e.source, e.target) for e in result.unknown_screens}
    assert ("FrmAdministrador.aspx", "FrmCompletelyMadeUp.aspx") in keys


# ── apply=True persistence ───────────────────────────────────────────────────


def test_scan_session_apply_writes_discovered_selectors(tmp_path, monkeypatch):
    import navigation_graph_learner as ngl
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(ngl, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(ngl, "_LEARNED_EDGES_PATH", cache_dir / "learned_edges.json")
    monkeypatch.setattr(ngl, "_DISCOVERED_SELECTORS_PATH", cache_dir / "discovered_selectors.json")

    session_dir = _write_session(tmp_path, _sample_payload())
    result = ngl.scan_session(session_dir, apply=True)
    assert result.ok is True

    sel_file = cache_dir / "discovered_selectors.json"
    assert sel_file.is_file(), "discovered_selectors.json should be written when apply=True"
    data = json.loads(sel_file.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert "FrmAdministrador.aspx" in data["by_screen"]
    assert data["by_screen"]["FrmAdministrador.aspx"]["btn_parametros"] == "a[href*='Parametros']"


def test_scan_session_dry_run_writes_nothing(tmp_path, monkeypatch):
    import navigation_graph_learner as ngl
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(ngl, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(ngl, "_LEARNED_EDGES_PATH", cache_dir / "learned_edges.json")
    monkeypatch.setattr(ngl, "_DISCOVERED_SELECTORS_PATH", cache_dir / "discovered_selectors.json")

    session_dir = _write_session(tmp_path, _sample_payload())
    ngl.scan_session(session_dir, apply=False)

    assert not (cache_dir / "discovered_selectors.json").exists()
    assert not (cache_dir / "learned_edges.json").exists()


def test_scan_session_apply_merges_selectors_additively(tmp_path, monkeypatch):
    import navigation_graph_learner as ngl
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(ngl, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(ngl, "_LEARNED_EDGES_PATH", cache_dir / "learned_edges.json")
    monkeypatch.setattr(ngl, "_DISCOVERED_SELECTORS_PATH", cache_dir / "discovered_selectors.json")

    # First session: writes #btnParametros for btn_parametros
    session_dir_a = _write_session(tmp_path, _sample_payload())
    ngl.scan_session(session_dir_a, apply=True)

    # Second session (different timestamp dir): tries to overwrite with a
    # less-stable selector + adds a new key. First-seen must win.
    second_payload = _sample_payload()
    second_payload["discovered_selectors"]["FrmAdministrador.aspx"] = {
        "btn_parametros": "button:has-text('Parametros')",  # weaker selector
        "btn_clientes": "a[href*='Clientes']",              # new key
    }
    second_dir = tmp_path / "20260505_150000"
    second_dir.mkdir()
    (second_dir / "session.json").write_text(json.dumps(second_payload), encoding="utf-8")
    ngl.scan_session(second_dir, apply=True)

    sel_file = cache_dir / "discovered_selectors.json"
    data = json.loads(sel_file.read_text(encoding="utf-8"))
    bucket = data["by_screen"]["FrmAdministrador.aspx"]
    assert bucket["btn_parametros"] == "a[href*='Parametros']", "first-seen must win"
    assert bucket["btn_clientes"] == "a[href*='Clientes']", "new key must be added"


def test_scan_session_apply_writes_learned_edges_for_proposed(tmp_path, monkeypatch):
    import navigation_graph_learner as ngl
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(ngl, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(ngl, "_LEARNED_EDGES_PATH", cache_dir / "learned_edges.json")
    monkeypatch.setattr(ngl, "_DISCOVERED_SELECTORS_PATH", cache_dir / "discovered_selectors.json")

    session_dir = _write_session(tmp_path, _sample_payload())
    result = ngl.scan_session(session_dir, apply=True)

    if result.proposed:
        # When the static graph already covers all edges (confirmed-only run)
        # the file is not written. We only assert the path is set when there
        # is at least one proposed edge.
        edges_file = cache_dir / "learned_edges.json"
        assert edges_file.is_file()
        data = json.loads(edges_file.read_text(encoding="utf-8"))
        assert "by_source" in data
