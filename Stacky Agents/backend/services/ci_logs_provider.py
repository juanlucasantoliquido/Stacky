"""ci_logs_provider.py — Plan 96. Sub-puerto ISP (patrón repo_writer.py:13).
NO amplia CIProvider (CI_PORT_METHODS congelado, ci_provider.py:100)."""
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class CILogsProvider(Protocol):
    name: str

    def list_failed_jobs(self, pipeline_id: str) -> list[dict]:
        """[{'job_id': str, 'name': str, 'stage': str, 'web_url': str|None}]
        — solo fallidos. web_url = link al job/log en la web del tracker
        (None si el tracker no lo provee).
        Lanza TrackerApiError si el pipeline no existe/PAT sin scope."""
        ...

    def get_job_log(self, job_id: str) -> str:
        """Texto del log (el caller trunca vía failure_doctor)."""
        ...


LOGS_PORT_METHODS = ("list_failed_jobs", "get_job_log")


def get_ci_logs_provider(project: Optional[str] = None) -> "CILogsProvider":
    """Fábrica espejo de get_ci_provider (ci_provider.py:107-133):
    resolve_project_context → ttype; gitlab exige STACKY_GITLAB_ENABLED
    (si no, TrackerConfigError) y retorna GitLabCILogsProvider(project=project);
    azure_devops ⇒ AdoCILogsProvider(project=project); otro ⇒ TrackerConfigError."""
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
        from services.gitlab_ci_logs import GitLabCILogsProvider  # noqa: PLC0415
        return GitLabCILogsProvider(project=project)

    if ttype == "azure_devops":
        from services.ado_ci_logs import AdoCILogsProvider  # noqa: PLC0415
        return AdoCILogsProvider(project=project)

    raise TrackerConfigError(f"tracker '{ttype}' sin CILogsProvider")
