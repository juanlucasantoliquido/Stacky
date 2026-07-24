"""tools/migrar_mantis_gitlab/mapping/custom_field_map.py — Plan 217 F3.

Arma el bloque Markdown de campos personalizados de Mantis que no tienen
equivalente nativo en GitLab (§6 del plan: "Campos personalizados
(custom_fields) definidos por instalación" -> tabla Markdown al final de la
descripción, `field_mapping.custom_fields.mode == "metadata_block"`).
Función pura, sin I/O.
"""
from __future__ import annotations

from typing import Any

_HEADING = "## Campos personalizados (Mantis)"


def map_custom_fields(custom_fields: list[dict[str, Any]]) -> str:
    """Devuelve el bloque Markdown completo (encabezado + tabla), o cadena
    vacía si `custom_fields` está vacío/no trae entradas con nombre (no
    agrega una tabla vacía sin sentido a la descripción)."""
    rows: list[str] = []
    for field in custom_fields or []:
        name = str(field.get("name") or field.get("field") or "").strip()
        if not name:
            continue
        value = str(field.get("value") or "").strip()
        # Escapar '|' literal para no romper la tabla Markdown; los saltos
        # de línea se colapsan a <br> (Markdown de tablas es de una línea).
        name = name.replace("|", "\\|")
        value = value.replace("|", "\\|").replace("\n", "<br>")
        rows.append(f"| {name} | {value} |")

    if not rows:
        return ""

    lines = [_HEADING, "", "| Campo | Valor |", "|---|---|", *rows]
    return "\n".join(lines)


__all__ = ["map_custom_fields"]
