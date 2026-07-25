"""tools/migrar_mantis_gitlab/migrator_mg_core.py — Plan 217 F4.

Generaliza el PATRÓN de `services/migrator_core.py` (plan_migration
read-only + orden topológico + snapshot con hash) para el origen Mantis.
NO edita `services/migrator_core.py` (C4 del plan): ese archivo es ADO-only
y no se toca ni se le importan símbolos escribibles.

Dos piezas de `migrator_core.py` se consideraron para reuso directo y se
descartaron a propósito (dejado documentado, no simplemente omitido):
  - `_TYPE_ORDER` (`services/migrator_core.py:14`, dict `{"Epic":0,
    "Issue":1,...}`): es ADO-específico (tipos de work item que Mantis no
    tiene). Este módulo define su PROPIO `_MG_TYPE_ORDER`, basado en el
    único criterio de jerarquía disponible en Mantis vía relaciones
    "child of": el issue tiene padre o no (2 niveles, no jerarquía
    arbitraria — el plan §7 no pide N niveles).
  - `_MARKER_TEMPLATE` (`services/migrator_core.py:24`, formato
    `stacky-migrated:ado:{ado_id}`): formato ADO. Este módulo define su
    propio `_MG_MARKER_TEMPLATE` (formato `mantis:{project_id}:{issue_id}`,
    tabla de mapeo §5 del plan, fila `id`).

Invariante READ-ONLY (mismo contrato que `migrator_core.plan_migration`):
`plan_migration()` SOLO invoca métodos `fetch_*` de `origin_adapter`. Nunca
llama nada de escritura — si el adapter pasado en un test no tuviera esos
métodos (p. ej. un fake mínimo con solo `fetch_*`), cualquier intento de
escribir explotaría por `AttributeError`. Esa ausencia ES la prueba de que
el dry-run es real, no una promesa de diseño.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Optional

from .mapping.category_map import map_category
from .mapping.custom_field_map import map_custom_fields
from .mapping.priority_severity_map import UnmappedPriorityError, map_priority, map_severity
from .mapping.status_map import map_status
from .mapping.tag_map import map_tags
from .mapping.user_map import UserMappingError, map_user
from .mapping.version_map import map_version

# Marker de idempotencia propio (§5 del plan, fila `id`; NO el de ADO).
_MG_MARKER_TEMPLATE = "<!-- stacky-migrated:mantis:{project_id}:{issue_id} -->"

# Orden topológico propio de Mantis — 2 niveles (sin padre / con padre),
# NO el `_TYPE_ORDER` de migrator_core.py (ver docstring del módulo).
_MG_TYPE_ORDER: dict[str, int] = {
    "no_parent": 0,
    "has_parent": 1,
}


# ── Dataclasses propias (no reusan MigrationOp/MigrationPlan de ADO) ──────


@dataclass(frozen=True)
class MgMigrationOp:
    op_kind: Literal["create_item", "post_comment", "upload_attachment", "create_issue_link"]
    mantis_issue_id: str
    dest_parent_mantis_id: Optional[str]
    payload: dict
    marker: str


@dataclass(frozen=True)
class MgMigrationPlan:
    ops: list[MgMigrationOp]
    counts_by_type: dict[str, int]
    warnings: list[str]
    skipped_at_plan: int = 0


# ── Helpers de extracción de campos del issue Mantis ──────────────────────


def _get_issue_id(issue: dict) -> str:
    return str(issue.get("id") or issue.get("mantis_issue_id") or "")


def _get_project_id(issue: dict) -> str:
    return str(issue.get("project_id") or "")


def _extract_parent_id(relationships: list[dict[str, Any]]) -> Optional[str]:
    """Busca en las relaciones del issue (forma `{"type": str, "target_issue_id": ...}`,
    ver `adapters/scraping_adapter.py:_parse_relationships_html`) una relación
    "child of" — el único criterio de jerarquía padre/hijo de 2 niveles que
    define este plan (§7: "no hace falta N niveles")."""
    for rel in relationships or []:
        rel_type = str(rel.get("type") or "").strip().lower()
        if "child of" in rel_type:
            target = rel.get("target_issue_id")
            if target is not None:
                return str(target)
    return None


def _build_description(issue: dict, custom_fields_mode: str) -> str:
    """§5 del plan: description + steps_to_reproduce + additional_information
    concatenados con encabezados Markdown, más el bloque de custom_fields si
    `custom_fields.mode == "metadata_block"`."""
    parts: list[str] = []
    description = (issue.get("description") or "").strip()
    if description:
        parts.append(f"## Descripción\n\n{description}")
    steps = (issue.get("steps_to_reproduce") or "").strip()
    if steps:
        parts.append(f"## Pasos para reproducir\n\n{steps}")
    extra = (issue.get("additional_information") or "").strip()
    if extra:
        parts.append(f"## Información adicional\n\n{extra}")
    if custom_fields_mode == "metadata_block":
        block = map_custom_fields(issue.get("custom_fields") or [])
        if block:
            parts.append(block)
    return "\n\n".join(parts)


def _build_payload(issue: dict, field_mapping: dict, user_mapping: dict, warnings: list[str]) -> dict:
    """Transforma un issue Mantis crudo a un payload de creación GitLab
    aplicando los `mapping/*.py` puros del batch anterior (F3). Nunca
    aborta por un valor sin mapear — cualquier gap se degrada a un
    fallback conocido y se registra en `warnings` (§8.1.4/§8.2.5 del plan:
    "se avisa antes de ejecutar", nunca abort silencioso)."""
    issue_id = _get_issue_id(issue)

    status_cfg = field_mapping.get("status") or {}
    gitlab_state, status_label, used_status_fallback = map_status(issue.get("status", ""), status_cfg)
    if used_status_fallback:
        warnings.append(
            f"issue {issue_id}: status Mantis {issue.get('status')!r} sin mapeo explícito, "
            "usando _unmapped_fallback"
        )

    labels: list[str] = [status_label]

    raw_priority = issue.get("priority")
    if raw_priority not in (None, ""):
        priority_cfg = field_mapping.get("priority") or {}
        # NO se pre-filtra por `int()`: el adapter de SCRAPING entrega el
        # NOMBRE de la prioridad ("high"/"alta"), no el ID numérico de la API
        # REST. `map_priority` acepta ambos (ver `resolve_priority_id`); el
        # pre-chequeo anterior descartaba el 100% de las prioridades leídas
        # por scraping antes siquiera de consultar al mapper.
        try:
            labels.append(
                map_priority(
                    raw_priority,
                    priority_cfg.get("scale") or {},
                    priority_cfg.get("label_prefix", "priority::"),
                )
            )
        except UnmappedPriorityError as exc:
            warnings.append(f"issue {issue_id}: {exc}")

    severity = issue.get("severity")
    if severity:
        severity_cfg = field_mapping.get("severity") or {}
        labels.append(map_severity(severity, severity_cfg.get("label_prefix", "severity::")))

    category = issue.get("category")
    if category:
        category_cfg = field_mapping.get("category") or {}
        labels.append(map_category(category, category_cfg.get("label_prefix", "category::")))

    tags_cfg = field_mapping.get("tags") or {}
    labels.extend(map_tags(issue.get("tags") or [], tags_cfg.get("label_prefix", "tag::")))

    version_cfg = field_mapping.get("version") or {}
    version_result = map_version(
        issue.get("target_version"),
        issue.get("fixed_in_version"),
        issue.get("affects_version") or issue.get("version"),
        version_cfg,
    )
    labels.extend(version_result["labels"])

    assignee = None
    handler = issue.get("handler")
    if handler:
        try:
            assignee = map_user(handler, user_mapping or {})
        except UserMappingError as exc:
            warnings.append(f"issue {issue_id}: {exc}")

    custom_fields_cfg = field_mapping.get("custom_fields") or {}
    description = _build_description(issue, custom_fields_cfg.get("mode", "metadata_block"))

    marker = _MG_MARKER_TEMPLATE.format(project_id=_get_project_id(issue), issue_id=issue_id)
    description = f"{description}\n\n{marker}" if description else marker

    return {
        "title": issue.get("summary", ""),
        "description": description,
        "state": gitlab_state,
        "labels": labels,
        "milestone": version_result["milestone"],
        "assignee": assignee,
    }


# ── plan_migration (invariante READ-ONLY) ─────────────────────────────────


def plan_migration(
    origin_adapter,
    existing_map: dict[str, str],
    field_mapping: dict,
    user_mapping: dict,
) -> MgMigrationPlan:
    """Lee TODO del origen Mantis (solo métodos `fetch_*` de `origin_adapter`,
    que cumple `adapters.base.MantisReadAdapter`) y arma el plan SIN escribir
    nada en el destino.

    `existing_map`: dict `{mantis_issue_id: status}` — mismo shape que
    produce `migrator_mg_map.get_full_mapping` reindexado por issue_id
    (status ∈ pending|done|partial|failed). Un issue con status "done" se
    saltea (idempotencia, §11 del plan); pending/partial/failed se
    re-planifican (no quedan atascados).

    `field_mapping`/`user_mapping`: dicts crudos (misma forma JSON que
    `migration_config.json` §4) — se pasan tal cual a los `mapping/*.py`
    puros de F3, que ya esperan esa forma.

    Orden topológico (2 niveles, §7 del plan): primero issues sin padre,
    después issues con padre (relación "child of" resuelta vía
    `origin_adapter.fetch_relationships`), para que el padre ya exista
    cuando F5/F6 (otro batch) resuelvan el link real contra GitLab.
    """
    issues = origin_adapter.fetch_all_issues()

    warnings: list[str] = []
    skipped_at_plan = 0
    ops: list[MgMigrationOp] = []

    for issue in issues:
        issue_id = _get_issue_id(issue)

        if existing_map.get(issue_id) == "done":
            skipped_at_plan += 1
            continue

        try:
            relationships = origin_adapter.fetch_relationships(issue.get("id"))
        except Exception:
            relationships = []
            warnings.append(f"issue {issue_id}: no se pudieron obtener relaciones")

        parent_id = _extract_parent_id(relationships)
        payload = _build_payload(issue, field_mapping, user_mapping, warnings)
        marker = _MG_MARKER_TEMPLATE.format(project_id=_get_project_id(issue), issue_id=issue_id)

        ops.append(
            MgMigrationOp(
                op_kind="create_item",
                mantis_issue_id=issue_id,
                dest_parent_mantis_id=parent_id,
                payload=payload,
                marker=marker,
            )
        )

    # Orden topológico estable: sin padre primero, con padre después.
    ops.sort(key=lambda op: _MG_TYPE_ORDER["has_parent" if op.dest_parent_mantis_id else "no_parent"])

    counts_by_type: dict[str, int] = {}
    for op in ops:
        counts_by_type[op.op_kind] = counts_by_type.get(op.op_kind, 0) + 1

    return MgMigrationPlan(
        ops=ops,
        counts_by_type=dict(sorted(counts_by_type.items())),
        warnings=warnings,
        skipped_at_plan=skipped_at_plan,
    )


def compute_plan_hash(plan: MgMigrationPlan) -> str:
    """Hash SHA-256 determinista del plan — mismo patrón que
    `_compute_plan_hash` de `api/migrator.py:48-55`: mismo plan -> mismo
    hash; un plan con 1 issue distinto -> hash distinto."""
    sorted_ids = sorted(op.mantis_issue_id for op in plan.ops if op.op_kind == "create_item")
    payload = json.dumps({"ids": sorted_ids, "counts": plan.counts_by_type}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


__all__ = [
    "MgMigrationOp",
    "MgMigrationPlan",
    "compute_plan_hash",
    "plan_migration",
]
