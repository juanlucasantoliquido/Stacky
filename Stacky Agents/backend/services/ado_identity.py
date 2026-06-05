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
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

logger = logging.getLogger("stacky_agents.ado_identity")

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


# ── Matcheo tolerante de identidad ─────────────────────────────────────────────
# Fuente única de verdad para comparar el assignee de un ticket contra la
# identidad del operador. Antes esta semántica estaba duplicada (api/adoption.py
# `_user_matches`) y el board ni siquiera la usaba (comparaba con `===` crudo),
# lo que rompía el filtro "Mis tareas" (B1). B1 (filtro) y B3 (auto-asignación)
# consumen ahora exactamente la misma lógica.


def user_matches(candidate: str | None, target: str | None) -> bool:
    """¿`candidate` (ej. Ticket.assigned_to_ado) identifica al mismo usuario que `target`?

    Match tolerante:
      1. Igualdad exacta tras trim + lowercase (cubre casing/dominio idéntico).
      2. Si no, compara la parte local (antes de `@`) en minúsculas, lo que tolera
         que un lado sea email (`jluca@ubimia.com`) y el otro un uniqueName sin
         dominio o un displayName degenerado a su local-part.

    Devuelve False si cualquiera de los dos está vacío (sin identidad → no filtra).
    """
    if not candidate or not target:
        return False
    c = candidate.strip().lower()
    t = target.strip().lower()
    if not c or not t:
        return False
    if c == t:
        return True
    return c.split("@", 1)[0] == t.split("@", 1)[0]


def resolve_me_unique_name(project_name: str | None) -> str:
    """uniqueName ADO del operador (single-operator por instancia).

    Prefiere el mapeo persistido (rápido); si no existe, lo resuelve vía PAT
    (connectionData) y lo cachea. Si no se puede resolver, devuelve "" — los
    callers deben tratar el vacío como "identidad desconocida" y NO filtrar /
    NO asignar, evitando una lista vacía confusa o una asignación errónea.
    """
    cached = get_cached_identity(project_name or "")
    if cached and cached.get("ado_unique_name"):
        return cached["ado_unique_name"]
    try:
        from services.project_context import build_ado_client

        identity = build_ado_client(project_name=project_name).get_authenticated_user()
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo resolver identidad ADO para 'me': %s", exc)
        return ""
    if identity.get("unique_name"):
        save_identity(project_name or "", identity)
    return identity.get("unique_name") or ""


__all__ = [
    "current_stacky_user",
    "get_cached_identity",
    "save_identity",
    "user_matches",
    "resolve_me_unique_name",
]
