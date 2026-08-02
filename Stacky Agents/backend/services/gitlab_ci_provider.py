"""Plan 71 F4 — Adapter GitLabCIProvider.

Delega a GitLabTrackerProvider.infer_pipeline y mapea al contrato CIProvider.
"""
from __future__ import annotations

from services.ci_provider import ItemRef, ItemPipelineResult, PipelineStageInfo

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
        # Plan 282 F2: el delegate sale de la FABRICA (unico constructor), que
        # resuelve el ca_bundle por proyecto. El constructor directo no lo hacia.
        from services.tracker_provider import build_gitlab_provider  # noqa: PLC0415
        self._delegate = build_gitlab_provider(project)

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

    def trigger_pipeline(self, item_ref: "ItemRef", ref: str,
                         variables: dict | None = None) -> dict:
        """Plan 72 F2 — Delega a delegate.trigger_pipeline(ref).

        item_ref se pasa por contrato del Protocol pero el delegate solo necesita ref.

        Plan 294 F7 — `variables` viaja con la forma de la API de GitLab
        ([{"key": ..., "value": ...}]). Si el delegate de este deploy es viejo y
        no acepta el argumento, el disparo IGUAL ocurre y el resultado declara
        `variables_applied: False`: degradacion VISIBLE, nunca silenciosa.
        Sin `variables`, el llamado es byte-identico al de antes.
        """
        if not variables:
            return self._delegate.trigger_pipeline(ref)

        payload = [{"key": str(k), "value": str(v)} for k, v in variables.items()]
        try:
            out = self._delegate.trigger_pipeline(ref, variables=payload)
        except TypeError:
            out = dict(self._delegate.trigger_pipeline(ref) or {})
            out["variables_applied"] = False
            return out
        out = dict(out or {})
        out.setdefault("variables_applied", True)
        return out

    def last_pipeline_for_ref(self, ref: str) -> dict | None:
        """Plan 72 F4 — preview HITL: devuelve el primer pipeline del ref o None.

        Read-only; reusa fetch_pipelines del delegate (Plan 71).
        """
        pipelines = self._delegate.fetch_pipelines(ref=ref)
        return pipelines[0] if pipelines else None

    def list_pipeline_definitions(self) -> tuple[list[dict], dict]:
        """Plan 246 F3 — inventario GitLab. Metodo OPCIONAL (fuera del Protocol).

        DIFERENCIA CONCEPTUAL con ADO: GitLab NO tiene "definitions". Un proyecto tiene
        UN archivo de CI (por default `.gitlab-ci.yml`, o el `ci_config_path` del
        proyecto) y muchas CORRIDAS. Devuelve COMO MUCHO UNA entrada por proyecto.

        Llamadas de red: EXACTAMENTE 2 (proyecto + 1 pipeline). [v2 - C1] PROHIBIDO
        usar el listado paginado del delegate: pagina hasta 40 GET (page_cap=40,
        per_page=100) cuando el inventario solo necesita la corrida mas reciente.
        """
        from services.pipeline_inventory import (  # noqa: PLC0415
            SOURCE_GITLAB_PIPELINES,
            map_run_status,
            pipeline_name_from_path,
        )

        meta: dict = {"available": False, "reason": "", "calls": 0}
        try:
            client = self._delegate._client
            proj_path = client._project_path()

            yaml_path = ".gitlab-ci.yml"
            yaml_path_source = "convencion"
            try:
                body, _headers = client._request("GET", f"/projects/{proj_path}")
                meta["calls"] += 1
                configured = (body or {}).get("ci_config_path") if isinstance(body, dict) else None
                if configured:
                    yaml_path = str(configured)
                    yaml_path_source = "proyecto"
            except Exception as exc:
                meta["calls"] += 1
                meta["reason"] = str(exc)[:200]

            runs: list = []
            try:
                body, _headers = client._request(
                    "GET",
                    f"/projects/{proj_path}/pipelines",
                    params={"per_page": 1, "page": 1},
                )
                meta["calls"] += 1
                runs = body if isinstance(body, list) else []
            except Exception as exc:
                meta["calls"] += 1
                meta["reason"] = str(exc)[:200]

            last = runs[0] if runs else None
            if last:
                status, detail = map_run_status(last.get("status"))
                raw_id = last.get("id")
                last_run = {
                    "status": status,
                    "status_detail": detail,
                    "at": last.get("updated_at") or last.get("created_at"),
                    "web_url": last.get("web_url"),
                    "run_id": str(raw_id) if raw_id is not None else None,
                    "source": "provider",
                }
            else:
                last_run = {
                    "status": "never_ran",
                    "status_detail": "sin_corridas",
                    "at": None,
                    "web_url": None,
                    "run_id": None,
                    "source": "provider",
                }

            entry = {
                "provider": "gitlab",
                "definition_id": "",
                "name": pipeline_name_from_path(yaml_path),
                "yaml_path": yaml_path,
                "default_branch": (last or {}).get("ref") or "",
                "queue_status": "",
                "yaml_path_source": yaml_path_source,
                "last_run": last_run,
                "source": SOURCE_GITLAB_PIPELINES,
            }
            meta["available"] = True
            return [entry], meta
        except Exception as exc:
            meta["available"] = False
            meta["reason"] = str(exc)[:200]
            return [], meta


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
