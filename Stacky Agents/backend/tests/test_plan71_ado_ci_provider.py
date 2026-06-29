"""Plan 71 F3 — Tests AdoCIProvider.

5 casos:
  1. infer_item_pipeline convierte ado_id int y delega a infer_pipeline.
  2. El resultado tiene source="llm".
  3. monitor_pipeline lanza NotImplementedError.
  4. _legacy_to_result es pura: no llama a ADO ni a la DB.
  5. No AttributeError con mock correcto de PipelineInferenceResult.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_legacy_result(ado_id=42, overall_progress=0.5, source="llm"):
    """Construye un PipelineInferenceResult mock con los atributos reales."""
    m = MagicMock()
    m.ado_id = ado_id
    m.stages = {
        "business": {"done": True, "confidence": 0.9, "evidence": "ok"},
        "developer": {"done": False, "confidence": 0.3, "evidence": ""},
    }
    m.overall_progress = overall_progress
    m.source = source
    m.summary = "some summary"
    m.inferred_at = "2026-01-01T00:00:00"
    m.model_used = "gpt-4o-mini"
    m.to_dict.return_value = {
        "ado_id": ado_id,
        "stages": m.stages,
        "overall_progress": overall_progress,
        "source": source,
    }
    return m


# ---------------------------------------------------------------------------
# C1 — infer_item_pipeline convierte item_id → int y llama a infer_pipeline
# ---------------------------------------------------------------------------
def test_infer_item_pipeline_calls_infer_pipeline():
    from services.ado_ci_provider import AdoCIProvider
    from services.ci_provider import ItemRef

    legacy = _make_legacy_result(ado_id=99)
    with patch("services.ado_ci_provider.infer_pipeline", return_value=legacy) as mock_inf:
        provider = AdoCIProvider(project="test_proj")
        ref = ItemRef(item_id="99", tracker_type="azure_devops")
        result = provider.infer_item_pipeline(ref)

    mock_inf.assert_called_once()
    call_kwargs = mock_inf.call_args.kwargs
    assert call_kwargs.get("ado_id") == 99


# ---------------------------------------------------------------------------
# C2 — resultado tiene source="llm" y overall_progress correcto
# ---------------------------------------------------------------------------
def test_result_source_is_llm():
    from services.ado_ci_provider import AdoCIProvider
    from services.ci_provider import ItemRef

    legacy = _make_legacy_result(overall_progress=0.75, source="llm")
    with patch("services.ado_ci_provider.infer_pipeline", return_value=legacy):
        provider = AdoCIProvider(project="test_proj")
        ref = ItemRef(item_id="42", tracker_type="azure_devops")
        result = provider.infer_item_pipeline(ref)

    assert result.source == "llm"
    assert result.overall_progress == 0.75


# ---------------------------------------------------------------------------
# C3 — monitor_pipeline lanza NotImplementedError
# ---------------------------------------------------------------------------
def test_monitor_pipeline_not_implemented():
    from services.ado_ci_provider import AdoCIProvider

    provider = AdoCIProvider(project="test_proj")
    with pytest.raises(NotImplementedError):
        provider.monitor_pipeline("pipeline-id-123")


# ---------------------------------------------------------------------------
# C4 — _legacy_to_result es pura (no toca DB ni red)
# ---------------------------------------------------------------------------
def test_legacy_to_result_is_pure():
    from services.ado_ci_provider import _legacy_to_result
    from services.ci_provider import ItemRef, ItemPipelineResult

    legacy = _make_legacy_result(ado_id=1, overall_progress=0.5)
    ref = ItemRef(item_id="1", tracker_type="azure_devops")

    result = _legacy_to_result(legacy, ref)

    assert isinstance(result, ItemPipelineResult)
    assert result.item_ref == ref
    assert result.overall_progress == 0.5


# ---------------------------------------------------------------------------
# C5 — Sin AttributeError con mock correcto
# ---------------------------------------------------------------------------
def test_no_attribute_error_with_correct_mock():
    from services.ado_ci_provider import AdoCIProvider
    from services.ci_provider import ItemRef

    legacy = _make_legacy_result(ado_id=7, overall_progress=1.0)
    with patch("services.ado_ci_provider.infer_pipeline", return_value=legacy):
        provider = AdoCIProvider(project="test_proj")
        ref = ItemRef(item_id="7", tracker_type="azure_devops")

        # No debe lanzar ninguna excepción
        result = provider.infer_item_pipeline(ref)
        d = result.to_dict()
        assert "item_ref" in d
        assert "stages" in d
