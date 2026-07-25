"""tools/migrar_mantis_gitlab/mapping/priority_severity_map.py — Plan 217 F3.

Traduce prioridad/severidad de Mantis a labels de GitLab (§5 del plan).
`map_priority` reusa `_PRIORITY_MAP` (`services/mantis_client.py:57`) para
convertir el ID crudo de prioridad Mantis a la escala interna 1-5 (1=crítico,
5=trivial), y de ahí a la clave configurada en `field_mapping.priority.scale`
(§4 del config, ej. `{"1": "P1-critica", ...}`). Funciones puras, sin I/O.
"""
from __future__ import annotations

import unicodedata

from services.mantis_client import _PRIORITY_MAP

# El adapter de SCRAPING lee la prioridad de la tabla HTML, donde Mantis
# muestra el NOMBRE traducido ("high"/"alta"), no el ID numérico que sí trae
# la API REST. Sin esta tabla, toda migración por scraping perdía el 100% de
# las prioridades (degradaba a advertencia en cada issue). Nombres estándar
# de MantisBT en inglés y en la traducción es_ES.
_PRIORITY_NAME_TO_ID: dict[str, int] = {
    "none": 10, "ninguna": 10, "sin prioridad": 10,
    "low": 20, "baja": 20,
    "normal": 30, "media": 30,
    "high": 40, "alta": 40,
    "urgent": 50, "urgente": 50,
    "immediate": 60, "inmediata": 60, "inmediato": 60,
}


def _normalize_name(raw: str) -> str:
    text = unicodedata.normalize("NFKD", str(raw or "").strip().lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def resolve_priority_id(priority: "int | str") -> int:
    """Acepta el ID numérico de Mantis (API REST) o el nombre mostrado en la
    UI (scraping), en inglés o español. Lanza `UnmappedPriorityError` si no
    reconoce el valor — nunca adivina."""
    if isinstance(priority, bool):
        raise UnmappedPriorityError(f"Prioridad inválida: {priority!r}")
    if isinstance(priority, int):
        return priority
    raw = str(priority).strip()
    if raw.isdigit():
        return int(raw)
    name = _normalize_name(raw)
    if name in _PRIORITY_NAME_TO_ID:
        return _PRIORITY_NAME_TO_ID[name]
    raise UnmappedPriorityError(
        f"La prioridad Mantis {priority!r} no es un ID numérico ni un nombre "
        f"conocido (esperado uno de: {sorted(set(_PRIORITY_NAME_TO_ID))})."
    )


class UnmappedPriorityError(Exception):
    """El ID de prioridad Mantis no está en `_PRIORITY_MAP` (o no tiene
    escala 1-5 asignada, o la escala resultante no está en `scale`).

    No se inventa un fallback silencioso acá — a diferencia de status,
    `field_mapping.priority` no define un `_unmapped_fallback` propio en el
    config (§4); el llamador decide cómo degradar ante este gap."""


def map_priority(priority_id: "int | str", scale: dict, label_prefix: str = "priority::") -> str:
    """Devuelve el label completo de prioridad (`f"{label_prefix}{scale[...]}"`).

    Acepta tanto el ID numérico de Mantis (API REST) como el nombre mostrado
    en la UI (scraping, inglés o español) — ver `resolve_priority_id`.

    Lanza `UnmappedPriorityError` si no reconoce la prioridad, si mapea a
    `None` (ej. Mantis "none"), o si la escala resultante no está en `scale`
    — nunca inventa un valor.
    """
    priority_id = resolve_priority_id(priority_id)
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


__all__ = [
    "UnmappedPriorityError",
    "map_priority",
    "map_severity",
    "resolve_priority_id",
]
