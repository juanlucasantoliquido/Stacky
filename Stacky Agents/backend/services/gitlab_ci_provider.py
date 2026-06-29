"""Plan 71 F4 — Adapter GitLabCIProvider.

Delega a GitLabTrackerProvider.infer_pipeline y mapea al contrato CIProvider.
"""
from __future__ import annotations

from services.ci_provider import ItemRef, ItemPipelineResult, PipelineStageInfo
from services.gitlab_provider import GitLabTrackerProvider

# Mapa de status CI → progreso numérico
STATUS_TO_PROGRESS: dict[str, float] = {
    "success": 1.0,
    "failed": 0.0,
    "running": 0.5,
    "pending": 0.5,
    "canceled": 0.0,
    "skipped": 0.0,
    "manual": 0.0,
    "created": 0.0,
}


class GitLabCIProvider:
    """CIProvider para GitLab CI. Delega a GitLabTrackerProvider.infer_pipeline."""

    name = "gitlab"

    def __init__(self, project: str | None = None) -> None:
        self._project = project
        self._delegate = GitLabTrackerProvider(project_name=project)

    def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult:
        try:
            pipelines = self._delegate.infer_pipeline(ref=item_ref.ref)
        except Exception as exc:
            # 403 u otro error → degradar a source="llm"
            err_str = str(exc)
            evidence = "PAT scope insuficiente" if "403" in err_str else err_str
            fallback_stage = PipelineStageInfo(
                stage="ci",
                done=False,
                source="llm",
                confidence=0.0,
                evidence=evidence,
                ref=item_ref.ref,
                web_url=None,
            )
            return ItemPipelineResult(
                item_ref=item_ref,
                stages=(fallback_stage,),
                overall_progress=0.0,
                source="llm",
                raw={"error": err_str},
            )

        return _pipelines_to_result(pipelines, item_ref)

    def monitor_pipeline(self, pipeline_id: str) -> dict:
        """Plan 72 F1 — Delega a delegate.poll_pipeline."""
        return self._delegate.poll_pipeline(pipeline_id)

    def trigger_pipeline(self, item_ref: "ItemRef", ref: str) -> dict:
        """Plan 72 F2 — Delega a delegate.trigger_pipeline(ref).

        item_ref se pasa por contrato del Protocol pero el delegate solo necesita ref.
        """
        return self._delegate.trigger_pipeline(ref)

    def last_pipeline_for_ref(self, ref: str) -> dict | None:
        """Plan 72 F4 — preview HITL: devuelve el primer pipeline del ref o None.

        Read-only; reusa fetch_pipelines del delegate (Plan 71).
        """
        pipelines = self._delegate.fetch_pipelines(ref=ref)
        return pipelines[0] if pipelines else None


def _pipelines_to_result(pipelines: list[dict], item_ref: ItemRef) -> ItemPipelineResult:
    """Convierte lista de dicts GitLab al contrato ItemPipelineResult.

    Keys esperadas por pipeline: source, status, ref, sha, web_url.
    """
    if not pipelines:
        return ItemPipelineResult(
            item_ref=item_ref,
            stages=(),
            overall_progress=0.0,
            source="ci",
            raw={"pipelines": []},
        )

    stages: list[PipelineStageInfo] = []
    for p in pipelines:
        source = p.get("source", "ci")
        status = p.get("status", "unknown")
        progress = STATUS_TO_PROGRESS.get(status, 0.0)
        # Si la fuente es llm, progreso siempre 0.0 (no hay datos reales)
        if source == "llm":
            progress = 0.0
        stages.append(
            PipelineStageInfo(
                stage="ci",
                done=(status == "success"),
                source=source,
                confidence=progress,
                evidence=f"status={status}",
                ref=p.get("ref"),
                web_url=p.get("web_url"),
            )
        )

    # overall_progress = media de los progressos
    if stages:
        overall = sum(STATUS_TO_PROGRESS.get(p.get("status", ""), 0.0)
                      for p in pipelines
                      if p.get("source") != "llm") / max(len(pipelines), 1)
        # Si todos son llm, overall=0.0
        if all(p.get("source") == "llm" for p in pipelines):
            overall = 0.0
    else:
        overall = 0.0

    primary_source = pipelines[0].get("source", "ci") if pipelines else "ci"

    return ItemPipelineResult(
        item_ref=item_ref,
        stages=tuple(stages),
        overall_progress=round(overall, 2),
        source=primary_source,
        raw={"pipelines": pipelines},
    )
