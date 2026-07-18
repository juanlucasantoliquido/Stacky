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


# ─────────────────────────────────────────────────────────────────────────────
# Plan 163 F1 — identidad de build (source_commit / built_at / repo_head / drift)
# ─────────────────────────────────────────────────────────────────────────────
import subprocess
import time

_CACHED_SOURCE_COMMIT: str | None = None
_SOURCE_COMMIT_RESOLVED = False   # distinguir "no resuelto aun" de "resuelto a None"
_CACHED_BUILT_AT: str | None = None
_BUILT_AT_RESOLVED = False
_REPO_HEAD_CACHE: tuple[float, str | None] | None = None   # (timestamp, value)
_REPO_HEAD_TTL_SECONDS = 10.0
_MANIFEST_PRESENT: bool | None = None   # C9: presencia del manifest cacheada (cero I/O por request)


def _manifest_present() -> bool:
    """True si existe release-manifest.json. Cacheado a nivel modulo (C9)."""
    global _MANIFEST_PRESENT
    if _MANIFEST_PRESENT is None:
        try:
            _MANIFEST_PRESENT = _release_manifest_path().exists()
        except Exception:  # noqa: BLE001
            _MANIFEST_PRESENT = False
    return _MANIFEST_PRESENT


def _release_manifest_path() -> Path:
    """release-manifest.json vive en la raiz del release (app_root en deploy)."""
    from runtime_paths import app_root
    return app_root() / "release-manifest.json"


def _read_manifest() -> dict | None:
    try:
        p = _release_manifest_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("app_version: manifest no legible: %s", exc)
    return None


def _git_short_head() -> str | None:
    """git rev-parse --short HEAD en el repo (solo dev). None si no hay git."""
    from runtime_paths import backend_root
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(backend_root()), capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception as exc:  # noqa: BLE001 (FileNotFoundError si no hay git, timeout, etc.)
        logger.debug("app_version: git rev-parse fallo: %s", exc)
    return None


def get_source_commit() -> str | None:
    """Identidad del build: manifest en deploy, git cacheado en dev. Cache de modulo."""
    global _CACHED_SOURCE_COMMIT, _SOURCE_COMMIT_RESOLVED
    if _SOURCE_COMMIT_RESOLVED:
        return _CACHED_SOURCE_COMMIT
    manifest = _read_manifest()
    if manifest and manifest.get("source_commit"):
        _CACHED_SOURCE_COMMIT = str(manifest["source_commit"]).strip() or None
    else:
        _CACHED_SOURCE_COMMIT = _git_short_head()
    _SOURCE_COMMIT_RESOLVED = True
    return _CACHED_SOURCE_COMMIT


def get_built_at() -> str | None:
    """built_at: manifest['generated_at'] en deploy; fecha del commit en dev. Cache de modulo."""
    global _CACHED_BUILT_AT, _BUILT_AT_RESOLVED
    if _BUILT_AT_RESOLVED:
        return _CACHED_BUILT_AT
    manifest = _read_manifest()
    if manifest and manifest.get("generated_at"):
        _CACHED_BUILT_AT = str(manifest["generated_at"]).strip() or None
    else:
        from runtime_paths import backend_root
        try:
            out = subprocess.run(
                ["git", "show", "-s", "--format=%cI", "HEAD"],
                cwd=str(backend_root()), capture_output=True, text=True, timeout=3,
            )
            _CACHED_BUILT_AT = out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None
        except Exception:  # noqa: BLE001
            _CACHED_BUILT_AT = None
    _BUILT_AT_RESOLVED = True
    return _CACHED_BUILT_AT


def get_repo_head() -> str | None:
    """HEAD vivo del repo (solo dev), con TTL corto. En deploy (frozen o con manifest) => None."""
    from runtime_paths import is_frozen
    if is_frozen() or _manifest_present():
        return None  # deploy: no hay drift posible (identidad inmutable); cero I/O por request (C9)
    global _REPO_HEAD_CACHE
    now = time.monotonic()
    if _REPO_HEAD_CACHE is not None and (now - _REPO_HEAD_CACHE[0]) < _REPO_HEAD_TTL_SECONDS:
        return _REPO_HEAD_CACHE[1]
    value = _git_short_head()
    _REPO_HEAD_CACHE = (now, value)
    return value


def get_build_drift() -> bool:
    """True solo si el HEAD vivo difiere del source_commit del proceso (solo dev)."""
    head = get_repo_head()
    src = get_source_commit()
    return bool(head and src and head != src)
