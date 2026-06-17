"""V0.5 — Tests de estimación de costo en telemetría (harness/telemetry.py)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("STACKY_PRICING_JSON", raising=False)
    yield


def test_codex_event_without_cost_gets_estimated():
    from harness.telemetry import from_codex_event

    event = {
        "type": "result",
        "session_id": "s1",
        "model": "claude-sonnet-4-6",
        "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
        # sin total_cost_usd
    }
    t = from_codex_event(event)
    assert t.total_cost_usd == 3.0
    assert t.cost_estimated is True
    assert t.to_dict()["cost_estimated"] is True


def test_reported_cost_always_wins():
    from harness.telemetry import from_codex_event

    event = {
        "type": "result",
        "model": "claude-sonnet-4-6",
        "total_cost_usd": 0.5,
        "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
    }
    t = from_codex_event(event)
    assert t.total_cost_usd == 0.5
    assert t.cost_estimated is False


def test_unknown_model_no_cost():
    from harness.telemetry import from_codex_event

    event = {
        "type": "result",
        "model": "gemini-x",
        "usage": {"input_tokens": 1000, "output_tokens": 1000},
    }
    t = from_codex_event(event)
    assert t.total_cost_usd is None
    assert t.cost_estimated is False


def test_claude_stream_reported_cost_not_overwritten():
    from harness.telemetry import from_claude_stream

    t = from_claude_stream({
        "session_id": "s",
        "model": "claude-sonnet-4-6",
        "total_cost_usd": 1.23,
        "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
    })
    assert t.total_cost_usd == 1.23
    assert t.cost_estimated is False
