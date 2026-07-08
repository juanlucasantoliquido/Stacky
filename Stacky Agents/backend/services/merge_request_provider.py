"""merge_request_provider.py — Plan 95. Sub-puerto ISP (patrón repo_writer.py:13)."""
from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class MergeRequestProvider(Protocol):
    """Protocol para providers de Merge Requests / Pull Requests."""
    name: str

    def create_merge_request(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> dict:
        """Crea un MR/PR.
        Retorna: {'id': str, 'web_url': str, 'state': 'open'}
        (id: iid GitLab / pullRequestId ADO, SIEMPRE str).
        Lanza TrackerApiError si el tracker rechaza (p.ej. MR duplicado).
        """
        ...

    def get_merge_request(self, mr_id: str) -> dict:
        """Consulta un MR/PR.
        Retorna: {'id', 'state': 'open'|'merged'|'closed',
                  'pipeline_status': 'success'|'failed'|'running'|'pending'|'canceled'|'none',
                  'mergeable': bool, 'web_url'}.
        """
        ...

    def merge_merge_request(self, mr_id: str) -> dict:
        """Mergear un MR/PR.
        Retorna: {'id', 'state': 'merged'}.
        Lanza TrackerApiError en caso de conflictos o policies.
        """
        ...


MR_PORT_METHODS = ("create_merge_request", "get_merge_request", "merge_merge_request")


def get_merge_request_provider(project: Optional[str] = None) -> MergeRequestProvider:
    """Fábrica espejo de get_repo_writer (repo_writer.py:30).
    Resuelve el tracker provider activo y valida isinstance MergeRequestProvider.
    """
    from services.repo_writer import get_repo_writer  # noqa: PLC0415

    writer = get_repo_writer(project)
    if not isinstance(writer, MergeRequestProvider):
        raise TypeError(
            f"Provider {writer.name} no implementa MergeRequestProvider. "
            f"Métodos faltantes: {set(MR_PORT_METHODS) - set(dir(writer))}"
        )
    return writer
