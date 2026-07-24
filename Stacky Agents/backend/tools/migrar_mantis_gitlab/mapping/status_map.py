"""tools/migrar_mantis_gitlab/mapping/status_map.py — Plan 217 F3.

Traduce un status de Mantis (string) a estado+label de GitLab según
`field_mapping.status` del `migration_config.json` (§4/§5 del plan).
Función pura, sin I/O ni estado.
"""
from __future__ import annotations


def map_status(mantis_status: str, field_mapping_status: dict) -> tuple[str, str, bool]:
    """Devuelve `(gitlab_state, label, used_fallback)`.

    `field_mapping_status` es el dict crudo de config (forma JSON de
    `field_mapping.status`: `{"new": {...}, ..., "_unmapped_fallback": {...}}`)
    — `config_schema.validate_config` ya garantiza que `_unmapped_fallback`
    existe (regla dura §4: ningún valor de Mantis sin mapeo explícito puede
    causar un abort silencioso).

    Si `mantis_status` no está mapeado explícitamente, cae a
    `_unmapped_fallback` y lo señala vía `used_fallback=True` para que el
    caller lo registre como advertencia (§8.2.5 del plan).
    """
    key = (mantis_status or "").strip().lower()
    entry = field_mapping_status.get(key)
    used_fallback = False
    if entry is None:
        entry = field_mapping_status["_unmapped_fallback"]
        used_fallback = True
    return entry["gitlab_state"], entry["label"], used_fallback


__all__ = ["map_status"]
