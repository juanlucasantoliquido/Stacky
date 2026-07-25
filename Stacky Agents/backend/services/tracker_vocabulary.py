"""services/tracker_vocabulary.py -- Plan 218 F5.

Vocabulario canónico del dominio + alias legacy. PURO. CONGELADO por el Plan 218.

P6 — backward-compatible o no va: NADA se renombra. Los campos `ado_*` siguen
existiendo y funcionando (495 usos en 88 archivos del frontend). Lo único que cambia
es que el payload pasa a ser un SUPERCONJUNTO del actual.

Este módulo nombra a los dos proveedores por definición: está en
NEUTRAL_REGISTRY_ALLOWLIST del censo de F1.
"""
from __future__ import annotations

CANONICAL_FIELDS: tuple[str, ...] = (
    "external_id", "tracker_type", "tracker_project", "item_type",
    "title", "description", "tracker_state", "item_url",
    "parent_external_id", "assignee", "priority",
)

# canónico -> alias legacy que DEBE seguir emitiéndose (P6)
LEGACY_ALIASES: dict[str, str] = {
    "external_id": "ado_id",
    "tracker_state": "ado_state",
    "item_url": "ado_url",
    "parent_external_id": "parent_ado_id",
    "assignee": "assigned_to_ado",
    "item_type": "work_item_type",
    # C7: `tracker_project` mapea a `project` (el proyecto DEL TRACKER).
    # `stacky_project_name` NO es canónico: es identidad interna de Stacky.
    "tracker_project": "project",
}

_CANONICAL_BY_LEGACY: dict[str, str] = {v: k for k, v in LEGACY_ALIASES.items()}


def with_legacy_aliases(payload: dict) -> dict:
    """Devuelve payload + las claves legacy. NUNCA quita claves. Idempotente.

    Si la clave legacy YA viene en el payload, se respeta su valor: hay columnas
    legacy que no son derivables de la canónica (p. ej. `ado_id` existe aunque
    `external_id` sea NULL), y pisarlas sería una regresión.
    """
    out = dict(payload)
    for canonico, legacy in LEGACY_ALIASES.items():
        if canonico in out:
            out.setdefault(legacy, out[canonico])
    return out


def to_canonical(payload: dict) -> dict:
    """Acepta claves legacy o canónicas y devuelve solo canónicas.

    Con ambas presentes y distintas, gana la CANÓNICA (es la fuente de verdad nueva).
    """
    out: dict = {}
    for legacy, canonico in _CANONICAL_BY_LEGACY.items():
        if legacy in payload:
            out[canonico] = payload[legacy]
    for canonico in CANONICAL_FIELDS:
        if canonico in payload:
            out[canonico] = payload[canonico]
    return out
