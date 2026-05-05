"""Unit tests for session_recorder.py — Fase 5 demo-driven learning recorder.

Coverage:
- _extract_screen_from_url() handles .aspx URLs, query strings, and rejects
  non-.aspx URLs (assets, API calls, root path).
- _dedupe_consecutive() collapses repeated entries so the navigation_path
  produced by framenavigated bursts is clean.
- _build_session_payload() produces a dict with the documented schema fields
  and round-trips cleanly through json.dumps/json.loads.
- _RecorderState integration: recording transitions populates navigation_path
  in order, attributes the most recent interaction to the next transition,
  and merges snapshots without overwriting previously-seen selectors.

NOTE: The async _run_recording() function is NOT covered here — it requires
a live Playwright browser. Integration coverage will live separately.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")


# ── _extract_screen_from_url ─────────────────────────────────────────────────


def test_extract_screen_handles_query_string():
    import session_recorder as sr
    assert sr._extract_screen_from_url("http://app/FrmAdministrador.aspx?q=1") == "FrmAdministrador.aspx"


def test_extract_screen_handles_no_query():
    import session_recorder as sr
    assert sr._extract_screen_from_url("http://app/FrmAgenda.aspx") == "FrmAgenda.aspx"


def test_extract_screen_handles_fragment():
    import session_recorder as sr
    assert sr._extract_screen_from_url("http://app/FrmAgenda.aspx#tab=1") == "FrmAgenda.aspx"


def test_extract_screen_handles_query_and_fragment():
    import session_recorder as sr
    assert sr._extract_screen_from_url("http://app/FrmJDemanda.aspx?id=99#top") == "FrmJDemanda.aspx"


def test_extract_screen_rejects_static_assets():
    import session_recorder as sr
    assert sr._extract_screen_from_url("http://app/static/bundle.js") is None
    assert sr._extract_screen_from_url("http://app/Content/site.css") is None
    assert sr._extract_screen_from_url("http://app/img/logo.png") is None


def test_extract_screen_rejects_root_and_empty():
    import session_recorder as sr
    assert sr._extract_screen_from_url("") is None
    assert sr._extract_screen_from_url("http://app/") is None


def test_extract_screen_case_insensitive_extension():
    # AIS ASP.NET sometimes emits uppercase .ASPX in URLs after server-side
    # rewrites — must not drop these silently.
    import session_recorder as sr
    assert sr._extract_screen_from_url("http://app/FrmAgenda.ASPX") == "FrmAgenda.ASPX"


# ── _dedupe_consecutive ──────────────────────────────────────────────────────


def test_dedupe_collapses_consecutive():
    import session_recorder as sr
    assert sr._dedupe_consecutive(["A", "A", "B"]) == ["A", "B"]


def test_dedupe_preserves_distinct_repeats():
    # A→B→A is a real backtrack and must NOT be collapsed.
    import session_recorder as sr
    assert sr._dedupe_consecutive(["A", "B", "A"]) == ["A", "B", "A"]


def test_dedupe_multi_run():
    import session_recorder as sr
    assert sr._dedupe_consecutive(["A", "A", "A", "B", "B", "C", "C", "C", "D"]) == ["A", "B", "C", "D"]


def test_dedupe_empty_and_falsy():
    import session_recorder as sr
    assert sr._dedupe_consecutive([]) == []
    assert sr._dedupe_consecutive(["", None, "A"]) == ["A"]


# ── _build_session_payload ───────────────────────────────────────────────────


def test_session_payload_schema_round_trip():
    import session_recorder as sr
    payload = sr._build_session_payload(
        goal="panel administradores",
        started_at="2026-05-05T14:30:00",
        navigation_path=["FrmLogin.aspx", "Default.aspx", "FrmAdministrador.aspx"],
        transitions=[
            {"from": "FrmLogin.aspx", "to": "Default.aspx",
             "trigger_type": "form_submit", "trigger_selector": "#c_btnOk",
             "trigger_label": "Ingresar"},
            {"from": "Default.aspx", "to": "FrmAdministrador.aspx",
             "trigger_type": "click", "trigger_selector": "a[href*='Administrador']",
             "trigger_label": "Administración"},
        ],
        discovered_selectors={
            "FrmAdministrador.aspx": {
                "btn_parametros": "a[href*='Parametros']",
                "btn_feriados": "a[href*='Feriados']",
            },
        },
        form_fields={},
        request_log=[],
    )
    # Round-trips cleanly
    serialized = json.dumps(payload, ensure_ascii=False)
    reloaded = json.loads(serialized)
    assert reloaded["schema_version"] == "1.0"
    assert reloaded["goal"] == "panel administradores"
    assert reloaded["navigation_path"][0] == "FrmLogin.aspx"
    assert reloaded["navigation_path"][-1] == "FrmAdministrador.aspx"
    assert len(reloaded["transitions"]) == 2
    assert reloaded["transitions"][0]["trigger_selector"] == "#c_btnOk"
    assert "FrmAdministrador.aspx" in reloaded["discovered_selectors"]


def test_session_payload_required_fields():
    import session_recorder as sr
    payload = sr._build_session_payload(
        goal="",
        started_at="2026-05-05T14:30:00",
        navigation_path=[],
        transitions=[],
        discovered_selectors={},
        form_fields={},
        request_log=[],
    )
    for required in (
        "schema_version", "tool_version", "recorded_at", "goal",
        "navigation_path", "transitions", "discovered_selectors",
        "form_fields", "request_log",
    ):
        assert required in payload, f"missing required field: {required}"


# ── _RecorderState integration ──────────────────────────────────────────────


def test_recorder_state_records_screens_and_transitions_in_order():
    import session_recorder as sr
    state = sr._RecorderState()
    assert state.record_screen("FrmLogin.aspx") is None
    prev = state.record_screen("Default.aspx")
    assert prev == "FrmLogin.aspx"
    state.record_transition(prev, "Default.aspx")
    prev2 = state.record_screen("FrmAdministrador.aspx")
    assert prev2 == "Default.aspx"
    state.record_transition(prev2, "FrmAdministrador.aspx")
    assert state.navigation_path == ["FrmLogin.aspx", "Default.aspx", "FrmAdministrador.aspx"]
    assert len(state.transitions) == 2


def test_recorder_state_attributes_interaction_to_next_transition():
    import session_recorder as sr
    state = sr._RecorderState()
    state.record_screen("FrmLogin.aspx")
    # Operator clicks "Administración" link
    state.last_interaction = {"selector": "a[href*='Administrador']", "label": "Administración"}
    prev = state.record_screen("FrmAdministrador.aspx")
    state.record_transition(prev, "FrmAdministrador.aspx")
    edge = state.transitions[-1]
    assert edge["trigger_type"] == "click"
    assert edge["trigger_selector"] == "a[href*='Administrador']"
    assert edge["trigger_label"] == "Administración"
    # Last interaction is consumed — should not bleed into the next transition.
    assert state.last_interaction is None


def test_recorder_state_dedupes_consecutive_screen_visits():
    import session_recorder as sr
    state = sr._RecorderState()
    state.record_screen("FrmAgenda.aspx")
    # Re-firing framenavigated for the same URL must not duplicate.
    assert state.record_screen("FrmAgenda.aspx") is None
    assert state.navigation_path == ["FrmAgenda.aspx"]


def test_recorder_state_merge_snapshot_first_seen_wins():
    import session_recorder as sr
    state = sr._RecorderState()
    state.merge_snapshot("FrmAgenda.aspx", {
        "buttons": {"btn_buscar": "#btnBuscar"},
        "links": {},
        "inputs": {},
    })
    # Second snapshot tries to overwrite with a less-stable selector.
    state.merge_snapshot("FrmAgenda.aspx", {
        "buttons": {"btn_buscar": "button:has-text('Buscar')",
                    "btn_limpiar": "#btnLimpiar"},
        "links": {},
        "inputs": {},
    })
    bucket = state.discovered_selectors["FrmAgenda.aspx"]
    assert bucket["btn_buscar"] == "#btnBuscar", "first-seen selector should win"
    assert bucket["btn_limpiar"] == "#btnLimpiar", "new keys must still be added"
