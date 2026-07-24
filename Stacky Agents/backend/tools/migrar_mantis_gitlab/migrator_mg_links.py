"""tools/migrar_mantis_gitlab/migrator_mg_links.py — Plan 217 Batch 4, F6b
(§7, §16 fila F6: relaciones tipadas -> GitLab Issue Links API).

Segunda pasada de la migración (§7 del plan: corre DESPUÉS de que
`execute_migration` ya creó los issues de ambos extremos, "ya que ambos
extremos existen"). Traduce relaciones tipadas Mantis a GitLab Issue Links
vía `writer.create_issue_link` (agregado a `DestinationWriter` en F4).

`parent_child` NO pasa por acá — se resuelve en `create_item` vía
`payload["dest_parent_gitlab_iid"]` (ver `migrator_mg_executor._apply_create_item`),
porque GitLab Issue Links API es una relación simétrica issue<->issue
(relates_to/blocks/is_blocked_by), no una jerarquía padre-hijo nativa como
la que resuelve `_link_parent` (gitlab_provider.py:102) para Epics/parent_id.

NOTA DE IMPRECISIÓN DEL PLAN (documentada, no oculta): el batch especifica
la firma `migrate_relationships(relationships, writer, mapping_lookup,
field_mapping_relationships)` sin un parámetro separado para "el issue
Mantis origen actual", pero da como ejemplo de shape de relación
`{"type": ..., "target_mantis_id": ...}` (sin `source_mantis_id`). El shape
REAL que ya produce `adapters/scraping_adapter.py:_parse_relationships_html`
es `{"type": str, "target_issue_id": int|None}` (tampoco lleva el origen,
porque `fetch_relationships(issue_id)` ya está scopeado a un issue). Para
que este módulo sea usable en ambos casos, sin adivinar un default
silencioso, se resuelve así:
  - se acepta `target_mantis_id` (nombre del batch) O `target_issue_id`
    (nombre real del adapter) indistintamente;
  - se exige `source_mantis_id` explícito en cada relación (el caller —
    fuera de este batch, la orquestación F9 — debe normalizar cada
    relación con el ID Mantis del issue actual antes de pasarla acá); una
    relación sin `source_mantis_id` se reporta como `failed`, nunca se
    asume un origen implícito.
"""
from __future__ import annotations

from .destination_writer import DestinationWriter

# Relaciones para las que GitLab Issue Links API no tiene equivalente 1:1
# (§6 del plan: "no tiene 'duplicate of' nativo salvo GitLab Premium"): se
# mapean a `relates_to` igual (vía field_mapping_relationships), PERO
# además se anota el tipo original de Mantis en un comentario aparte.
_NO_NATIVE_EQUIVALENT = frozenset({"duplicate_of", "has_duplicate"})

# `parent_child` se resuelve en create_item (dest_parent_gitlab_iid), nunca
# como Issue Link — se saltea explícitamente acá, no por ausencia de mapeo.
_PARENT_CHILD_TYPE = "parent_child"


def _extract_target_mantis_id(rel: dict) -> "str | None":
    target = rel.get("target_mantis_id")
    if target is None:
        target = rel.get("target_issue_id")
    return str(target) if target is not None else None


def migrate_relationships(
    relationships: list[dict],
    writer: DestinationWriter,
    mapping_lookup: dict[str, str],
    field_mapping_relationships: dict,
) -> list[dict]:
    """Por cada relación Mantis, resuelve `source_iid`/`target_iid` vía
    `mapping_lookup` (dict `mantis_issue_id -> gitlab_iid`, viene del
    `live_map` post-`execute_migration`) y crea el Issue Link tipado
    correspondiente.

    Relaciones cuyo target (o source) todavía no está migrado se SALTEAN
    con un warning en el resultado — nunca explotan (razón por la que esto
    es una segunda pasada, §7 del plan).

    Devuelve `list[dict]` con `{"status": "migrated"|"skipped"|"failed",
    "type": ..., ...}` por relación, para que el reporte (F7, otro batch)
    lo consuma."""
    results: list[dict] = []

    for rel in relationships:
        rel_type = str(rel.get("type") or "")
        source_mantis_id = rel.get("source_mantis_id")
        target_mantis_id = _extract_target_mantis_id(rel)

        if not source_mantis_id or not target_mantis_id:
            results.append({
                "status": "failed",
                "type": rel_type,
                "error": "relación sin source_mantis_id/target_mantis_id resolubles",
            })
            continue

        if rel_type == _PARENT_CHILD_TYPE:
            results.append({
                "status": "skipped",
                "type": rel_type,
                "reason": "parent_child se resuelve en create_item (dest_parent_gitlab_iid), no en Issue Links",
            })
            continue

        source_iid = mapping_lookup.get(str(source_mantis_id))
        target_iid = mapping_lookup.get(str(target_mantis_id))

        if not source_iid:
            results.append({
                "status": "skipped",
                "type": rel_type,
                "reason": f"source_mantis_id {source_mantis_id} aún no migrado",
            })
            continue
        if not target_iid:
            results.append({
                "status": "skipped",
                "type": rel_type,
                "reason": f"target_mantis_id {target_mantis_id} aún no migrado",
            })
            continue

        link_type = field_mapping_relationships.get(rel_type)
        if not link_type:
            results.append({
                "status": "failed",
                "type": rel_type,
                "error": f"tipo de relación Mantis {rel_type!r} sin mapeo en field_mapping.relationships",
            })
            continue

        try:
            writer.create_issue_link(source_iid, target_iid, link_type)
            if rel_type in _NO_NATIVE_EQUIVALENT:
                writer.post_comment(
                    source_iid,
                    f"Relación original en Mantis: {rel_type}",
                )
            results.append({"status": "migrated", "type": rel_type, "link_type": link_type})
        except Exception as exc:
            results.append({"status": "failed", "type": rel_type, "error": str(exc)})

    return results


__all__ = ["migrate_relationships"]
