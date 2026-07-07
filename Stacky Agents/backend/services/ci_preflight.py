"""ci_preflight.py — Plan 93. Sub-puerto ISP (patrón RepoWriter, repo_writer.py:13).
NO amplia CIProvider (CI_PORT_METHODS congelado, ci_provider.py:100)."""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class CIPreflightProvider(Protocol):
    name: str

    def lint_yaml(self, yaml_str: str) -> dict:
        """{'status': 'ok'|'fail'|'unavailable', 'errors': [str], 'detail': str}"""
        ...

    def list_runners(self) -> dict:
        """{'status': 'ok'|'unavailable', 'runners': [{'id', 'online': bool,
        'tags': [str]}], 'detail': str}"""
        ...


PREFLIGHT_PORT_METHODS = ("lint_yaml", "list_runners")


def get_preflight_provider(project: Optional[str] = None) -> CIPreflightProvider:
    """Fábrica espejo de get_ci_provider (ci_provider.py:107): resuelve
    tracker_type vía resolve_project_context; gitlab -> GitLabPreflightProvider,
    azure_devops -> AdoPreflightProvider; otro -> TrackerConfigError."""
    from services.project_context import resolve_project_context  # noqa: PLC0415
    from services.tracker_provider import TrackerConfigError  # noqa: PLC0415

    ctx = resolve_project_context(project_name=project)
    ttype = (getattr(ctx, "tracker_type", None) or "azure_devops").strip().lower()

    if ttype == "gitlab":
        from services.gitlab_preflight import GitLabPreflightProvider  # noqa: PLC0415
        return GitLabPreflightProvider(project=project)

    if ttype == "azure_devops":
        from services.ado_preflight import AdoPreflightProvider  # noqa: PLC0415
        return AdoPreflightProvider(project=project)

    raise TrackerConfigError(f"tracker '{ttype}' sin CIPreflightProvider")
