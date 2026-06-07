"""
UI Sections Store
=================
Persistencia de visibilidad de las pestañas de navegación principal.

Archivo en disco (``data/ui_sections.json``)::

    {
      "version": "1.0",
      "updated_at": "<iso>",
      "sections": {
      "pm":     { "visible": true },
      "logs":   { "visible": true },
      "docs":   { "visible": true },
      "memory": { "visible": true }
      }
    }

Reglas:
- Solo se persisten secciones **opcionales** (``pm``, ``logs``, ``docs``,
  ``memory``).
- Las secciones ``team``, ``tickets`` y ``settings`` son obligatorias y nunca
  aparecen en el JSON ni pueden togglearse desde la UI.
- Defensa en profundidad: si alguien edita el JSON a mano e incluye claves
  fuera de ``OPTIONAL_SECTIONS``, son ignoradas al leer.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("stacky_agents.ui_sections_store")

# Única fuente de verdad de qué secciones se pueden ocultar.
OPTIONAL_SECTIONS: frozenset[str] = frozenset({"pm", "logs", "docs", "memory"})

_CONFIG_FILE = Path("data/ui_sections.json")


class ValidationError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_raw() -> dict:
    try:
        text = _CONFIG_FILE.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("formato inesperado — root no es objeto")
        return data
    except FileNotFoundError:
        return {"version": "1.0", "updated_at": _now_iso(), "sections": {}}
    except (json.JSONDecodeError, ValueError) as exc:
        _log.warning(
            "ui_sections.json inválido en %s (%s) — iniciando vacío",
            _CONFIG_FILE, exc,
        )
        return {"version": "1.0", "updated_at": _now_iso(), "sections": {}}


def _write(data: dict) -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    _CONFIG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_sections() -> dict[str, dict[str, Any]]:
    """
    Devuelve el estado de visibilidad de todas las secciones opcionales,
    rellenando defaults (``visible: True``) cuando falten en el archivo.

    Solo emite claves dentro de ``OPTIONAL_SECTIONS`` — claves espurias en el
    JSON son ignoradas.
    """
    raw = _read_raw().get("sections") or {}
    if not isinstance(raw, dict):
        raw = {}
    result: dict[str, dict[str, Any]] = {}
    for key in OPTIONAL_SECTIONS:
        entry = raw.get(key) if isinstance(raw.get(key), dict) else None
        visible = entry.get("visible", True) if entry else True
        result[key] = {"visible": bool(visible)}
    return result


def set_section_visible(section: str, visible: bool) -> dict[str, dict[str, Any]]:
    """
    Actualiza la visibilidad de una sección opcional.

    Raises:
        ValidationError: si ``section`` no está en ``OPTIONAL_SECTIONS``.
    """
    if not isinstance(section, str) or section not in OPTIONAL_SECTIONS:
        raise ValidationError(
            f"section '{section}' no es opcional. "
            f"Valores permitidos: {sorted(OPTIONAL_SECTIONS)}."
        )
    if not isinstance(visible, bool):
        raise ValidationError("visible debe ser booleano.")

    data = _read_raw()
    sections = data.get("sections")
    if not isinstance(sections, dict):
        sections = {}
    sections[section] = {"visible": visible}
    # Limpiar claves no opcionales heredadas de ediciones manuales.
    cleaned = {k: v for k, v in sections.items() if k in OPTIONAL_SECTIONS}
    data["sections"] = cleaned
    _write(data)
    return get_sections()


def seed_defaults_if_empty() -> int:
    """
    Si ``data/ui_sections.json`` no existe, lo crea vacío (con todas las
    opcionales en su default ``visible: True``).
    """
    if _CONFIG_FILE.exists():
        return 0
    _write({"version": "1.0", "sections": {}})
    _log.info("ui_sections seed: archivo inicial escrito en %s", _CONFIG_FILE)
    return 1
