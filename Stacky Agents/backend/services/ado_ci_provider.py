"""Plan 71 F3 — Adapter AdoCIProvider.

Delega a ado_pipeline_inference.infer_pipeline y mapea el resultado
al contrato CIProvider (ItemPipelineResult / PipelineStageInfo).
"""
from __future__ import annotations

from services.ci_provider import CIProvider, ItemRef, ItemPipelineResult, PipelineStageInfo
from services.ado_pipeline_inference import infer_pipeline


class AdoCIProvider:
    """CIProvider para Azure DevOps. Delega al motor LLM de infer_pipeline."""

    name = "azure_devops"

    def __init__(self, project: str | None = None) -> None:
        self._project = project

    def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult:
        ado_id = int(item_ref.item_id)
        legacy = infer_pipeline(ado_id=ado_id, project_name=self._project)
        return _legacy_to_result(legacy, item_ref)

    def monitor_pipeline(self, pipeline_id: str) -> dict:
        raise NotImplementedError(
            "monitor_pipeline se implementa en Plan 72 F1"
        )


def _legacy_to_result(legacy, item_ref: ItemRef) -> ItemPipelineResult:
    """Convierte PipelineInferenceResult al contrato ItemPipelineResult."""
    raw_stages: dict = legacy.stages or {}

    stage_objects: list[PipelineStageInfo] = []
    for stage_name, stage_data in raw_stages.items():
        if isinstance(stage_data, dict):
            stage_objects.append(
                PipelineStageInfo(
                    stage=stage_name,
                    done=bool(stage_data.get("done", False)),
                    source=legacy.source or "llm",
                    confidence=float(stage_data.get("confidence", 0.0)),
                    evidence=str(stage_data.get("evidence", "")),
                    ref=None,
                    web_url=None,
                )
            )

    overall = getattr(legacy, "overall_progress", None)
    if overall is None and stage_objects:
        done_count = sum(1 for s in stage_objects if s.done)
        overall = done_count / len(stage_objects)
    overall = float(overall or 0.0)

    return ItemPipelineResult(
        item_ref=item_ref,
        stages=tuple(stage_objects),
        overall_progress=overall,
        source=legacy.source or "llm",
        raw=legacy.to_dict(),
    )
