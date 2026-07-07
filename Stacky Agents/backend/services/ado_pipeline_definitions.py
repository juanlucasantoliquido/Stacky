"""ado_pipeline_definitions.py — Planes 93/94/95. Solo LECTURA en este plan.
Resuelve la pipeline definition YAML de ADO para un yaml_path dado."""
from __future__ import annotations

_MAX_DEFINITIONS = 50  # [C12] cap explícito — el click no cuelga


def _resolve_repo_id(project: str | None) -> str:
    """Plan 95 F1.a — Helper para resolver el repo_id de ADO.
    Reglas CERRADAS (C3 del plan):
    (a) si project_config define `repository` (nombre o id), matchear contra
        GET {base_proj}/_apis/git/repositories?api-version=7.1
        (por id exacto o name case-insensitive); sin match ⇒
        TrackerApiError(status=404, kind="ado_repo_not_found").
    (b) sin config y la lista tiene EXACTAMENTE 1 repo ⇒ ese.
    (c) sin config y >1 repos ⇒ TrackerApiError(status=400,
        kind="ado_repo_ambiguous", mensaje con los nombres disponibles).
    """
    from services.ado_client import AdoClient  # noqa: PLC0415
    from project_manager import get_project_config  # noqa: PLC0415
    from services.tracker_provider import TrackerApiError  # noqa: PLC0415

    client = AdoClient(project=project)
    url = f"{client._base_proj}/_apis/git/repositories?api-version=7.1"
    body = client._request("GET", url)
    repos = body.get("value", [])

    # (a) Si project_config define repository
    cfg = get_project_config(project)
    repo_identifier = cfg.get("repository") if cfg else None
    if repo_identifier:
        for repo in repos:
            # Match por id exacto o name case-insensitive
            if str(repo.get("id")) == str(repo_identifier):
                return str(repo["id"])
            if repo.get("name", "").lower() == str(repo_identifier).lower():
                return str(repo["id"])
        raise TrackerApiError(
            status=404,
            kind="ado_repo_not_found",
            message=f"Repo '{repo_identifier}' no encontrado en proyecto ADO {project}",
        )

    # (b) Sin config y 1 repo ⇒ ese
    if len(repos) == 1:
        return str(repos[0]["id"])

    # (c) Sin config y >1 repos ⇒ error ambiguo
    if len(repos) > 1:
        available = ", ".join([r.get("name", "unknown") for r in repos])
        raise TrackerApiError(
            status=400,
            kind="ado_repo_ambiguous",
            message=f"Múltiples repos en ADO: {available}. Especificá 'repository' en project_config.",
        )

    raise TrackerApiError(
        status=404,
        kind="ado_repo_not_found",
        message=f"No hay repos en ADO para proyecto {project}",
    )


def _default_branch(provider, project: str | None) -> str:
    """Plan 95 F1.a — Helper para obtener la default branch de ADO.
    GET .../repositories/{id} → campo `defaultBranch`, STRIP del prefijo
    "refs/heads/".
    """
    from services.ado_client import AdoClient  # noqa: PLC0415

    client = AdoClient(project=project)
    repo_id = _resolve_repo_id(project)
    url = f"{client._base_proj}/_apis/git/repositories/{repo_id}?api-version=7.1"
    body = client._request("GET", url)
    default_branch = body.get("defaultBranch", "")
    # Strip "refs/heads/"
    if default_branch.startswith("refs/heads/"):
        return default_branch[len("refs/heads/"):]
    return default_branch


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


class DefinitionConfirmRequired(Exception):
    """Excepción para cuando ensure_yaml_definition requiere confirm=True (HITL)."""
    pass


def ensure_yaml_definition(project: str | None, yaml_path: str = "azure-pipelines.yml",
                           *, confirm: bool = False) -> dict:
    """Plan 95 F1.b — find_yaml_definition; si existe → {'id', 'name', 'created': False}.
    Si NO existe: exige confirm=True (HITL — crear una definition es mutante);
    sin confirm lanza DefinitionConfirmRequired. Crea con POST
    {base_proj}/_apis/build/definitions?api-version=7.1.
    """
    from services.ado_client import AdoClient  # noqa: PLC0415
    from services.tracker_provider import TrackerApiError  # noqa: PLC0415

    existing = find_yaml_definition(project, yaml_path)
    if existing:
        return {"id": existing["id"], "name": existing["name"], "created": False}

    # No existe: requiere confirm HITL
    if not confirm:
        raise DefinitionConfirmRequired(
            "La pipeline definition no existe en ADO. Confirmá para crearla (HITL)."
        )

    # Crear la definition
    client = AdoClient(project=project)
    repo_id = _resolve_repo_id(project)
    default_branch = _default_branch(None, project)  # noqa: PLW0621

    # Slug del proyecto/repo para el nombre
    from project_manager import get_project_config  # noqa: PLC0415
    cfg = get_project_config(project)
    slug = (cfg.get("repository") or project or "stacky").replace("/", "-").lower()

    url = f"{client._base_proj}/_apis/build/definitions?api-version=7.1"
    body = {
        "name": f"stacky-{slug}",
        "type": "build",
        "queueStatus": "enabled",
        "repository": {
            "id": repo_id,
            "type": "TfsGit",
            "defaultBranch": f"refs/heads/{default_branch}",
        },
        "process": {
            "type": 2,
            "yamlFilename": yaml_path,
        },
    }

    try:
        response = client._request("POST", url, body=body)
        return {
            "id": response.get("id"),
            "name": response.get("name"),
            "created": True,
        }
    except Exception as e:
        raise TrackerApiError(
            status=500,
            kind="ado_definition_create_failed",
            message=f"Error creando pipeline definition: {e}",
        ) from e
