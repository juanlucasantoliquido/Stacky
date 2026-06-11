"""H1.3 — Tests de harness.telemetry."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_from_claude_stream_extracts_fields():
    from harness.telemetry import from_claude_stream

    stream = {
        "session_id": "sess-abc",
        "num_turns": 5,
        "total_cost_usd": 0.12,
        "is_error": False,
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 800,
        },
    }
    t = from_claude_stream(stream)
    assert t.runtime == "claude_code_cli"
    assert t.session_id == "sess-abc"
    assert t.num_turns == 5
    assert t.total_cost_usd == 0.12
    assert t.input_tokens == 1000
    assert t.output_tokens == 200
    assert t.cache_read_tokens == 800
    assert t.raw["is_error"] is False


def test_from_codex_event_extracts_session_id():
    from harness.telemetry import from_codex_event

    event = {"type": "system", "session_id": "codex-xyz", "num_turns": 3}
    t = from_codex_event(event)
    assert t.runtime == "codex_cli"
    assert t.session_id == "codex-xyz"
    assert t.num_turns == 3


def test_from_codex_event_extracts_nested_session_id():
    from harness.telemetry import from_codex_event

    event = {"type": "event", "item": {"session_id": "nested-sess"}}
    t = from_codex_event(event)
    assert t.session_id == "nested-sess"


def test_from_codex_event_unknown_schema_stores_raw():
    from harness.telemetry import from_codex_event

    event = {"type": "unknown", "custom_field": "value", "nested": {"x": 1}}
    t = from_codex_event(event)
    assert t.raw["custom_field"] == "value"
    assert t.session_id is None


def test_run_telemetry_to_dict():
    from harness.telemetry import RunTelemetry

    t = RunTelemetry(
        runtime="codex_cli",
        session_id="s1",
        num_turns=2,
        total_cost_usd=0.05,
        input_tokens=100,
        output_tokens=50,
    )
    d = t.to_dict()
    assert d["session_id"] == "s1"
    assert d["runtime"] == "codex_cli"
    assert "raw" not in d  # raw no va en to_dict


def _make_fake_scope(fake_row):
    class _FakeSession:
        def get(self, model, eid):
            return fake_row

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return _FakeSession


def test_persist_writes_harness_telemetry(monkeypatch):
    """persist() escribe harness_telemetry en metadata de la ejecución."""
    import harness.telemetry as ht
    from harness.telemetry import RunTelemetry, persist

    class _FakeRow:
        def __init__(self):
            self.metadata_dict = {}

    fake_row = _FakeRow()
    FakeSession = _make_fake_scope(fake_row)
    monkeypatch.setattr(ht, "session_scope", lambda: FakeSession())

    t = RunTelemetry(runtime="codex_cli", session_id="sess-x")
    persist(42, t)

    assert "harness_telemetry" in fake_row.metadata_dict
    assert fake_row.metadata_dict["harness_telemetry"]["session_id"] == "sess-x"
    # codex no escribe claude_telemetry
    assert "claude_telemetry" not in fake_row.metadata_dict


def test_persist_claude_writes_legacy_key(monkeypatch):
    """claude_code_cli también escribe claude_telemetry para retro-compat."""
    import harness.telemetry as ht
    from harness.telemetry import RunTelemetry, persist

    class _FakeRow:
        def __init__(self):
            self.metadata_dict = {}

    fake_row = _FakeRow()
    FakeSession = _make_fake_scope(fake_row)
    monkeypatch.setattr(ht, "session_scope", lambda: FakeSession())

    t = RunTelemetry(
        runtime="claude_code_cli",
        session_id="c-sess",
        raw={"session_id": "c-sess", "num_turns": 3},
    )
    persist(99, t)

    assert "harness_telemetry" in fake_row.metadata_dict
    assert "claude_telemetry" in fake_row.metadata_dict
    # session_id no va en claude_telemetry (raw - session_id)
    assert "session_id" not in fake_row.metadata_dict["claude_telemetry"]
    assert fake_row.metadata_dict["claude_telemetry"]["num_turns"] == 3
