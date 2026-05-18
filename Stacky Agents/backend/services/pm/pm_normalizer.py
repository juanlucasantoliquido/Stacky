"""Normaliza payloads crudos de Azure DevOps a estructuras internas PM.

Funciones puras — sin acceso a DB ni a red. Reciben dicts de ADO y devuelven
dicts canónicos del dominio PM que el KPI engine consume.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _get_field(work_item: dict, field: str, default: Any = None) -> Any:
    return ((work_item.get("fields") or {}).get(field, default))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def normalize_work_item(work_item: dict) -> dict:
    """Convierte el dict crudo de un work item ADO a la estructura interna PM."""
    assigned_raw = _get_field(work_item, "System.AssignedTo")
    if isinstance(assigned_raw, dict):
        assigned_to = assigned_raw.get("uniqueName") or assigned_raw.get("displayName")
    elif isinstance(assigned_raw, str):
        assigned_to = assigned_raw
    else:
        assigned_to = None

    tags_raw = _get_field(work_item, "System.Tags") or ""
    tags = [t.strip() for t in tags_raw.split(";") if t.strip()] if tags_raw else []

    return {
        "ado_id": work_item.get("id"),
        "title": _get_field(work_item, "System.Title"),
        "work_item_type": _get_field(work_item, "System.WorkItemType"),
        "state": _get_field(work_item, "System.State"),
        "assigned_to": assigned_to,
        "iteration_path": _get_field(work_item, "System.IterationPath"),
        "area_path": _get_field(work_item, "System.AreaPath"),
        "priority": _get_field(work_item, "Microsoft.VSTS.Common.Priority"),
        "severity": _get_field(work_item, "Microsoft.VSTS.Common.Severity"),
        "story_points": _get_field(work_item, "Microsoft.VSTS.Scheduling.StoryPoints"),
        "tags": tags,
        "parent_ado_id": _get_field(work_item, "System.Parent"),
        "created_at": _parse_iso(_get_field(work_item, "System.CreatedDate")),
        "changed_at": _parse_iso(_get_field(work_item, "System.ChangedDate")),
        "closed_at": _parse_iso(_get_field(work_item, "Microsoft.VSTS.Common.ClosedDate")),
    }


def normalize_iteration(iteration: dict) -> dict:
    """Aplana el dict de iteración de ADO."""
    attrs = iteration.get("attributes") or {}
    return {
        "id": iteration.get("id"),
        "name": iteration.get("name"),
        "path": iteration.get("path"),
        "start_date": _parse_iso(attrs.get("startDate")),
        "end_date": _parse_iso(attrs.get("finishDate")),
        "timeframe": attrs.get("timeFrame"),
    }


def extract_state_transitions(revisions: list[dict]) -> list[dict]:
    """Reduce un listado de revisiones ADO a transiciones de estado.

    Devuelve una lista ordenada cronológicamente: [{state, entered_at, changed_by}].
    Solo emite una entrada cuando cambia `System.State` entre revisiones consecutivas.
    """
    transitions: list[dict] = []
    last_state: str | None = None
    for rev in revisions:
        fields = rev.get("fields") or {}
        state = fields.get("System.State")
        changed_at = _parse_iso(fields.get("System.ChangedDate"))
        if state is None or changed_at is None:
            continue
        if state == last_state:
            continue
        changed_by_raw = fields.get("System.ChangedBy")
        if isinstance(changed_by_raw, dict):
            changed_by = changed_by_raw.get("uniqueName") or changed_by_raw.get("displayName")
        else:
            changed_by = changed_by_raw if isinstance(changed_by_raw, str) else None
        transitions.append({
            "state": state,
            "entered_at": changed_at,
            "changed_by": changed_by,
        })
        last_state = state
    return transitions
