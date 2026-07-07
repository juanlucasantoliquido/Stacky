"""gitlab_ci_logs.py — Plan 96. Adapter GitLab del sub-puerto CILogsProvider."""
from typing import Optional


class GitLabCILogsProvider:
    name = "gitlab"

    def __init__(self, project: Optional[str] = None):
        from services.gitlab_provider import GitLabTrackerProvider  # noqa: PLC0415
        # kwarg REAL: project= (gitlab_provider.py:33). NO existe project_name=.
        self._provider = GitLabTrackerProvider(project=project)
        self._client = self._provider._client  # GitLabClient (gitlab_provider.py:36)

    def list_failed_jobs(self, pipeline_id: str) -> list[dict]:
        proj_path = self._client._project_path()  # helper real (gitlab_provider.py:104)
        # Paginado (20/pág default) — _request_paginated (gitlab_client.py:177);
        # el scope va en params, NUNCA inline en el path.
        items = self._client._request_paginated(
            f"/projects/{proj_path}/pipelines/{pipeline_id}/jobs",
            params={"scope[]": "failed"},
        )
        return [{"job_id": str(j["id"]), "name": j.get("name") or "",
                 "stage": j.get("stage") or "",
                 "web_url": j.get("web_url")}  # passthrough
                for j in items]

    def get_job_log(self, job_id: str) -> str:
        proj_path = self._client._project_path()
        # _request ya sniffea Content-Type y devuelve resp.text si no es JSON
        # (gitlab_client.py:164-175); trace vacío ⇒ devuelve {} (:169-170) ⇒ coaccionar.
        body, _ = self._client._request("GET", f"/projects/{proj_path}/jobs/{job_id}/trace")
        return body if isinstance(body, str) else ""
