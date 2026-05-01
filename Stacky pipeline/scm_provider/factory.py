"""
scm_provider.factory — Selector de ScmProvider.

Prioridad:
  1. Config explícita: projects/<X>/config.json → `scm.type`
  2. Autodetección: si workspace contiene `.git/` → git
  3. Fallback: git
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .base import ScmProvider
from .git_provider import GitProvider

logger = logging.getLogger("stacky.scm.factory")

_BASE_DIR = Path(__file__).resolve().parent.parent

_PROVIDERS: dict[str, type[ScmProvider]] = {
    "git": GitProvider,
}


def load_scm_config(project_name: str | None = None) -> dict:
    """Devuelve el bloque `scm` efectivo del proyecto (o {} si no hay)."""
    if not project_name:
        return {}
    try:
        from project_manager import get_project_config
        pcfg = get_project_config(project_name) or {}
    except Exception:
        pcfg = {}
    return pcfg.get("scm") or {}


def _autodetect_scm(workspace: str) -> str:
    if not workspace:
        return ""
    p = Path(workspace)
    if (p / ".git").exists():
        return "git"
    # Buscar .git en ancestros (git permite workspaces anidados)
    for ancestor in p.parents:
        if (ancestor / ".git").exists():
            return "git"
    return ""


def get_scm(
    project_name: str | None = None,
    workspace: str | None = None,
    override_config: dict | None = None,
) -> ScmProvider:
    """
    Retorna el ScmProvider apropiado. Nunca levanta: si no puede resolver,
    devuelve GitProvider (default).
    """
    cfg = override_config or load_scm_config(project_name)
    kind = (cfg.get("type") or "").strip().lower()

    if not kind and workspace:
        kind = _autodetect_scm(workspace)

    if not kind:
        kind = "git"  # default

    impl = _PROVIDERS.get(kind, GitProvider)
    return impl(cfg)
