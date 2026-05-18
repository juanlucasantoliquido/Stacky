"""Tests del cliente LLM PM con tracking de tokens — Fase 2.

Sin red. Backend mock siempre, para que tests/evals sean determinísticos
y verificables sin API key ni dependencias externas.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
os.environ["STACKY_PM_LLM_BACKEND"] = "mock"


@pytest.fixture(autouse=True)
def _pm_tables_ready():
    from db import init_db, session_scope
    from services.pm.models import PmAiUsage

    init_db()
    with session_scope() as session:
        session.query(PmAiUsage).delete()
    yield
    with session_scope() as session:
        session.query(PmAiUsage).delete()


def _spec(**overrides):
    from services.pm.pm_llm_client import LLMCallSpec
    base = dict(
        project="TestPM",
        agent_kind="sentiment",
        prompt_type="comment_sentiment_v1",
        model="claude-haiku-4-5",
        system="Sos un clasificador de sentimientos.",
        user="Comentario: el ticket está listo para QA",
        max_output_tokens=256,
        temperature=0.0,
        fixture_id=None,
        expect_json=True,
    )
    base.update(overrides)
    return LLMCallSpec(**base)


# ── PII guard ──────────────────────────────────────────────────────────────────

def test_blocks_raw_email_in_input():
    from services.pm.pm_llm_client import PiiLeakError, call_llm
    with pytest.raises(PiiLeakError):
        # call_llm checks PII before invoking — pero también persiste? No,
        # bloquea antes de cualquier IO. Necesitamos invocar el guard.
        call_llm(_spec(user="Comentario de juan@empresa.com sobre el ticket"))


def test_blocks_raw_cuit_in_system():
    from services.pm.pm_llm_client import PiiLeakError, call_llm
    with pytest.raises(PiiLeakError):
        call_llm(_spec(system="Contexto: cliente 20-12345678-9 ..."))


def test_accepts_masked_pii_tokens():
    from services.pm.pm_llm_client import call_llm
    # ZZZ_PII_EMAIL_1 NO es un email crudo — debe pasar
    result = call_llm(_spec(user="El usuario ZZZ_PII_EMAIL_1 reportó el bug"))
    assert result.success is True


# ── mock backend + tracking ────────────────────────────────────────────────────

def test_mock_call_persists_usage_row():
    from db import session_scope
    from services.pm.models import PmAiUsage
    from services.pm.pm_llm_client import call_llm

    result = call_llm(_spec())
    assert result.success is True
    assert result.backend == "mock"
    assert result.tokens_in > 0
    assert result.tokens_out > 0
    assert result.usage_id is not None

    with session_scope() as session:
        row = session.query(PmAiUsage).filter(PmAiUsage.id == result.usage_id).one()
        assert row.project == "TestPM"
        assert row.agent_kind == "sentiment"
        assert row.model == "claude-haiku-4-5"
        assert row.backend == "mock"
        assert row.tokens_in == result.tokens_in
        assert row.tokens_out == result.tokens_out
        # Costo se calcula con el pricing del MODEL del spec, no del backend.
        # Esto permite simular costos reales aunque el backend sea mock.
        assert row.cost_usd > 0  # claude-haiku-4-5 tiene pricing > 0
        assert row.success is True
        assert row.advisory_only is True
        assert row.correlation_id


def test_mock_with_mock_model_id_has_zero_cost():
    """Si querés que el costo sea cero, usá model='mock-1.0'."""
    from db import session_scope
    from services.pm.models import PmAiUsage
    from services.pm.pm_llm_client import call_llm

    result = call_llm(_spec(model="mock-1.0"))
    assert result.cost_usd == 0.0
    with session_scope() as session:
        row = session.query(PmAiUsage).filter(PmAiUsage.id == result.usage_id).one()
        assert row.cost_usd == 0.0


def test_cost_is_computed_with_real_pricing_for_claude_models():
    from services.pm.pm_llm_client import _compute_cost_usd
    # Haiku: $1 input + $5 output per 1M tokens
    cost = _compute_cost_usd("claude-haiku-4-5", tokens_in=1_000_000, tokens_out=1_000_000)
    assert cost == pytest.approx(6.0, rel=1e-3)

    # Sonnet: $3 + $15
    cost = _compute_cost_usd("claude-sonnet-4-6", tokens_in=100_000, tokens_out=50_000)
    assert cost == pytest.approx(0.3 + 0.75, rel=1e-3)

    # Opus: $15 + $75
    cost = _compute_cost_usd("claude-opus-4-7", tokens_in=10_000, tokens_out=5_000)
    assert cost == pytest.approx(0.15 + 0.375, rel=1e-3)


def test_unknown_model_returns_zero_cost():
    from services.pm.pm_llm_client import _compute_cost_usd
    assert _compute_cost_usd("unknown-model", 1000, 1000) == 0.0


def test_call_returns_parsed_json_when_expect_json_true():
    from services.pm.pm_llm_client import call_llm
    result = call_llm(_spec(expect_json=True))
    assert result.success is True
    assert isinstance(result.parsed_json, dict)
    assert result.parsed_json.get("analyzer_output_version") == "1.0"


def test_invalid_json_marks_call_as_failed():
    """Si el modelo devuelve algo que no es JSON y expect_json=True, success=False."""
    from services.pm.pm_llm_client import call_llm
    # Forzamos un prompt_type unknown para que el mock devuelva texto no-JSON-ish.
    # En realidad el mock siempre devuelve JSON válido. Para este test, monkeypatch.
    import services.pm.pm_llm_client as mod
    original = mod._call_mock

    def bad_mock(spec):
        return "not json at all", 5, 5

    mod._call_mock = bad_mock
    try:
        result = call_llm(_spec(expect_json=True))
        assert result.success is False
        assert "JSONDecodeError" in (result.error or "")
    finally:
        mod._call_mock = original


def test_multiple_calls_each_get_unique_correlation_id():
    from services.pm.pm_llm_client import call_llm
    r1 = call_llm(_spec())
    r2 = call_llm(_spec())
    assert r1.correlation_id != r2.correlation_id
    assert r1.usage_id != r2.usage_id


def test_recommendation_agent_kind_persists_correctly():
    from db import session_scope
    from services.pm.models import PmAiUsage
    from services.pm.pm_llm_client import call_llm

    result = call_llm(_spec(agent_kind="recommendation", prompt_type="rec_engine_v1"))
    assert result.success is True

    with session_scope() as session:
        row = session.query(PmAiUsage).filter(PmAiUsage.id == result.usage_id).one()
        assert row.agent_kind == "recommendation"
        assert row.prompt_type == "rec_engine_v1"


def test_fixture_id_is_persisted_for_eval_calls():
    from db import session_scope
    from services.pm.models import PmAiUsage
    from services.pm.pm_llm_client import call_llm

    result = call_llm(_spec(fixture_id="fixture_blocker_comment"))
    with session_scope() as session:
        row = session.query(PmAiUsage).filter(PmAiUsage.id == result.usage_id).one()
        assert row.fixture_id == "fixture_blocker_comment"
