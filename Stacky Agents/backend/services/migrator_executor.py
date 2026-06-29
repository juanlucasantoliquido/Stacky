"""Plan 74 F4 — Ejecutor de migración (execute_migration + hydrate_map_from_destination).

Aplica cada op del MigrationPlan contra el destino con idempotencia por marker.
NO existe _apply_link (C2: el link viaja en create_item vía TrackerItem.parent_id).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from services.migrator_map import (
    get_gitlab_iid,
    upsert_mapping,
    ensure_map_schema,
)
from services.migrator_attachments import migrate_attachment  # importado a nivel módulo para poder parchear en tests
from services.tracker_provider import TrackerItem, TrackerApiError

_MARKER_RE = re.compile(r"<!--\s*stacky-migrated:ado:(\d+)\s*-->")


@dataclass
class MigrationResult:
    applied: int = 0
    skipped: int = 0
    failed: list = field(default_factory=list)          # [{ado_id, op_kind, error}]
    mapping_rows: list = field(default_factory=list)    # filas para bulk_upsert
    markers_used: list = field(default_factory=list)
    orphaned: list = field(default_factory=list)        # ado_ids creados sin parent


def execute_migration(plan, dest_provider, db, *,
                      stacky_project: str, migration_run: str,
                      existing_map: dict) -> MigrationResult:
    """Aplica cada op del plan contra dest_provider.

    existing_map debe construirse con hydrate_map_from_destination ANTES de llamar (F4b).
    Para create_item: si el ado_id ya está en existing_map → skip.
    Para post_comment: si comment_exists(marker) → skip.
    Para upload_attachment: delega a migrate_attachment.
    NO hay op_kind=link_parent (C2). El link va en TrackerItem.parent_id.
    """
    ensure_map_schema(db)
    # mutable copy — se actualiza tras cada create exitoso para que los hijos resuelvan su padre
    live_map: dict[str, str] = dict(existing_map)
    result = MigrationResult()
    # Incluir los items ya filtrados en el plan como "skipped"
    result.skipped += getattr(plan, "skipped_at_plan", 0)

    for op in plan.ops:
        try:
            if op.op_kind == "create_item":
                _apply_create(op, dest_provider, db, stacky_project, migration_run,
                               live_map, result)
            elif op.op_kind == "post_comment":
                _apply_comment(op, dest_provider, live_map, result)
            elif op.op_kind == "upload_attachment":
                _apply_attachment(op, dest_provider, live_map, result)
        except Exception as exc:
            result.failed.append({
                "ado_id": op.ado_id,
                "op_kind": op.op_kind,
                "error": str(exc),
            })

    return result


def _apply_create(op, dest_provider, db, stacky_project, migration_run, live_map, result):
    """Crea el item en el destino si no existe; actualiza live_map y persiste el mapeo."""
    if op.ado_id in live_map:
        result.skipped += 1
        return

    # Resolver parent_id → iid mapeado
    parent_iid = None
    if op.dest_parent_ado_id:
        parent_iid = live_map.get(op.dest_parent_ado_id)
        if parent_iid is None:
            result.orphaned.append(op.ado_id)

    description_with_marker = (op.payload.get("description_html") or "") + "\n" + op.marker
    item = TrackerItem(
        item_type=op.payload.get("item_type", "issue"),
        title=op.payload.get("title", ""),
        description_html=description_with_marker,
        labels=tuple(op.payload.get("labels") or []),
        assignee=op.payload.get("assignee"),
        parent_id=parent_iid,
    )

    created = dest_provider.create_item(item)
    iid = str(created.get("iid") or created.get("id") or "")
    web_url = created.get("web_url") or ""

    upsert_mapping(
        db,
        stacky_project=stacky_project,
        ado_id=op.ado_id,
        ado_type=op.ado_type,
        gitlab_iid=iid,
        gitlab_web_url=web_url,
        marker=op.marker,
        migration_run=migration_run,
    )
    live_map[op.ado_id] = iid
    result.applied += 1
    result.markers_used.append(op.marker)
    result.mapping_rows.append({
        "ado_id": op.ado_id, "gitlab_iid": iid, "web_url": web_url,
    })


def _apply_comment(op, dest_provider, live_map, result):
    """Postea el comentario si el marker no existe ya en el destino."""
    dest_iid = live_map.get(op.ado_id)
    if dest_iid is None:
        result.skipped += 1
        return

    if dest_provider.comment_exists(dest_iid, op.marker):
        result.skipped += 1
        return

    body = (op.payload.get("body") or "") + "\n" + op.marker
    dest_provider.post_comment(dest_iid, body)
    result.applied += 1


def _apply_attachment(op, dest_provider, live_map, result):
    """Descarga y sube el attachment si no está ya en la descripción del destino."""
    dest_iid = live_map.get(op.ado_id)
    if dest_iid is None:
        result.skipped += 1
        return

    attach_result = migrate_attachment(
        op.payload, dest_provider,
        dest_iid=dest_iid,
        ado_pat="",  # el PAT se obtiene del client_profile en el endpoint (F6)
    )
    if attach_result.get("verified"):
        result.applied += 1
    else:
        result.failed.append({
            "ado_id": op.ado_id,
            "op_kind": "upload_attachment",
            "error": attach_result.get("error", "upload failed"),
        })


# ── F4b: hydrate_map_from_destination (C4 — idempotencia ante DB vacía) ──────

def hydrate_map_from_destination(dest_provider, db, *, stacky_project: str) -> dict[str, str]:
    """Reconstruye el mapeo ado_id→iid desde el DESTINO (fuente de verdad).

    Lista los items del destino que portan el marker stacky-migrated:ado:{id}
    en su descripción, parsea el ado_id y hace upsert_mapping local.
    Devuelve el map fusionado (local ∪ destino).
    READ-ONLY sobre el destino: solo invoca fetch_*/get_*.
    """
    from services.migrator_map import get_full_mapping
    from services.tracker_provider import TrackerQuery

    ensure_map_schema(db)

    # Obtener el mapa local actual
    existing = {row["ado_id"]: row["gitlab_iid"] for row in get_full_mapping(db, stacky_project)}

    # Buscar items en el destino con markers stacky-migrated
    try:
        items = dest_provider.fetch_open_items(TrackerQuery())
    except Exception:
        return existing

    for item in items:
        desc = item.get("description") or item.get("description_html") or ""
        iid = str(item.get("iid") or item.get("id") or "")
        web_url = item.get("web_url") or ""
        item_type = item.get("item_type") or "issue"

        for match in _MARKER_RE.finditer(desc):
            ado_id = match.group(1)
            if ado_id not in existing:
                upsert_mapping(
                    db,
                    stacky_project=stacky_project,
                    ado_id=ado_id,
                    ado_type=item_type,
                    gitlab_iid=iid,
                    gitlab_web_url=web_url,
                    marker=match.group(0),
                    migration_run="hydrated",
                )
                existing[ado_id] = iid

    return existing
