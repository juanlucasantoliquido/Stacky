"""
services/ado_identity.py — Vinculación usuario Stacky ↔ identidad Azure DevOps
(plan 2026-05-27, Requerimiento B).

Stacky Agents corre localmente (un operador por instancia), por lo que el
"usuario Stacky" se identifica por el usuario del SO. La identidad ADO se
resuelve a partir del PAT configurado en el proyecto (vía connectionData) y se
persiste en `data/ado_user_map.json` con un timestamp de verificación, evitando
golpear ADO en cada request.

Estructura del mapa:
  {
    "<stacky_user>::<PROJECT>": {
      "stacky_user": "juanluca",
      "project": "RSPACIFICO",
      "ado_unique_name": "jluca@ubimia.com",
      "ado_display_name": "Juan L. Santoliquido",
      "ado_id": "....",
      "verified_at": "2026-05-27T12:00:00Z"
    }
  }
"""

from __future__ import annotations

import getpass
import json
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

_MAP_FILENAME = "ado_user_map.json"


def _map_path() -> Path:
    return data_dir() / _MAP_FILENAME


def current_stacky_user() -> str:
    try:
        return getpass.getuser() or "operator"
    except Exception:
        return "operator"


def _key(stacky_user: str, project: str) -> str:
    return f"{stacky_user}::{(project or '').upper()}"


def _load_map() -> dict:
    path = _map_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_map(data: dict) -> None:
    path = _map_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cached_identity(project: str, stacky_user: str | None = None) -> dict | None:
    """Devuelve el mapeo persistido para (usuario, proyecto), o None."""
    su = stacky_user or current_stacky_user()
    return _load_map().get(_key(su, project))


def save_identity(project: str, identity: dict, stacky_user: str | None = None) -> dict:
    """Persiste el mapeo stackyUser→adoUser con timestamp de verificación."""
    su = stacky_user or current_stacky_user()
    entry = {
        "stacky_user": su,
        "project": (project or "").upper(),
        "ado_unique_name": (identity.get("unique_name") or "").strip(),
        "ado_display_name": identity.get("display_name") or "",
        "ado_id": identity.get("id") or "",
        "verified_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    data = _load_map()
    data[_key(su, project)] = entry
    _save_map(data)
    return entry


__all__ = [
    "current_stacky_user",
    "get_cached_identity",
    "save_identity",
]
