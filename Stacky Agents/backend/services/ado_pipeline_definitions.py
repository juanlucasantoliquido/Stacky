"""ado_pipeline_definitions.py — Planes 93/94/95. Solo LECTURA en este plan.
Resuelve la pipeline definition YAML de ADO para un yaml_path dado."""
from __future__ import annotations

_MAX_DEFINITIONS = 50  # [C12] cap explícito — el click no cuelga


def find_yaml_definition(project: str | None, yaml_path: str = "azure-pipelines.yml") -> dict | None:
    """GET {base_proj}/_apis/build/definitions?api-version=7.1 (via
    AdoClient._request, ado_client.py:257) e itera buscando
    definition.process.yamlFilename == yaml_path (GET del detalle si la lista no
    trae process; máximo 50 definitions [C12]). Devuelve {'id': int, 'name': str}
    o None. Nunca lanza hacia arriba: TrackerApiError/errores -> None (el caller
    degrada a 'unavailable')."""
    try:
        from services.ado_client import AdoClient  # noqa: PLC0415

        client = AdoClient(project=project)
        url = f"{client._base_proj}/_apis/build/definitions?api-version=7.1"
        body = client._request("GET", url)
        definitions = (body.get("value") or [])[:_MAX_DEFINITIONS]

        for definition in definitions:
            process = definition.get("process") or {}
            yaml_filename = process.get("yamlFilename")
            if yaml_filename is None:
                # La lista no siempre trae 'process' completo: hidratar detalle.
                detail_url = (
                    f"{client._base_proj}/_apis/build/definitions/"
                    f"{definition.get('id')}?api-version=7.1"
                )
                try:
                    detail = client._request("GET", detail_url)
                except Exception:
                    continue
                yaml_filename = (detail.get("process") or {}).get("yamlFilename")

            if yaml_filename == yaml_path:
                return {"id": definition.get("id"), "name": definition.get("name")}

        return None
    except Exception:
        return None
