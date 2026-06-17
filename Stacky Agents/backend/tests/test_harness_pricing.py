"""V0.5 — Tests del pricing fallback (harness/pricing.py)."""
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
def _clean_env(monkeypatch):
    monkeypatch.delenv("STACKY_PRICING_JSON", raising=False)
    yield


def test_estimate_basic_sonnet():
    from harness.pricing import estimate_cost

    # 1M input @ $3 + 1M output @ $15 = 18.0
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000) == 18.0


def test_estimate_haiku():
    from harness.pricing import estimate_cost

    # 1M input @ $1 + 1M output @ $5 = 6.0
    assert estimate_cost("claude-haiku-4-5", 1_000_000, 1_000_000) == 6.0


def test_longest_prefix_wins():
    from harness.pricing import estimate_cost

    # "claude-sonnet-4" debe ganar sobre cualquier prefijo más corto.
    cost = estimate_cost("claude-sonnet-4-6-20251114", 1_000_000, 0)
    assert cost == 3.0


def test_unknown_model_returns_none():
    from harness.pricing import estimate_cost

    assert estimate_cost("gemini-ultra", 1000, 1000) is None


def test_no_model_returns_none():
    from harness.pricing import estimate_cost

    assert estimate_cost(None, 1000, 1000) is None


def test_no_tokens_returns_none():
    from harness.pricing import estimate_cost

    assert estimate_cost("claude-sonnet-4-6", None, None) is None


def test_partial_tokens_ok():
    from harness.pricing import estimate_cost

    # solo output: 2M @ $15 = 30.0
    assert estimate_cost("claude-sonnet-4-6", None, 2_000_000) == 30.0


def test_env_override(monkeypatch):
    from harness.pricing import estimate_cost

    monkeypatch.setenv("STACKY_PRICING_JSON", '{"claude-sonnet-4": [6.0, 30.0]}')
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 0) == 6.0


def test_env_override_adds_new_model(monkeypatch):
    from harness.pricing import estimate_cost

    monkeypatch.setenv("STACKY_PRICING_JSON", '{"gemini-2": [0.5, 2.0]}')
    assert estimate_cost("gemini-2-flash", 1_000_000, 0) == 0.5
    # default sigue funcionando
    assert estimate_cost("claude-haiku-4-5", 1_000_000, 0) == 1.0


def test_env_malformed_falls_back(monkeypatch):
    from harness.pricing import estimate_cost

    monkeypatch.setenv("STACKY_PRICING_JSON", "{not valid json")
    # no crashea; usa default
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 0) == 3.0


def test_env_malformed_shape_falls_back(monkeypatch):
    from harness.pricing import estimate_cost

    monkeypatch.setenv("STACKY_PRICING_JSON", '{"claude-sonnet-4": "expensive"}')
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 0) == 3.0
