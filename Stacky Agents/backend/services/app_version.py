"""A0 — Versión visible del deploy.

Fuente 1: DeployStackyAgents/VERSION.txt (primera línea stripped)
Fuente 2: frontend/package.json campo "version"
Fuente 3: "0.0.0-unknown"

Caché en _CACHED_VERSION (module-level) para no releer en cada request.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from runtime_paths import backend_root, app_root

logger = logging.getLogger("stacky.services.app_version")

_CACHED_VERSION: str | None = None


def _version_txt_path() -> Path:
    """Ruta a DeployStackyAgents/VERSION.txt (junto al directorio del backend)."""
    # En dev: backend_root() = .../Stacky Agents/backend
    # DeployStackyAgents está al mismo nivel que "Stacky Agents"
    return backend_root().parent.parent / "DeployStackyAgents" / "VERSION.txt"


def _package_json_path() -> Path:
    """Ruta a frontend/package.json."""
    return backend_root().parent / "frontend" / "package.json"


def get_app_version() -> str:
    """Retorna la versión del deploy, usando caché de módulo."""
    global _CACHED_VERSION
    if _CACHED_VERSION is not None:
        return _CACHED_VERSION

    # Fuente 1: VERSION.txt
    try:
        p = _version_txt_path()
        if p.exists():
            text = p.read_text(encoding="utf-8").strip().splitlines()
            if text and text[0].strip():
                _CACHED_VERSION = text[0].strip()
                return _CACHED_VERSION
    except Exception as exc:
        logger.debug("app_version: VERSION.txt no legible: %s", exc)

    # Fuente 2: frontend/package.json
    try:
        p = _package_json_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            v = data.get("version", "")
            if v:
                _CACHED_VERSION = str(v)
                return _CACHED_VERSION
    except Exception as exc:
        logger.debug("app_version: package.json no legible: %s", exc)

    # Fuente 3: fallback
    _CACHED_VERSION = "0.0.0-unknown"
    return _CACHED_VERSION
