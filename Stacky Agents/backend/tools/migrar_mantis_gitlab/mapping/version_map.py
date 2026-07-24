"""tools/migrar_mantis_gitlab/mapping/version_map.py — Plan 217 F3.

Traduce las 3 versiones de Mantis (`target_version`, `fixed_in_version`,
`affects_version`) a milestone/labels de GitLab según `field_mapping.version`
del config (§4/§5/§6 del plan): GitLab Milestone es un único slot, no dos
versiones (afectada/corregida) separadas, por eso cada campo se resuelve
independientemente a `milestone` o a un label con prefijo configurable.
Función pura, sin I/O.
"""
from __future__ import annotations

_MILESTONE_MODE = "milestone"
_LABEL_MODE_PREFIX = "label:"


def _resolve_slot(value: str | None, mode: str, out: dict) -> None:
    cleaned = (value or "").strip()
    if not cleaned:
        return
    if mode == _MILESTONE_MODE:
        out["milestone"] = cleaned
    elif mode.startswith(_LABEL_MODE_PREFIX):
        label_prefix = mode[len(_LABEL_MODE_PREFIX):]
        out["labels"].append(f"{label_prefix}{cleaned}")
    # Modo desconocido/no reconocido: no se inventa un destino. El caller
    # (fases posteriores) puede registrarlo como advertencia si hace falta.


def map_version(
    target_version: str | None,
    fixed_in_version: str | None,
    affects_version: str | None,
    field_mapping_version: dict,
) -> dict:
    """Devuelve `{"milestone": str | None, "labels": list[str]}` según
    `target_version_as`/`fixed_in_version_as`/`affects_version_as` de
    `field_mapping_version` (defaults iguales a los de `config_schema.VersionMapping`)."""
    out: dict = {"milestone": None, "labels": []}
    _resolve_slot(
        target_version,
        field_mapping_version.get("target_version_as", _MILESTONE_MODE),
        out,
    )
    _resolve_slot(
        fixed_in_version,
        field_mapping_version.get("fixed_in_version_as", "label:fixed_in::"),
        out,
    )
    _resolve_slot(
        affects_version,
        field_mapping_version.get("affects_version_as", "label:affects::"),
        out,
    )
    return out


__all__ = ["map_version"]
