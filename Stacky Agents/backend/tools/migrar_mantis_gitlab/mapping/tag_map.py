"""tools/migrar_mantis_gitlab/mapping/tag_map.py — Plan 217 F3.

Traduce los tags de un issue Mantis a labels GitLab `tag::X` (uno por tag,
§5 del plan). Función pura, sin I/O.
"""
from __future__ import annotations


def map_tags(tags: list[str], label_prefix: str = "tag::") -> list[str]:
    return [f"{label_prefix}{cleaned}" for tag in (tags or []) if (cleaned := (tag or "").strip())]


__all__ = ["map_tags"]
