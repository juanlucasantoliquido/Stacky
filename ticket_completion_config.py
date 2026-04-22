"""
ticket_completion_config.py — Config centralizada para el flujo de finalización
de ticket (auto-transition ADO, nota automática, commit con trailer AB#).

Decisión de diseño: NO se agrega un archivo de config nuevo. Se extiende el
existente ``Tools/Stacky/config.json`` con una sección ``ticket_completion``;
los proyectos pueden override-ear por ``projects/<X>/config.json`` siguiendo el
patrón ya establecido por ``issue_tracker`` (ver ``issue_provider/factory.py``).

Forma canónica del bloque::

    "ticket_completion": {
      "auto_transition_state": {
        "enabled": true,
        "target_state": "Doing"
      },
      "auto_post_note": {
        "enabled": true,
        "note_template": "Ticket completado via Stacky. Archivos modificados: {files_count}. Rama: {branch}.",
        "is_html": false
      },
      "auto_commit": {
        "enabled": true
      }
    }

Cada flag es independiente — se puede activar ``auto_commit`` sin
``auto_post_note`` ni ``auto_transition_state`` y viceversa.

Placeholders soportados en ``note_template``:
  - ``{ticket_id}``    — ID del ticket (ej. 27698)
  - ``{branch}``       — rama activa (o vacío si no se pudo detectar)
  - ``{files_count}``  — cantidad de archivos commiteados
  - ``{revision}``     — hash corto del commit (vacío si el commit no se hizo aún)
  - ``{commit_msg}``   — mensaje de commit (primera línea)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("stacky.ticket_completion_config")

_BASE_DIR = Path(__file__).resolve().parent
_GLOBAL_CONFIG = _BASE_DIR / "config.json"

# Defaults — garantizan que el flujo funcione aun si la sección no existe.
# target_state default = "Doing": seguimos el uso que hoy tiene Stacky
# (ver config.json.state_mapping). Típicamente un estado FINAL sería
# "Resolved" / "Done" / "Closed"; el usuario pidió "Doing", dejamos su palabra
# pero lo hacemos configurable — ver README interno.
_DEFAULTS: dict = {
    "auto_transition_state": {
        "enabled": False,
        "target_state": "Doing",
    },
    "auto_post_note": {
        "enabled": False,
        "note_template": (
            "Ticket completado vía Stacky.\n"
            "Archivos modificados: {files_count}\n"
            "Rama: {branch}\n"
            "Commit: {revision}"
        ),
        "is_html": False,
    },
    "auto_commit": {
        "enabled": True,  # el endpoint /api/git_commit YA hacía commit; lo
                         # dejamos ON por default para no romper el flujo actual.
    },
}


@dataclass
class CompletionStep:
    enabled: bool = False
    extra: dict = field(default_factory=dict)

    def get(self, key: str, default=None):
        return self.extra.get(key, default)


@dataclass
class CompletionConfig:
    auto_transition_state: CompletionStep = field(default_factory=CompletionStep)
    auto_post_note: CompletionStep = field(default_factory=CompletionStep)
    auto_commit: CompletionStep = field(default_factory=CompletionStep)

    def to_dict(self) -> dict:
        def _step(s: CompletionStep) -> dict:
            d = {"enabled": s.enabled}
            d.update(s.extra)
            return d
        return {
            "auto_transition_state": _step(self.auto_transition_state),
            "auto_post_note":        _step(self.auto_post_note),
            "auto_commit":           _step(self.auto_commit),
        }


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("No se pudo leer %s: %s", path, e)
        return {}


def _read_project_config(project_name: str | None) -> dict:
    if not project_name:
        return {}
    try:
        from project_manager import get_project_config
        return get_project_config(project_name) or {}
    except Exception as e:
        logger.debug("project_manager.get_project_config falló: %s", e)
        return {}


def _merge_dict(base: dict, override: dict) -> dict:
    """Merge shallow con override — los dicts anidados se mergean 1 nivel."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        else:
            out[k] = v
    return out


def load_completion_config(project_name: str | None = None) -> CompletionConfig:
    """Carga la config efectiva: defaults → global → proyecto."""
    global_block = _read_json(_GLOBAL_CONFIG).get("ticket_completion") or {}
    project_block = _read_project_config(project_name).get("ticket_completion") or {}

    effective = _merge_dict(_DEFAULTS, global_block)
    effective = _merge_dict(effective, project_block)

    def _build(step_key: str) -> CompletionStep:
        block = effective.get(step_key) or {}
        enabled = bool(block.get("enabled", False))
        extra = {k: v for k, v in block.items() if k != "enabled"}
        return CompletionStep(enabled=enabled, extra=extra)

    return CompletionConfig(
        auto_transition_state=_build("auto_transition_state"),
        auto_post_note=_build("auto_post_note"),
        auto_commit=_build("auto_commit"),
    )


def render_note_template(template: str, **context) -> str:
    """Renderiza ``template`` reemplazando placeholders ``{name}``.

    Seguro ante keys faltantes — no lanza KeyError; reemplaza por "".
    """
    if not template:
        return ""
    safe_ctx = {k: ("" if v is None else str(v)) for k, v in context.items()}
    try:
        return template.format_map(_SafeDict(safe_ctx))
    except Exception as e:
        logger.debug("render_note_template falló (%s) — devolviendo template crudo", e)
        return template


class _SafeDict(dict):
    """dict que devuelve "" ante keys faltantes (para str.format_map)."""

    def __missing__(self, key):
        return ""
