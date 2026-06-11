"""H2.2 — Tests de telemetría codex via harness.telemetry.from_codex_event.

Usa fixtures JSONL tomados del código _extract_codex_session_id existente.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

# Fixtures JSONL que emite codex (basados en _extract_codex_session_id)
_SYSTEM_INIT_LINE = json.dumps({
    "type": "system",
    "subtype": "init",
    "session_id": "codex-sess-001",
})

_RESULT_WITH_USAGE = json.dumps({
    "type": "result",
    "session_id": "codex-sess-001",
    "num_turns": 4,
    "total_cost_usd": 0.08,
    "usage": {
        "input_tokens": 500,
        "output_tokens": 120,
        "cache_read_input_tokens": 300,
    },
})

_ITEM_EVENT = json.dumps({
    "type": "item",
    "item": {
        "type": "message",
        "session_id": "codex-sess-nested",
        "text": "hola",
    },
})

_UNKNOWN_EVENT = json.dumps({
    "type": "custom_event_xyz",
    "data": {"something": True},
})


def test_from_codex_event_session_id_top_level():
    from harness.telemetry import from_codex_event

    event = json.loads(_SYSTEM_INIT_LINE)
    t = from_codex_event(event)
    assert t.session_id == "codex-sess-001"
    assert t.runtime == "codex_cli"


def test_from_codex_event_with_usage():
    from harness.telemetry import from_codex_event

    event = json.loads(_RESULT_WITH_USAGE)
    t = from_codex_event(event)
    assert t.session_id == "codex-sess-001"
    assert t.num_turns == 4
    assert t.total_cost_usd == 0.08
    assert t.input_tokens == 500
    assert t.output_tokens == 120
    assert t.cache_read_tokens == 300


def test_from_codex_event_nested_session_id():
    from harness.telemetry import from_codex_event

    event = json.loads(_ITEM_EVENT)
    t = from_codex_event(event)
    assert t.session_id == "codex-sess-nested"


def test_from_codex_event_unknown_stores_raw():
    from harness.telemetry import from_codex_event

    event = json.loads(_UNKNOWN_EVENT)
    t = from_codex_event(event)
    assert t.session_id is None
    assert t.raw["data"]["something"] is True


def test_harness_telemetry_has_session_id_after_run(monkeypatch):
    """Aceptación H2.2: metadata de un run codex contiene harness_telemetry con session_id."""
    import harness.telemetry as ht
    from harness.telemetry import RunTelemetry, persist

    class _FakeRow:
        def __init__(self):
            self.metadata_dict = {}

    fake_row = _FakeRow()

    class _FakeSession:
        def get(self, model, eid):
            return fake_row

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(ht, "session_scope", lambda: _FakeSession())

    t = from_codex_event_helper("codex-sess-xyz")
    persist(1, t)

    assert "harness_telemetry" in fake_row.metadata_dict
    assert fake_row.metadata_dict["harness_telemetry"]["session_id"] == "codex-sess-xyz"


def from_codex_event_helper(session_id: str):
    from harness.telemetry import from_codex_event
    return from_codex_event({"type": "system", "session_id": session_id})
