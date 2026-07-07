"""ado_ci_logs.py — Plan 96. Adapter ADO del sub-puerto CILogsProvider."""
from typing import Optional


class AdoCILogsProvider:
    name = "azure_devops"

    def __init__(self, project: Optional[str] = None):
        from services.project_context import build_ado_client  # noqa: PLC0415
        # Factory canónica per-proyecto (project_context.py:208) — NUNCA
        # AdoClient() pelado: resuelve el proyecto ACTIVO (bug documentado en
        # ado_publisher.py:587) y cruzaría PAT/org/project.
        self._client = build_ado_client(project)

    def _call(self, method: str, url: str):
        from services.ado_client import AdoApiError  # noqa: PLC0415
        from services.tracker_provider import TrackerApiError  # noqa: PLC0415
        try:
            return self._client._request(method, url)
        except AdoApiError as e:
            # AdoApiError(RuntimeError) NO es TrackerApiError (ado_client.py:62
            # vs tracker_provider.py:48): traducir para que F3 propague el status real.
            raise TrackerApiError(getattr(e, "status_code", None) or 502, str(e))

    def list_failed_jobs(self, pipeline_id: str) -> list[dict]:
        url = f"{self._client._base_proj}/_apis/build/builds/{pipeline_id}/timeline?api-version=7.1"
        body = self._call("GET", url)
        out = []
        for r in (body.get("records") or []):
            # SOLO result=="failed": las Tasks "canceled" caen en cascada por
            # el fallo de otra y su log no explica nada (tarjetas-ruido).
            if r.get("type") != "Task" or r.get("result") != "failed":
                continue
            log = r.get("log") or {}
            if not log.get("id"):  # records sin log se omiten — defensivo
                continue
            record_guid = r.get("id")
            out.append({
                "job_id": f"{pipeline_id}:{log['id']}",  # id compuesto build:log
                "name": r.get("name") or "",
                "stage": r.get("parentId") or "",
                # deep-link al log del job en la web de ADO
                "web_url": (f"{self._client._base_proj}/_build/results"
                            f"?buildId={pipeline_id}&view=logs&j={record_guid}")
                           if record_guid else None,
            })
        return out

    def get_job_log(self, job_id: str) -> str:
        from services.tracker_provider import TrackerApiError  # noqa: PLC0415
        build_id, sep, log_id = job_id.partition(":")
        if not sep or not build_id or not log_id:
            raise TrackerApiError(400, f"job_id ADO invalido: {job_id!r} (esperado 'build:log')")
        url = f"{self._client._base_proj}/_apis/build/builds/{build_id}/logs/{log_id}?api-version=7.1"
        body = self._call("GET", url)
        # AdoClient._headers fuerza Accept: application/json (ado_client.py:250-255)
        # ⇒ el log llega como {"count": N, "value": ["línea", ...]}; _request RECHAZA
        # no-JSON lanzando AdoApiError (ado_client.py:274-282) — cubierto por _call.
        if isinstance(body, dict):
            return "\n".join(str(line) for line in (body.get("value") or []))
        return str(body or "")
