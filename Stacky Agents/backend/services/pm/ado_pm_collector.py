"""Collector de Azure DevOps para PM Intelligence Suite.

Extiende `AdoClient` con llamadas a iterations y revisions que el cliente base
no expone. NO modifica `ado_client.py` — compone con él reutilizando su auth
y `_request` privado (alias intencional, mismo módulo Stacky).

Endpoints ADO usados:
- GET _apis/work/teamsettings/iterations           — lista iteraciones del team
- GET _apis/work/teamsettings/iterations/{id}      — detalle (start/end dates)
- POST _apis/wit/wiql                              — WIQL para work items del sprint
- GET _apis/wit/workitems/{id}/revisions           — histórico de cambios (state transitions)

Fase 1 MVP: solo lectura. No publica ni modifica work items en ADO.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Iterable

from services.ado_client import AdoApiError, AdoClient

logger = logging.getLogger("stacky_agents.pm.collector")

_API_VERSION = "7.1"
_API_VERSION_WORK = "7.1-preview.1"

_WIQL_BY_ITERATION = (
    "SELECT [System.Id] FROM WorkItems "
    "WHERE [System.TeamProject] = @project "
    "AND [System.IterationPath] = '{iteration_path}' "
    "ORDER BY [System.ChangedDate] DESC"
)


def fetch_iterations(client: AdoClient, team: str | None = None) -> list[dict]:
    """Devuelve iteraciones del team. Si no se pasa team, usa el default del project.

    Response shape (per iteration):
      {"id": "...", "name": "Sprint 42", "path": "Project\\Sprint 42",
       "attributes": {"startDate": "...", "finishDate": "...", "timeFrame": "current|future|past"}}
    """
    team_segment = f"/{urllib.parse.quote(team)}" if team else ""
    url = (
        f"{client._base_proj}{team_segment}/_apis/work/teamsettings/iterations"
        f"?api-version={_API_VERSION_WORK}"
    )
    try:
        data = client._request("GET", url)
    except AdoApiError as e:
        logger.warning("fetch_iterations falló: %s", e)
        return []
    return data.get("value") or []


def fetch_current_iteration(client: AdoClient, team: str | None = None) -> dict | None:
    """Iteración activa según ADO ($timeframe=current)."""
    team_segment = f"/{urllib.parse.quote(team)}" if team else ""
    url = (
        f"{client._base_proj}{team_segment}/_apis/work/teamsettings/iterations"
        f"?$timeframe=current&api-version={_API_VERSION_WORK}"
    )
    try:
        data = client._request("GET", url)
    except AdoApiError as e:
        logger.warning("fetch_current_iteration falló: %s", e)
        return None
    items = data.get("value") or []
    return items[0] if items else None


def fetch_work_items_by_iteration(client: AdoClient, iteration_path: str) -> list[dict]:
    """Trae work items de una iteración específica con campos PM relevantes."""
    safe_path = iteration_path.replace("'", "''")
    wiql = _WIQL_BY_ITERATION.format(iteration_path=safe_path)

    wiql_url = f"{client._base_proj}/_apis/wit/wiql?api-version={_API_VERSION}"
    try:
        result = client._request("POST", wiql_url, {"query": wiql})
    except AdoApiError as e:
        logger.warning("WIQL by iteration falló: %s", e)
        return []
    ids = [int(w["id"]) for w in (result.get("workItems") or []) if w.get("id") is not None]
    if not ids:
        return []
    return _batch_get_pm_fields(client, ids)


def _batch_get_pm_fields(client: AdoClient, ids: list[int], page: int = 200) -> list[dict]:
    fields = [
        "System.Id",
        "System.Title",
        "System.State",
        "System.WorkItemType",
        "System.AssignedTo",
        "System.CreatedDate",
        "System.ChangedDate",
        "System.IterationPath",
        "System.AreaPath",
        "System.Tags",
        "Microsoft.VSTS.Common.Priority",
        "Microsoft.VSTS.Common.Severity",
        "Microsoft.VSTS.Scheduling.StoryPoints",
        "Microsoft.VSTS.Common.ClosedDate",
        "System.Parent",
    ]
    fields_qs = ",".join(fields)
    out: list[dict] = []
    for i in range(0, len(ids), page):
        chunk = ids[i : i + page]
        ids_qs = ",".join(str(x) for x in chunk)
        url = (
            f"{client._base_proj}/_apis/wit/workitems"
            f"?ids={ids_qs}&fields={urllib.parse.quote(fields_qs)}"
            f"&api-version={_API_VERSION}"
        )
        try:
            data = client._request("GET", url)
        except AdoApiError as e:
            logger.warning("batch_get_pm_fields chunk falló: %s", e)
            continue
        out.extend(data.get("value") or [])
    return out


def fetch_revisions(client: AdoClient, ado_id: int) -> list[dict]:
    """Devuelve revisiones del work item — base para cycle_time y blocked_time.

    Cada revisión incluye `fields.System.State`, `fields.System.ChangedDate`,
    `revisedBy`. Sin filtros, top default ADO (~200).
    """
    url = (
        f"{client._base_proj}/_apis/wit/workitems/{ado_id}/revisions"
        f"?api-version={_API_VERSION}"
    )
    try:
        data = client._request("GET", url)
    except AdoApiError as e:
        logger.warning("fetch_revisions(%s) falló: %s", ado_id, e)
        return []
    return data.get("value") or []


def fetch_revisions_for_many(
    client: AdoClient, ado_ids: Iterable[int]
) -> dict[int, list[dict]]:
    """Trae revisiones para un conjunto de work items. Devuelve {ado_id: revisions[]}."""
    out: dict[int, list[dict]] = {}
    for ado_id in ado_ids:
        out[int(ado_id)] = fetch_revisions(client, int(ado_id))
    return out
