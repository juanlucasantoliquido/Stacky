"""tools/migrar_mantis_gitlab/mapping/category_map.py — Plan 217 F3.

Traduce la categoría de un issue Mantis a un label GitLab `category::X`
(§5/§6 del plan: GitLab no tiene equivalente 1:1 de "categoría de proyecto").
Función pura, sin I/O.
"""
from __future__ import annotations


def map_category(category: str, label_prefix: str = "category::") -> str:
    return f"{label_prefix}{(category or '').strip()}"


__all__ = ["map_category"]
