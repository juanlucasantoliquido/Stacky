"""Tests del backend Copilot Pro para pm_llm_client.

Sin red. Mockea copilot_bridge._invoke_copilot para devolver respuestas
controladas y verificar:
- Tokens reales del API se capturan en pm_ai_usage
- backend="copilot" persistido correctamente
- Errores del bridge se transforman en LLMBackendError
- PII guard funciona igual que con otros backends
- Pricing aplicado al modelo del spec (referencia, no costo real al usuario
  Copilot Pro)
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


@pytest.fixture(autouse=True)
def _force_copilot_backend(monkeypatch):
    """Cada test corre con STACKY_PM_LLM_BACKEND=copilot."""
    monkeypatch.setenv("STACKY_PM_LLM_BACKEND", "copilot")
    yield


def _stub_copilot_invoke(monkeypatch, *, text: str, tokens_in: int, tokens_out: int):
    """Reemplaza copilot_bridge._invoke_copilot con un stub que devuelve datos
    controlados, sin hacer ninguna llamada HTTP."""
    import copilot_bridge

    class _FakeBridgeResponse:
        def __init__(self, text, metadata):
            self.text = text
            self.format = "markdown"
            self.metadata = metadata

    def fake_invoke(*, agent_type, system, user, on_log, execution_id, model):
        on_log("info", "stub copilot invoke")
        return _FakeBridgeResponse(
            text=text,
            metadata={
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "duration_ms": 42,
            },
        )

    monkeypatch.setattr(copilot_bridge, "_invoke_copilot", fake_invoke)


def _spec(**overrides):
    from services.pm.pm_llm_client import LLMCallSpec
    base = dict(
        project="TestPM",
        agent_kind="sentiment",
        prompt_type="comment_sentiment_v1",
        model="gpt-4o",
        system="Sos un clasificador.",
        user='Comentario: "ticket en QA"',
        max_output_tokens=256,
        temperature=0.0,
        fixture_id=None,
        expect_json=True,
    )
    base.update(overrides)
    return LLMCallSpec(**base)


# ── happy path ────────────────────────────────────────────────────────────────

def test_copilot_call_persists_with_real_tokens(monkeypatch):
    """Tokens del API de Copilot se capturan exactos en pm_ai_usage."""
    from db import session_scope
    from services.pm.models import PmAiUsage
    from services.pm.pm_llm_client import call_llm

    payload = (
        '{"analyzer_output_version": "1.0", "results": [{'
        '"comment_id": 1, "sentiment_label": "positive", '
        '"sentiment_score": 0.9, "flags": [], "confidence": 0.85}], '
        '"model_used": "gpt-4o"}'
    )
    _stub_copilot_invoke(monkeypatch, text=payload, tokens_in=1234, tokens_out=567)

    result = call_llm(_spec())
    assert result.success is True
    assert result.backend == "copilot"
    # Tokens deben coincidir EXACTO con lo que devuelve copilot
    assert result.tokens_in == 1234
    assert result.tokens_out == 567

    with session_scope() as session:
        row = session.query(PmAiUsage).filter(PmAiUsage.id == result.usage_id).one()
        assert row.backend == "copilot"
        assert row.model == "gpt-4o"
        assert row.tokens_in == 1234
        assert row.tokens_out == 567
        assert row.advisory_only is True


def test_copilot_call_computes_reference_cost_with_pricing(monkeypatch):
    """Costo USD se calcula con pricing de referencia (no es costo real para
    usuarios Copilot Pro, pero da una métrica útil para comparar con API directo)."""
    from services.pm.pm_llm_client import call_llm

    _stub_copilot_invoke(
        monkeypatch,
        text='{"ok": true, "model_used": "gpt-4o"}',
        tokens_in=1_000_000,
        tokens_out=500_000,
    )
    result = call_llm(_spec(expect_json=False))
    # gpt-4o: $2.50 input + $10 output per 1M tokens
    # 1M in × $2.50 + 0.5M out × $10 = 2.5 + 5.0 = $7.50
    assert result.cost_usd == pytest.approx(7.5, rel=1e-3)


def test_copilot_call_parses_json_when_expected(monkeypatch):
    from services.pm.pm_llm_client import call_llm

    _stub_copilot_invoke(
        monkeypatch,
        text='{"rec_output_version": "1.0", "recommendations": [], "advisory_only": true}',
        tokens_in=100,
        tokens_out=30,
    )
    result = call_llm(_spec(agent_kind="recommendation", expect_json=True))
    assert result.success is True
    assert isinstance(result.parsed_json, dict)
    assert result.parsed_json.get("advisory_only") is True


def test_copilot_backend_is_dispatched_by_env_var(monkeypatch):
    """STACKY_PM_LLM_BACKEND=copilot fuerza el dispatch incluso si
    config.LLM_BACKEND es otro."""
    from services.pm.pm_llm_client import _backend_name
    monkeypatch.setenv("STACKY_PM_LLM_BACKEND", "copilot")
    assert _backend_name() == "copilot"


def test_invalid_backend_value_falls_back_to_mock(monkeypatch):
    from services.pm.pm_llm_client import _backend_name
    monkeypatch.setenv("STACKY_PM_LLM_BACKEND", "openai_direct")
    assert _backend_name() == "mock"


# ── error handling ────────────────────────────────────────────────────────────

def test_copilot_bridge_runtime_error_captured_as_failed_call(monkeypatch):
    """Si copilot_bridge falla (auth, 429, network), pm_llm_client marca
    el call como failed sin lanzar excepción al caller."""
    import copilot_bridge
    from services.pm.pm_llm_client import call_llm

    def failing_invoke(**_kwargs):
        raise RuntimeError("copilot API HTTP 401: bad token")

    monkeypatch.setattr(copilot_bridge, "_invoke_copilot", failing_invoke)
    result = call_llm(_spec())
    assert result.success is False
    assert result.error is not None
    assert "LLMBackendError" in result.error
    assert "401" in result.error
    # Aun fallando, la fila se persiste (para que el operador vea el incidente)
    assert result.usage_id is not None


def test_copilot_pii_guard_blocks_raw_email(monkeypatch):
    """El PII guard se ejecuta ANTES del backend, sin importar cuál sea."""
    from services.pm.pm_llm_client import PiiLeakError, call_llm

    # No necesitamos stubear copilot_bridge porque la excepción se levanta antes
    with pytest.raises(PiiLeakError):
        call_llm(_spec(user="contactar a juan@empresa.com"))


def test_copilot_backend_with_missing_bridge_raises_backend_error(monkeypatch):
    """Si copilot_bridge no se puede importar, _call_copilot lanza
    LLMBackendError y el call queda marcado como failed."""
    import services.pm.pm_llm_client as mod
    from services.pm.pm_llm_client import call_llm

    # Simular ImportError monkey-patcheando _call_copilot directamente
    def broken_call(_spec):
        from services.pm.pm_llm_client import LLMBackendError
        raise LLMBackendError("Backend 'copilot' requiere copilot_bridge.py")

    monkeypatch.setattr(mod, "_call_copilot", broken_call)
    result = call_llm(_spec())
    assert result.success is False
    assert "LLMBackendError" in (result.error or "")


# ── tracking metadata ─────────────────────────────────────────────────────────

def test_correlation_id_unique_across_copilot_calls(monkeypatch):
    from services.pm.pm_llm_client import call_llm

    _stub_copilot_invoke(
        monkeypatch,
        text='{"ok": true}',
        tokens_in=10,
        tokens_out=5,
    )
    r1 = call_llm(_spec(expect_json=False))
    r2 = call_llm(_spec(expect_json=False))
    assert r1.correlation_id != r2.correlation_id
    assert r1.usage_id != r2.usage_id


def test_fixture_id_persisted_for_copilot_eval_runs(monkeypatch):
    from db import session_scope
    from services.pm.models import PmAiUsage
    from services.pm.pm_llm_client import call_llm

    _stub_copilot_invoke(
        monkeypatch,
        text='{"analyzer_output_version": "1.0", "results": []}',
        tokens_in=200,
        tokens_out=50,
    )
    result = call_llm(_spec(fixture_id="sentiment_blocker_comment"))
    with session_scope() as session:
        row = session.query(PmAiUsage).filter(PmAiUsage.id == result.usage_id).one()
        assert row.fixture_id == "sentiment_blocker_comment"
        assert row.backend == "copilot"


def test_copilot_call_with_openai_model_priced_correctly(monkeypatch):
    """Modelos OpenAI vía Copilot (gpt-4o-mini) deben usar su propio pricing."""
    from services.pm.pm_llm_client import _compute_cost_usd

    # gpt-4o-mini: $0.15 input + $0.60 output per 1M tokens
    cost = _compute_cost_usd("gpt-4o-mini", tokens_in=1_000_000, tokens_out=500_000)
    assert cost == pytest.approx(0.15 + 0.30, rel=1e-3)

    # o1: $15 input + $60 output per 1M tokens (reasoning, caro)
    cost = _compute_cost_usd("o1", tokens_in=10_000, tokens_out=5_000)
    assert cost == pytest.approx(0.15 + 0.30, rel=1e-3)
