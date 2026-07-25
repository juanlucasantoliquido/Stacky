"""tools/migrar_mantis_gitlab/mapping/tag_map.py — Plan 217 F3.

Traduce los tags de un issue Mantis a labels GitLab `tag::X` (uno por tag,
§5 del plan). Función pura, sin I/O.
"""
from __future__ import annotations


def map_tags(tags: "list[str] | str | None", label_prefix: str = "tag::") -> list[str]:
    """Devuelve un label por etiqueta.

    Acepta también un STRING separado por comas: un adapter que entregue la
    celda de etiquetas sin parsear haría que un `for` la recorriera CARÁCTER
    a carácter, generando labels basura (`tag::S`, `tag::i`, …) — pasó con
    el literal "Sin etiquetas adjuntas." de Mantis.
    """
    if isinstance(tags, str):
        tags = [t for t in tags.replace(";", ",").split(",")]
    return [f"{label_prefix}{cleaned}" for tag in (tags or []) if (cleaned := (tag or "").strip())]


__all__ = ["map_tags"]
