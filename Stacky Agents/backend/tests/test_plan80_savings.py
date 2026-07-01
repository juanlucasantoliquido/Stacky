"""Plan 80 F5 — estimate_query_savings + aggregate_savings + GET /savings.

Casos:
  1. estimate_query_savings(0, 0) -> ceros, sin div/0.
  2. estimate_query_savings(4000, 400) -> tokens_baseline=1000, tokens_mcp=100,
     delta=900, delta_pct=0.9.
  3. estimate_query_savings(400, 4000) (MCP peor) -> delta y delta_pct negativos.
  4. Negativos clamped: estimate_query_savings(-10, -10) -> 0,0,0,0.0.
  5. aggregate_savings() -> samples=0, delta_pct is None.
  6. GET /api/codebase-memory-mcp/savings -> 200, samples==0, delta_pct is None.
  7. Pureza (sin red): monkeypatch socket.socket.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.codebase_memory_mcp_wiring import (  # noqa: E402
    aggregate_savings,
    estimate_query_savings,
)


def test_estimate_zero_baseline_no_divzero():
    result = estimate_query_savings(0, 0)
    assert result == {"tokens_baseline": 0, "tokens_mcp": 0, "delta": 0, "delta_pct": 0.0}


def test_estimate_typical_savings():
    result = estimate_query_savings(4000, 400)
    assert result["tokens_baseline"] == 1000
    assert result["tokens_mcp"] == 100
    assert result["delta"] == 900
    assert result["delta_pct"] == 0.9


def test_estimate_mcp_worse_than_baseline():
    result = estimate_query_savings(400, 4000)
    assert result["delta"] < 0
    assert result["delta_pct"] < 0


def test_estimate_negative_inputs_clamped():
    result = estimate_query_savings(-10, -10)
    assert result == {"tokens_baseline": 0, "tokens_mcp": 0, "delta": 0, "delta_pct": 0.0}


def test_aggregate_savings_honest_shape():
    result = aggregate_savings()
    assert result["samples"] == 0
    assert result["delta_pct"] is None


def test_savings_endpoint_returns_honest_shape(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/api/codebase-memory-mcp/savings")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["samples"] == 0
    assert body["delta_pct"] is None


def test_pure_functions_no_network(monkeypatch):
    def _raise(*args, **kwargs):
        raise AssertionError("no debería abrir sockets")

    monkeypatch.setattr("socket.socket", _raise)
    assert estimate_query_savings(100, 10)["delta"] == 23
    assert aggregate_savings()["samples"] == 0
