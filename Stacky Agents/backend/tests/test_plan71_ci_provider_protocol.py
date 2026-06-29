"""Plan 71 F1 — Tests del sub-puerto CIProvider (Protocol).

5 casos:
  1. ItemRef es dataclass frozen y hasheable.
  2. PipelineStageInfo contiene todos los campos requeridos.
  3. ItemPipelineResult.to_dict() incluye item_ref, stages, overall_progress, source, raw.
  4. CIProvider es runtime_checkable: implementación mínima satisface isinstance.
  5. ci_provider.py no importa ADO ni GitLab en el módulo.
"""
from __future__ import annotations

import importlib
import sys
import types


# ---------------------------------------------------------------------------
# C1 — ItemRef es frozen y hasheable
# ---------------------------------------------------------------------------
def test_item_ref_frozen_and_hasheable():
    from services.ci_provider import ItemRef

    ref = ItemRef(item_id="123", tracker_type="azure_devops")
    assert ref.item_id == "123"
    assert ref.tracker_type == "azure_devops"
    assert ref.ref is None
    # hasheable (frozen=True lo garantiza)
    assert hash(ref) == hash(ItemRef(item_id="123", tracker_type="azure_devops"))


# ---------------------------------------------------------------------------
# C2 — PipelineStageInfo tiene los campos esperados
# ---------------------------------------------------------------------------
def test_pipeline_stage_info_fields():
    from services.ci_provider import PipelineStageInfo

    s = PipelineStageInfo(
        stage="business",
        done=True,
        source="llm",
        confidence=0.9,
        evidence="found R-BUSINESS",
        ref=None,
        web_url=None,
    )
    assert s.stage == "business"
    assert s.done is True
    assert s.source == "llm"
    assert s.confidence == 0.9
    assert s.evidence == "found R-BUSINESS"


# ---------------------------------------------------------------------------
# C3 — ItemPipelineResult.to_dict()
# ---------------------------------------------------------------------------
def test_item_pipeline_result_to_dict():
    from services.ci_provider import ItemRef, ItemPipelineResult, PipelineStageInfo

    ref = ItemRef(item_id="42", tracker_type="azure_devops")
    stage = PipelineStageInfo(
        stage="business", done=True, source="llm", confidence=1.0,
        evidence="ok", ref=None, web_url=None,
    )
    result = ItemPipelineResult(
        item_ref=ref,
        stages=(stage,),
        overall_progress=1.0,
        source="llm",
        raw={"ado_id": 42},
    )
    d = result.to_dict()
    assert d["item_ref"]["item_id"] == "42"
    assert d["overall_progress"] == 1.0
    assert d["source"] == "llm"
    assert "stages" in d
    assert "raw" in d


# ---------------------------------------------------------------------------
# C4 — CIProvider es runtime_checkable
# ---------------------------------------------------------------------------
def test_ci_provider_runtime_checkable():
    from services.ci_provider import CIProvider, ItemRef, ItemPipelineResult

    class FakeProvider:
        name = "fake"

        def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult:
            ...

        def monitor_pipeline(self, pipeline_id: str) -> dict:
            ...

    assert isinstance(FakeProvider(), CIProvider)


# ---------------------------------------------------------------------------
# C5 — ci_provider.py no importa ADO ni GitLab en el módulo
# ---------------------------------------------------------------------------
def test_ci_provider_no_ado_gitlab_import():
    """El módulo ci_provider no debe tener imports directos de ado_client ni gitlab_provider."""
    import services.ci_provider as mod

    src = mod.__file__
    with open(src, encoding="utf-8") as f:
        lines = f.readlines()

    forbidden = ("ado_client", "gitlab_provider", "gitlab_client")
    for line in lines:
        stripped = line.strip()
        # Solo revisar líneas que sean sentencias de import reales (no comentarios, no docstrings)
        if not stripped.startswith("import ") and not stripped.startswith("from "):
            continue
        for bad in forbidden:
            assert bad not in stripped, (
                f"ci_provider.py contiene import prohibido '{bad}': {stripped!r}"
            )
