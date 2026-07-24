"""tools/migrar_mantis_gitlab/mapping/priority_severity_map.py — Plan 217 F3.

Traduce prioridad/severidad de Mantis a labels de GitLab (§5 del plan).
`map_priority` reusa `_PRIORITY_MAP` (`services/mantis_client.py:57`) para
convertir el ID crudo de prioridad Mantis a la escala interna 1-5 (1=crítico,
5=trivial), y de ahí a la clave configurada en `field_mapping.priority.scale`
(§4 del config, ej. `{"1": "P1-critica", ...}`). Funciones puras, sin I/O.
"""
from __future__ import annotations

from services.mantis_client import _PRIORITY_MAP


class UnmappedPriorityError(Exception):
    """El ID de prioridad Mantis no está en `_PRIORITY_MAP` (o no tiene
    escala 1-5 asignada, o la escala resultante no está en `scale`).

    No se inventa un fallback silencioso acá — a diferencia de status,
    `field_mapping.priority` no define un `_unmapped_fallback` propio en el
    config (§4); el llamador decide cómo degradar ante este gap."""


def map_priority(priority_id: int, scale: dict, label_prefix: str = "priority::") -> str:
    """Devuelve el label completo de prioridad (`f"{label_prefix}{scale[...]}"`).

    Lanza `UnmappedPriorityError` si `priority_id` no está en `_PRIORITY_MAP`,
    si mapea a `None` (ej. Mantis "none"), o si la escala resultante no está
    en `scale` — nunca inventa un valor.
    """
    if priority_id not in _PRIORITY_MAP:
        raise UnmappedPriorityError(
            f"El ID de prioridad Mantis {priority_id!r} no está en _PRIORITY_MAP "
            "(services/mantis_client.py)."
        )
    scale_level = _PRIORITY_MAP[priority_id]
    if scale_level is None:
        raise UnmappedPriorityError(
            f"El ID de prioridad Mantis {priority_id!r} no tiene escala 1-5 asignada "
            "(_PRIORITY_MAP devuelve None para valores como 'none')."
        )
    scale_key = str(scale_level)
    if scale_key not in scale:
        raise UnmappedPriorityError(
            f"La escala de prioridad '{scale_key}' no está en field_mapping.priority.scale."
        )
    return f"{label_prefix}{scale[scale_key]}"


def map_severity(severity: str, label_prefix: str = "severity::") -> str:
    """Label de severidad Mantis -> GitLab. Mantis expone `severity` como
    texto libre (no hay tabla de traducción como en prioridad) — simple
    `f"{label_prefix}{severity}"`."""
    return f"{label_prefix}{(severity or '').strip()}"


__all__ = ["UnmappedPriorityError", "map_priority", "map_severity"]
