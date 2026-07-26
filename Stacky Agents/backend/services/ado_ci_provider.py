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
        """Plan 95 F1.c — GET {base_proj}/_apis/build/builds/{id}?api-version=7.1
        → {"id", "status": _map_status(build), "ref", "web_url"}.
        """
        from services.ado_client import AdoClient  # noqa: PLC0415
        from services.tracker_provider import TrackerApiError  # noqa: PLC0415

        client = AdoClient(project=self._project)
        url = f"{client._base_proj}/_apis/build/builds/{pipeline_id}?api-version=7.1"
        try:
            build = client._request("GET", url)
            status = _map_status(build)
            ref = build.get("sourceBranch", "")
            if ref.startswith("refs/heads/"):
                ref = ref[len("refs/heads/"):]
            web_url = build.get("_links", {}).get("web", {}).get("href", "")
            return {
                "id": str(build.get("id")),
                "status": status,
                "ref": ref,
                "web_url": web_url,
            }
        except Exception as e:
            raise TrackerApiError(
                status=500,
                kind="ado_monitor_failed",
                message=f"Error monitoreando pipeline ADO {pipeline_id}: {e}",
            ) from e

    def trigger_pipeline(self, item_ref: "ItemRef", ref: str) -> dict:
        """Plan 95 F1.c — Runs API. Resuelve la definition (find_yaml_definition;
        si None lanza TrackerApiError(status=409, kind='ado_definition_missing')).
        POST {base_proj}/_apis/pipelines/{definitionId}/runs?api-version=7.1.
        Retorno NORMALIZADO al shape que la UI ya consume del lado GitLab:
        {"id": run.id, "status": _map_status(run), "ref": ref, "web_url": run._links.web.href}.
        """
        from services.ado_client import AdoClient  # noqa: PLC0415
        from services.ado_pipeline_definitions import find_yaml_definition  # noqa: PLC0415
        from services.tracker_provider import TrackerApiError  # noqa: PLC0415

        # Resolver definition ANTES de crear el cliente (evita validación PAT si no hay definition)
        definition = find_yaml_definition(self._project)
        if definition is None:
            raise TrackerApiError(
                status=409,
                kind="ado_definition_missing",
                message=(
                    "No hay pipeline definition en ADO. Usá 'Llevar a producción' → "
                    "'Crear definición' (asegurate de haber commiteado el YAML primero)."
                ),
            )

        client = AdoClient(project=self._project)
        definition_id = definition["id"]
        url = f"{client._base_proj}/_apis/pipelines/{definition_id}/runs?api-version=7.1"
        body = {
            "resources": {
                "repositories": {
                    "self": {
                        "refName": f"refs/heads/{ref}"
                    }
                }
            }
        }

        try:
            run = client._request("POST", url, body=body)
            status = _map_status(run)
            web_url = run.get("_links", {}).get("web", {}).get("href", "")
            return {
                "id": str(run.get("id")),
                "status": status,
                "ref": ref,
                "web_url": web_url,
            }
        except Exception as e:
            raise TrackerApiError(
                status=500,
                kind="ado_trigger_failed",
                message=f"Error trigger pipeline ADO: {e}",
            ) from e

    def last_pipeline_for_ref(self, ref: str) -> dict | None:
        """Plan 95 F1.c — GET {base_proj}/_apis/build/builds?branchName=refs/heads/{ref}
        &$top=1 &queryOrder=queueTimeDescending → build normalizado o None.
        """
        from services.ado_client import AdoClient  # noqa: PLC0415

        client = AdoClient(project=self._project)
        url = (
            f"{client._base_proj}/_apis/build/builds?"
            f"branchName=refs/heads/{ref}&$top=1&queryOrder=queueTimeDescending&api-version=7.1"
        )
        try:
            body = client._request("GET", url)
            builds = body.get("value", [])
            if not builds:
                return None
            build = builds[0]
            status = _map_status(build)
            return {
                "id": str(build.get("id")),
                "status": status,
                "ref": ref,
                "web_url": build.get("_links", {}).get("web", {}).get("href", ""),
            }
        except Exception:
            return None

    def list_pipeline_definitions(self) -> tuple[list[dict], dict]:
        """Plan 246 F2 — inventario de definiciones ADO + ultima corrida por definicion.

        METODO OPCIONAL: NO esta en el Protocol CIProvider (ci_provider.py:83-95) ni en
        CI_PORT_METHODS (:100, contrato CONGELADO). Mismo patron que
        last_pipeline_for_ref (:107). Se consume duck-typed con getattr.

        Presupuesto de red: 1 (definiciones) + <=10 (hidratacion) + 1 (builds batch).
        PROHIBIDO caer a un bucle de una llamada por definicion.
        """
        from services.ado_pipeline_definitions import list_definitions  # noqa: PLC0415
        from services.pipeline_inventory import (  # noqa: PLC0415
            SOURCE_ADO_DEFINITIONS,
            _MAX_BUILDS_SCAN,
            map_run_status,
        )

        defs, meta = list_definitions(self._project)
        if not defs:
            return [], meta

        def _sin_corridas() -> dict:
            return {
                "status": "never_ran",
                "status_detail": "sin_corridas",
                "at": None,
                "web_url": None,
                "run_id": None,
                "source": "provider",
            }

        latest: dict[str, dict] = {}
        batch_ok = True
        try:
            from services.ado_client import AdoClient  # noqa: PLC0415

            client = AdoClient(project=self._project)
            ids_csv = ",".join(d["definition_id"] for d in defs)
            url = (
                f"{client._base_proj}/_apis/build/builds?definitions={ids_csv}"
                f"&$top={_MAX_BUILDS_SCAN}&queryOrder=queueTimeDescending&api-version=7.1"
            )
            body = client._request("GET", url)
            builds = (body or {}).get("value")
            if not isinstance(builds, list):
                raise ValueError("respuesta batch sin 'value'")
            for build in builds:
                def_id = str(((build.get("definition") or {}).get("id")) or "")
                if def_id and def_id not in latest:
                    latest[def_id] = build
        except Exception:
            batch_ok = False

        out: list[dict] = []
        for definition in defs:
            build = latest.get(definition["definition_id"])
            if not batch_ok:
                last_run = {
                    "status": "unknown",
                    "status_detail": "batch_no_soportado",
                    "at": None,
                    "web_url": None,
                    "run_id": None,
                    "source": "provider",
                }
            elif build is None:
                last_run = _sin_corridas()
            else:
                status, detail = map_run_status(_map_status(build))
                raw_id = build.get("id")
                last_run = {
                    "status": status,
                    "status_detail": detail,
                    "at": build.get("finishTime") or build.get("queueTime"),
                    "web_url": (build.get("_links") or {}).get("web", {}).get("href") or None,
                    "run_id": str(raw_id) if raw_id is not None else None,
                    "source": "provider",
                }
            out.append(
                {
                    "provider": "azure_devops",
                    "name": definition["name"],
                    "yaml_path": definition["yaml_path"],
                    "default_branch": definition["default_branch"] or None,
                    "definition_id": definition["definition_id"],
                    "last_run": last_run,
                    "source": SOURCE_ADO_DEFINITIONS,
                }
            )

        meta = dict(meta)
        meta["batch_ok"] = batch_ok
        return out, meta


def _map_status(build: dict) -> str:
    """Plan 95 F1.c — ADO (status, result) → vocabulario GitLab:
    notStarted→created; inProgress→running; postponed→pending;
    completed+succeeded→success; completed+(failed|partiallySucceeded)→failed;
    completed+canceled→canceled.
    Tabla LITERAL (dict) con test.
    """
    status = build.get("status", "")
    result = build.get("result", "")

    if status == "notStarted":
        return "created"
    if status == "inProgress":
        return "running"
    if status == "postponed":
        return "pending"
    if status == "completed":
        if result == "succeeded":
            return "success"
        if result in ("failed", "partiallySucceeded"):
            return "failed"
        if result == "canceled":
            return "canceled"
    # Fallback
    return "pending"


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
