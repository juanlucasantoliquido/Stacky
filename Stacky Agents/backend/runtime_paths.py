from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def backend_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def app_root() -> Path:
    configured = os.getenv("STACKY_APP_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    if is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        return exe_dir.parent if exe_dir.name.lower() == "backend" else exe_dir

    return backend_root()


def data_dir() -> Path:
    configured = os.getenv("STACKY_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    if is_frozen():
        return app_root() / "data"
    return backend_root() / "data"


def projects_dir() -> Path:
    configured = os.getenv("STACKY_PROJECTS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    if is_frozen():
        return app_root() / "projects"
    return backend_root() / "projects"


def _active_workspace_root() -> Path | None:
    """workspace_root del proyecto activo, leído directo de projects/<active>/config.json.

    Self-contained (sólo usa projects_dir/data_dir) para no depender de
    project_manager y evitar el ciclo project_manager → runtime_paths.
    """
    try:
        pdir = projects_dir()
        active_name: str | None = None
        active_file = data_dir() / "active_project.json"
        if active_file.exists():
            data = json.loads(active_file.read_text(encoding="utf-8"))
            active_name = (data.get("active") or "").strip() or None
        if not active_name and pdir.exists():
            # Sin marcador explícito: primer proyecto con config.json.
            for d in sorted(pdir.iterdir()):
                if (d / "config.json").exists():
                    active_name = d.name
                    break
        if not active_name:
            return None
        cfg_file = pdir / active_name / "config.json"
        if not cfg_file.exists():
            return None
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        ws = (cfg.get("workspace_root") or "").strip()
        if ws:
            return Path(ws).expanduser().resolve()
    except Exception:
        return None
    return None


def repo_root() -> Path:
    """Root del repo donde el agente escribe `Agentes/outputs`.

    Prioridad:
      1. `STACKY_REPO_ROOT` — override explícito (tests y deploys).
      2. Congelado (deploy portable): `workspace_root` del proyecto activo. El
         exe vive fuera del repo del cliente, así que contar `parents` desde
         el módulo empaquetado no aplica.
      3. Layout de fuentes: `backend/runtime_paths.py` → parents[4] = `<repo>`
         (`<repo>/Tools/Stacky/Stacky Agents/backend/runtime_paths.py`).
    """
    env = os.getenv("STACKY_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if is_frozen():
        ws = _active_workspace_root()
        if ws is not None:
            return ws
    return Path(__file__).resolve().parents[4]


def frontend_dist_dir() -> Path | None:
    configured = os.getenv("STACKY_FRONTEND_DIST", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            app_root() / "frontend" / "dist",
            backend_root().parent / "frontend" / "dist",
            Path.cwd() / "frontend" / "dist",
        ]
    )

    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate.resolve()
    return None


def runtime_config() -> dict[str, Any]:
    configured = os.getenv("STACKY_RUNTIME_CONFIG", "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(data_dir() / "runtime_config.json")

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}
