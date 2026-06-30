"""Plan 44 F1 — Agregador puro de telemetría de grounding."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _agg(*args, **kwargs):
    from services.grounding_observatory import aggregate_grounding
    return aggregate_grounding(*args, **kwargs)


def test_empty_returns_zeroed():
    r = _agg([])
    assert r["total_epics"] == 0
    assert r["avg_confidence"] is None
    assert r["grounding_warning_rate"] == 0.0
    assert r["runtime_coverage"] == []
    assert r["confidence_trend"] == []


def test_counts_warnings():
    r = _agg([
        {"warnings": ["x"]},
        {"warnings": []},
        {"warnings": None},
    ])
    assert r["epics_with_warnings"] == 1
    assert r["grounding_warning_rate"] == pytest.approx(1 / 3)


def test_avg_confidence_ignores_none():
    r = _agg([{"confidence": 0.8}, {"confidence": None}, {"confidence": 0.6}])
    assert r["avg_confidence"] == pytest.approx(0.7)


def test_classifies_modules_and_processes():
    r = _agg([{"cited_modules": ["módulo 12", "proceso CargaNomina", "módulo 12"]}])
    assert r["top_cited_modules"] == [{"name": "módulo 12", "count": 2}]
    assert r["top_cited_processes"] == [{"name": "proceso CargaNomina", "count": 1}]


def test_no_prefix_all_classified_as_module():
    r = _agg([{"cited_modules": ["CargaNomina", "IncHost"]}])
    assert r["top_cited_processes"] == []
    names = {m["name"] for m in r["top_cited_modules"]}
    assert names == {"CargaNomina", "IncHost"}


def test_trend_preserves_order_and_nulls():
    r = _agg([{"confidence": 0.5}, {"confidence": None}, {"confidence": 0.9}])
    assert r["confidence_trend"] == [0.5, None, 0.9]


def test_trend_caps_at_20():
    r = _agg([{"confidence": 0.5} for _ in range(25)])
    assert len(r["confidence_trend"]) == 20


def test_top_caps_at_10():
    summaries = [{"cited_modules": [f"módulo M{i}"]} for i in range(15)]
    r = _agg(summaries)
    assert len(r["top_cited_modules"]) == 10


def test_runtime_coverage_populated():
    r = _agg([{}, {}, {}], runtimes=["claude_code_cli", "claude_code_cli", "codex_cli"])
    assert r["runtime_coverage"] == ["claude_code_cli", "codex_cli"]


def test_runtime_coverage_empty_when_none():
    r = _agg([{}], runtimes=None)
    assert r["runtime_coverage"] == []
