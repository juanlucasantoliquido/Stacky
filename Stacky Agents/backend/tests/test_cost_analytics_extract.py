"""Plan 142 F0 — Tests del extractor canónico de costo (services/cost_analytics.py).

PURO: sin DB, sin Flask. Reconcilia harness_telemetry / claude_telemetry / top-level
en una única CostRow con cost_kind clasificado (reported|estimated|nominal|unknown).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_empty_md_is_unknown():
    from services.cost_analytics import extract_cost_row

    row = extract_cost_row({})
    assert row.cost_usd is None
    assert row.cost_kind == "unknown"
    assert row.tokens_in is None
    assert row.tokens_out is None
    assert row.cache_read_tokens is None
    assert row.cache_savings_usd is None

    # md=None también debe degradar igual (guard `md = md or {}`).
    row_none = extract_cost_row(None)
    assert row_none.cost_kind == "unknown"
    assert row_none.cost_usd is None


def test_top_level_cost_is_reported():
    from services.cost_analytics import extract_cost_row

    md = {"runtime": "claude_code_cli", "model": "claude-sonnet-5", "cost_usd": 0.75}
    row = extract_cost_row(md)
    assert row.cost_usd == 0.75
    assert row.cost_kind == "reported"


def test_harness_estimated_flag():
    from services.cost_analytics import extract_cost_row

    md = {
        "runtime": "codex_cli",
        "harness_telemetry": {
            "total_cost_usd": 0.42,
            "cost_estimated": True,
            "input_tokens": 1000,
            "output_tokens": 200,
            "raw": {"model": "gpt-5"},
        },
    }
    row = extract_cost_row(md)
    assert row.cost_usd == 0.42
    assert row.cost_kind == "estimated"
    assert row.model == "gpt-5"
    assert row.tokens_in == 1000
    assert row.tokens_out == 200


def test_copilot_is_nominal_never_reported():
    from services.cost_analytics import extract_cost_row

    # Copilot con tokens pero SIN costo reportado -> nominal, hint vía pricing.
    md = {
        "runtime": "github_copilot",
        "model": "claude-sonnet-5",
        "harness_telemetry": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
    }
    row = extract_cost_row(md)
    assert row.cost_kind == "nominal"
    assert row.cost_usd == 18.0  # 1M*3 + 1M*15 = 18.0 (estimate_cost hint)

    # Incluso si por algún motivo trajera un total_cost_usd reportado, sigue "nominal"
    # (suscripción plana: NUNCA facturable, nunca "reported").
    md2 = {
        "runtime": "github_copilot",
        "harness_telemetry": {"total_cost_usd": 5.0, "cost_estimated": False},
    }
    row2 = extract_cost_row(md2)
    assert row2.cost_kind == "nominal"
    assert row2.cost_usd == 5.0


def test_codex_tokens_only_estimated():
    from services.cost_analytics import extract_cost_row

    md = {
        "runtime": "codex_cli",
        "model": "gpt-5",
        "harness_telemetry": {"input_tokens": 2000, "output_tokens": 500},
    }
    row = extract_cost_row(md)
    assert row.cost_kind == "estimated"
    assert row.cost_usd is not None and row.cost_usd > 0


def test_unknown_model_no_cost_returns_none_not_zero():
    from services.cost_analytics import extract_cost_row

    md = {"runtime": "codex_cli", "model": "totally-unknown-model-xyz",
          "harness_telemetry": {"input_tokens": 100, "output_tokens": 50}}
    row = extract_cost_row(md)
    assert row.cost_usd is None
    assert row.cost_kind == "unknown"


def test_cache_savings_computed_from_input_price():
    from services.cost_analytics import extract_cost_row

    md = {
        "runtime": "claude_code_cli",
        "model": "claude-sonnet-5",
        "harness_telemetry": {
            "total_cost_usd": 1.0,
            "cost_estimated": False,
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_tokens": 50000,
        },
    }
    row = extract_cost_row(md)
    # claude-sonnet-5 input price = 3.0 USD/Mtok -> 50000*3.0/1e6 = 0.15
    assert row.cache_savings_usd == 0.15


def test_precedence_harness_over_legacy_over_toplevel():
    from services.cost_analytics import extract_cost_row

    md = {
        "runtime": "claude_code_cli",
        "cost_usd": 9.99,  # top-level (debe perder)
        "claude_telemetry": {"total_cost_usd": 5.55},  # legacy (debe perder)
        "harness_telemetry": {"total_cost_usd": 1.23, "cost_estimated": False},  # gana
    }
    row = extract_cost_row(md)
    assert row.cost_usd == 1.23
    assert row.cost_kind == "reported"


def test_malformed_harness_cost_falls_to_estimated_or_unknown():
    from services.cost_analytics import extract_cost_row

    # No-numérico + tokens/modelo presentes -> _as_float da None -> degrade a "estimated".
    md_with_tokens = {
        "runtime": "codex_cli",
        "model": "gpt-5",
        "harness_telemetry": {
            "total_cost_usd": "not-a-number",
            "input_tokens": 1000,
            "output_tokens": 200,
        },
    }
    row = extract_cost_row(md_with_tokens)
    assert row.cost_kind == "estimated"
    assert row.cost_usd is not None

    # No-numérico + sin tokens/modelo -> no hay forma de estimar -> "unknown", NUNCA 0.0.
    md_no_tokens = {
        "runtime": "codex_cli",
        "harness_telemetry": {"total_cost_usd": "not-a-number"},
    }
    row2 = extract_cost_row(md_no_tokens)
    assert row2.cost_kind == "unknown"
    assert row2.cost_usd is None
