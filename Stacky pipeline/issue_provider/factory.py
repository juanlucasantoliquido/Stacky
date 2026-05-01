"""
issue_provider.factory — Selecciona el IssueProvider correcto según config.

Fuentes de configuración (en orden de precedencia):
  1. `issue_tracker` en config del proyecto (projects/<X>/config.json)
  2. `issue_tracker` en config global (Stacky/config.json)

Forma canónica del bloque `issue_tracker`:

    "issue_tracker": {
        "type": "azure_devops",
        "organization": "UbimiaPacifico",
        "project": "Strategist_Pacifico",
        "area_path": "Strategist_Pacifico\\AgendaWeb",   // opcional
        "wiql": "SELECT [System.Id] FROM WorkItems WHERE ...",  // opcional
        "state_mapping": { "New": "asignada", "Active": "aceptada", ... },
        "auto_resolve": false,
        "pat": "<raw o preencoded>",    // opcional (preferible auth file)
        "auth_file": "auth/ado_auth.json" // opcional
    }
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .azure_devops_provider import AzureDevOpsProvider
from .base import IssueProvider

logger = logging.getLogger("stacky.issue.factory")

_BASE_DIR = Path(__file__).resolve().parent.parent

_PROVIDERS: dict[str, type[IssueProvider]] = {
    "azure_devops": AzureDevOpsProvider,
    "ado":          AzureDevOpsProvider,    # alias corto
}


def _read_global_config() -> dict:
    cfg_path = _BASE_DIR / "config.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("config.json ilegible: %s", e)
        return {}


def _read_project_config(project_name: str) -> dict:
    if not project_name:
        return {}
    try:
        from project_manager import get_project_config
        return get_project_config(project_name) or {}
    except Exception as e:
        logger.debug("No se pudo cargar config de proyecto %s: %s", project_name, e)
        return {}


def load_tracker_config(project_name: str | None = None) -> dict:
    """
    Devuelve el bloque `issue_tracker` efectivo: merge global + proyecto.
    """
    global_cfg  = _read_global_config()
    project_cfg = _read_project_config(project_name) if project_name else {}

    # Project override > Global
    eff: dict = {}
    eff.update(global_cfg.get("issue_tracker") or {})
    eff.update(project_cfg.get("issue_tracker") or {})

    return eff


def get_provider(project_name: str | None = None,
                 override_config: dict | None = None) -> IssueProvider:
    """
    Retorna el IssueProvider activo para el proyecto dado.
    Lanza RuntimeError si no se puede resolver.
    """
    cfg = override_config or load_tracker_config(project_name)
    if not cfg:
        raise RuntimeError(
            "No hay configuración de issue_tracker. Agregue un bloque "
            "'issue_tracker' a config.json o al config del proyecto."
        )
    kind = (cfg.get("type") or "").strip().lower()
    impl = _PROVIDERS.get(kind)
    if not impl:
        raise RuntimeError(
            f"issue_tracker.type='{cfg.get('type')}' no soportado. "
            f"Tipos válidos: {sorted(_PROVIDERS.keys())}"
        )
    return impl(cfg)
