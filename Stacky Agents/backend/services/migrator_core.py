"""Plan 74 F2 — Orquestador de migración (plan_migration).

Produce un MigrationPlan (lista de MigrationOp) a partir de leer el origen
por el puerto TrackerProvider. NUNCA escribe en el destino.

Invariante READ-ONLY: plan_migration solo invoca métodos fetch_*/get_* sobre origin.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# Orden topológico: los padres se crean antes que los hijos.
_TYPE_ORDER: dict[str, int] = {
    "Epic": 0,
    "Issue": 1,
    "User Story": 1,
    "Feature": 1,
    "Task": 2,
    "Bug": 2,
    "Test Case": 2,
}

_MARKER_TEMPLATE = "<!-- stacky-migrated:ado:{ado_id} -->"


@dataclass(frozen=True)
class MigrationOp:
    """Una operación del plan. op_kind ∈ {create_item, post_comment, upload_attachment}.
    NOTA: NO existe op_kind 'link_parent' (C2). El link se establece dentro de
    create_item pasando dest_parent_ado_id resuelto a iid en F4."""
    op_kind: Literal["create_item", "post_comment", "upload_attachment"]
    ado_id: str
    ado_type: str
    dest_parent_ado_id: Optional[str]   # ado_id del padre (F4 lo resuelve a iid via map)
    payload: dict
    marker: str


@dataclass(frozen=True)
class MigrationPlan:
    ops: list                            # list[MigrationOp], ORDENADAS topológicamente
    counts_by_type: dict[str, int]       # tipo → count de create_item ops (a migrar)
    warnings: list[str]
    skipped_at_plan: int = 0            # items filtrados por existing_map (ya migrados)


def _get_ado_id(item: dict) -> str:
    """Extrae el ado_id del item."""
    return str(item.get("id") or item.get("ado_id") or "")


def _get_ado_type(item: dict) -> str:
    return str(item.get("item_type") or item.get("type") or item.get("work_item_type") or "Issue")


def _get_parent(item: dict) -> Optional[str]:
    parent = item.get("parent")
    if parent is None:
        return None
    return str(parent) if parent else None


def _type_order(item_type: str) -> int:
    return _TYPE_ORDER.get(item_type, 1)


def _build_create_op(item: dict, *, existing_ado_ids: set[str]) -> tuple[MigrationOp, list[str]]:
    """Construye la op create_item y sus warnings."""
    ado_id = _get_ado_id(item)
    ado_type = _get_ado_type(item)
    parent_ado_id = _get_parent(item)
    warnings = []

    if parent_ado_id and parent_ado_id not in existing_ado_ids:
        warnings.append(
            f"padre ado_id {parent_ado_id} no está en el plan ni en existing_map; "
            f"item {ado_id} se creará huérfano (orphan)"
        )

    marker = _MARKER_TEMPLATE.format(ado_id=ado_id)
    op = MigrationOp(
        op_kind="create_item",
        ado_id=ado_id,
        ado_type=ado_type,
        dest_parent_ado_id=parent_ado_id,
        payload={
            "title": item.get("title", ""),
            "description_html": item.get("description", "") or item.get("description_html", ""),
            "labels": item.get("labels", []),
            "item_type": ado_type,
            "assignee": item.get("assignee"),
        },
        marker=marker,
    )
    return op, warnings


def _build_comment_ops(ado_id: str, ado_type: str, comments: list[dict]) -> list[MigrationOp]:
    ops = []
    for c in comments:
        comment_id = str(c.get("id") or "")
        marker = f"<!-- stacky-migrated-comment:ado:{ado_id}:{comment_id} -->"
        body = c.get("body") or c.get("text") or ""
        ops.append(MigrationOp(
            op_kind="post_comment",
            ado_id=ado_id,
            ado_type=ado_type,
            dest_parent_ado_id=None,
            payload={"body": body},
            marker=marker,
        ))
    return ops


def _build_attachment_ops(ado_id: str, ado_type: str, attachments: list[dict]) -> list[MigrationOp]:
    ops = []
    for a in attachments:
        attach_id = str(a.get("id") or a.get("name") or "")
        marker = f"<!-- stacky-migrated-attach:ado:{ado_id}:{attach_id} -->"
        ops.append(MigrationOp(
            op_kind="upload_attachment",
            ado_id=ado_id,
            ado_type=ado_type,
            dest_parent_ado_id=None,
            payload=dict(a),
            marker=marker,
        ))
    return ops


def plan_migration(
    origin,
    dest,
    *,
    stacky_project: str,
    existing_map: dict[str, str],
) -> MigrationPlan:
    """Lee del origen por el puerto y produce el plan SIN escribir en dest.

    Para cada item del origen:
      - si ado_id in existing_map -> skip
      - sino -> genera op create_item + ops comment + ops attachment

    Las ops se ORDENAN por _TYPE_ORDER (Epic→Issue/Story→Task).
    Un padre ausente del origen Y del plan -> warning (item se creará huérfano).
    NO emite ops de linkeo: el link viaja en el create_item (DECISIÓN C2).
    """
    from services.tracker_provider import TrackerQuery
    query = TrackerQuery()
    items = origin.fetch_open_items(query)

    # Calcular set de ado_ids en el plan (para detectar huérfanos)
    all_ado_ids_in_plan = {_get_ado_id(i) for i in items}
    all_known_ids = set(existing_map.keys()) | all_ado_ids_in_plan

    create_ops: list[MigrationOp] = []
    comment_ops: list[MigrationOp] = []
    attach_ops: list[MigrationOp] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}
    skipped_at_plan: int = 0

    for item in items:
        ado_id = _get_ado_id(item)
        ado_type = _get_ado_type(item)

        if ado_id in existing_map:
            skipped_at_plan += 1
            continue  # ya migrado

        op, warns = _build_create_op(item, existing_ado_ids=all_known_ids)
        create_ops.append(op)
        warnings.extend(warns)
        counts[ado_type] = counts.get(ado_type, 0) + 1

        # Comentarios
        try:
            comments = origin.fetch_all_comments(ado_id)
            comment_ops.extend(_build_comment_ops(ado_id, ado_type, comments))
        except Exception:
            warnings.append(f"No se pudieron obtener comentarios de ado_id={ado_id}")

        # Attachments
        try:
            attachments = origin.fetch_attachments(ado_id)
            attach_ops.extend(_build_attachment_ops(ado_id, ado_type, attachments))
        except Exception:
            warnings.append(f"No se pudieron obtener attachments de ado_id={ado_id}")

    # Orden topológico: Epic → Issue/Story → Task
    create_ops.sort(key=lambda o: _type_order(o.ado_type))

    # counts determinista (ordenado alfabético)
    counts = dict(sorted(counts.items()))

    all_ops: list[MigrationOp] = create_ops + comment_ops + attach_ops

    return MigrationPlan(ops=all_ops, counts_by_type=counts, warnings=warnings,
                         skipped_at_plan=skipped_at_plan)
