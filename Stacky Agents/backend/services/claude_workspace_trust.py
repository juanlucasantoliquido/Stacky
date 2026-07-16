"""Preflight de confianza de workspace para el binario `claude` (Plan 144 F2/F3).

El CLI de Claude Code ignora permisos y sale con code 1 si el workspace no está
en projects[<key>].hasTrustDialogAccepted:true dentro de ~/.claude.json.
Este módulo lee/normaliza/escribe ese estado. Específico de Claude CLI:
Codex/Copilot NO lo usan (ver Plan 144 §3)."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("stacky_agents.claude_workspace_trust")


@dataclass(frozen=True)
class WorkspaceTrust:
    trusted: bool          # projects[key].hasTrustDialogAccepted is True
    present: bool          # el key del proyecto existe en projects
    config_path: str       # ruta absoluta a ~/.claude.json
    project_key: str       # key normalizado que se buscó/escribiría
    error: str | None = None  # None si la lectura fue OK


def _claude_json_path(home: str | None = None) -> Path:
    base = Path(home) if home else Path(os.path.expanduser("~"))
    return base / ".claude.json"


def _normalize_project_key(workspace_root: str) -> str:
    """El CLI keyea projects con la ruta absoluta en barras '/'.
    Evidencia [V] del log: projects["C:/desarrollo/GIT/RS/RSPACIFICO"]."""
    return str(Path(workspace_root).resolve()).replace("\\", "/")


def read_workspace_trust(workspace_root: str, *, home: str | None = None) -> WorkspaceTrust:
    key = _normalize_project_key(workspace_root)
    path = _claude_json_path(home)
    if not path.exists():
        return WorkspaceTrust(trusted=False, present=False, config_path=str(path),
                              project_key=key, error="~/.claude.json no existe")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return WorkspaceTrust(trusted=False, present=False, config_path=str(path),
                              project_key=key, error=f"~/.claude.json ilegible: {exc}")
    projects = data.get("projects") or {}
    entry = projects.get(key)
    if entry is None:
        return WorkspaceTrust(trusted=False, present=False, config_path=str(path),
                              project_key=key, error=None)
    return WorkspaceTrust(trusted=bool(entry.get("hasTrustDialogAccepted")),
                          present=True, config_path=str(path), project_key=key, error=None)


def set_workspace_trusted(workspace_root: str, *, home: str | None = None) -> WorkspaceTrust:
    """Escribe projects[key].hasTrustDialogAccepted = True. Hace backup previo
    (~/.claude.json.stacky.bak) y crea el archivo/estructura si falta. SOLO se
    invoca cuando el operador activó el auto-set (Plan 144 F3, excepción dura d)."""
    key = _normalize_project_key(workspace_root)
    path = _claude_json_path(home)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — no pisar un JSON que no entendemos
            return WorkspaceTrust(trusted=False, present=False, config_path=str(path),
                                  project_key=key, error="no se sobreescribe un ~/.claude.json ilegible")
        try:
            (path.parent / ".claude.json.stacky.bak").write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:  # noqa: BLE001 — backup best-effort
            pass
    projects = data.setdefault("projects", {})
    entry = projects.setdefault(key, {})
    entry["hasTrustDialogAccepted"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.warning("trust auto-set aplicado a projects[%s].hasTrustDialogAccepted=true", key)
    return WorkspaceTrust(trusted=True, present=True, config_path=str(path),
                          project_key=key, error=None)
