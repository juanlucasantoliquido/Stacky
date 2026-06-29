"""Plan 71 F1 — Sub-puerto CIProvider.

Define el Protocol formal que los adaptadores CI deben implementar
(AdoCIProvider para azure_devops, GitLabCIProvider para gitlab) más la
fábrica get_ci_provider() que selecciona el adapter según el proyecto.

Regla de diseño: este módulo NO importa ado_client ni gitlab_provider
en el cuerpo del módulo. Las importaciones de adapters son LAZY (dentro
de get_ci_provider), igual que el patrón de tracker_provider.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Value objects (frozen dataclasses)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemRef:
    """Referencia a un ítem de tracker (ADO work item id, GitLab issue iid, etc.)."""

    item_id: str
    tracker_type: str       # "azure_devops" | "gitlab"
    ref: Optional[str] = None   # branch/sha/ref de CI para filtrar pipelines


@dataclass(frozen=True)
class PipelineStageInfo:
    """Estado de una etapa del pipeline de delivery."""

    stage: str              # "business" | "functional" | "technical" | "developer" | "qa"
    done: bool
    source: str             # "llm" | "ci" | "cache"
    confidence: float
    evidence: str
    ref: Optional[str]
    web_url: Optional[str]

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "done": self.done,
            "source": self.source,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "ref": self.ref,
            "web_url": self.web_url,
        }


@dataclass(frozen=True)
class ItemPipelineResult:
    """Resultado completo de la inferencia de pipeline para un ítem."""

    item_ref: ItemRef
    stages: tuple                   # tuple[PipelineStageInfo, ...]
    overall_progress: float
    source: str                     # "llm" | "ci" | "cache"
    raw: dict                       # datos crudos del adapter

    def to_dict(self) -> dict:
        return {
            "item_ref": {
                "item_id": self.item_ref.item_id,
                "tracker_type": self.item_ref.tracker_type,
                "ref": self.item_ref.ref,
            },
            "stages": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.stages],
            "overall_progress": self.overall_progress,
            "source": self.source,
            "raw": self.raw,
        }


# ---------------------------------------------------------------------------
# Protocol formal
# ---------------------------------------------------------------------------

@runtime_checkable
class CIProvider(Protocol):
    """Puerto CI: inferencia de pipeline agnóstica del tracker."""

    name: str

    def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult:
        ...

    def monitor_pipeline(self, pipeline_id: str) -> dict:
        ...


# Contrato congelado — no renombrar sin actualizar centinela del Plan 71
CI_PORT_METHODS: tuple[str, ...] = ("infer_item_pipeline", "monitor_pipeline")


# ---------------------------------------------------------------------------
# Fábrica get_ci_provider()  (F2 — añadida en el mismo módulo, lazy imports)
# ---------------------------------------------------------------------------

def get_ci_provider(project: Optional[str] = None) -> CIProvider:
    """Devuelve el CIProvider adecuado según el tipo de tracker del proyecto.

    Lógica idéntica a get_tracker_provider() de tracker_provider.py pero
    para el sub-puerto CI.
    """
    from services.project_context import resolve_project_context  # noqa: PLC0415
    from services.tracker_provider import TrackerConfigError  # noqa: PLC0415
    import config as _config  # noqa: PLC0415

    ctx = resolve_project_context(project_name=project)
    ttype = (getattr(ctx, "tracker_type", None) or "azure_devops").strip().lower()

    if ttype == "gitlab":
        if not getattr(_config.config, "STACKY_GITLAB_ENABLED", False):
            raise TrackerConfigError(
                "issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false"
            )
        from services.gitlab_ci_provider import GitLabCIProvider  # noqa: PLC0415
        return GitLabCIProvider(project=project)

    if ttype == "azure_devops":
        from services.ado_ci_provider import AdoCIProvider  # noqa: PLC0415
        return AdoCIProvider(project=project)

    from services.tracker_provider import TrackerConfigError  # noqa: PLC0415
    raise TrackerConfigError(f"tracker '{ttype}' sin CIProvider")
