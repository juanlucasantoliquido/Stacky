"""tools/migrar_mantis_gitlab/mapping/user_map.py — Plan 217 F3.

Traduce un username Mantis a la asignación GitLab según `user_mapping` del
`migration_config.json` (§4/§8.1.5 del plan). Función pura, sin I/O.
"""
from __future__ import annotations


class UserMappingError(Exception):
    """`default_fallback == "fail"` y el username Mantis no está mapeado
    explícitamente en `user_mapping.map` — regla dura: no se degrada en
    silencio a `unassigned`, el caller debe decidir qué hacer."""


def map_user(mantis_username: str, user_mapping: dict) -> str:
    """Devuelve el destino de asignación GitLab para `mantis_username`.

    Busca en `user_mapping["map"]`. Si no está mapeado, usa
    `user_mapping["default_fallback"]` (§4 del config, 3 valores válidos):
      - `"unassigned"` -> devuelve la cadena literal `"unassigned"`.
      - `"assign_to:<user>"` -> devuelve esa cadena tal cual (el caller la
        interpreta como "asignar a `<user>`").
      - `"fail"` -> lanza `UserMappingError` (sin fallback silencioso).
    """
    mapping = user_mapping.get("map") or {}
    resolved = mapping.get(mantis_username)
    if resolved:
        return resolved

    fallback = user_mapping.get("default_fallback", "unassigned")
    if fallback == "fail":
        raise UserMappingError(
            f"Usuario Mantis '{mantis_username}' no está mapeado en user_mapping.map "
            "y default_fallback='fail' (regla dura: no hay fallback silencioso)."
        )
    return fallback


__all__ = ["UserMappingError", "map_user"]
