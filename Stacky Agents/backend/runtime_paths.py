from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("stacky.runtime_paths")

# Sentinel devuelto por repo_root() cuando NO se puede resolver en un deploy
# congelado sin proyecto activo. Es un path inexistente a propósito: los
# consumidores que arman `<repo_root>/Agentes/outputs` verán un directorio
# inexistente y harán no-op, en vez de escanear basura bajo `<repo>/Tools/Stacky`
# (el viejo fallback `parents[4]`, que en el .exe empaquetado dentro del repo
# apuntaba ahí y dejaba al output_watcher poleando un dir equivocado).
_UNRESOLVED_REPO_ROOT = Path(__file__).resolve().parent / "__stacky_repo_root_unresolved__"

# Throttle del WARNING: repo_root() se llama en cada scan del watcher (~3s); sin
# esto el log se inundaría mientras no haya proyecto activo. Se rearma cuando la
# resolución vuelve a funcionar, para que un nuevo período no-resuelto sí avise.
_warned_unresolved_repo_root = False


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
      3. Congelado **sin** proyecto activo: sentinel inexistente
         (`_UNRESOLVED_REPO_ROOT`) + WARNING. NO se cae a `parents[4]`: en un
         deploy embebido (`<repo>/Tools/Stacky/.../backend/_internal/`) ese path
         apunta a `<repo>/Tools/Stacky`, no a `<repo>`, y el watcher terminaba
         escaneando un directorio equivocado para siempre (causa raíz C1).
      4. Layout de fuentes (no congelado): `backend/runtime_paths.py` →
         parents[4] = `<repo>` (`<repo>/Tools/Stacky/Stacky Agents/backend/`).
    """
    global _warned_unresolved_repo_root
    env = os.getenv("STACKY_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if is_frozen():
        ws = _active_workspace_root()
        if ws is not None:
            _warned_unresolved_repo_root = False  # rearmar el warning
            return ws
        # Deploy congelado sin proyecto activo: no resoluble todavía. Devolver un
        # sentinel inexistente en lugar de parents[4] (ver punto 3 del docstring).
        if not _warned_unresolved_repo_root:
            logger.warning(
                "repo_root() no resoluble: deploy congelado sin proyecto activo. "
                "Devuelvo sentinel inexistente (%s); los watchers no escanearán "
                "hasta que se active un proyecto con workspace_root. Seteá "
                "STACKY_REPO_ROOT para forzar la resolución.",
                _UNRESOLVED_REPO_ROOT,
            )
            _warned_unresolved_repo_root = True
        return _UNRESOLVED_REPO_ROOT
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


def stacky_home() -> Path:
    """Carpeta canónica `Stacky` dentro del runtime activo.

    Prioridad:
      1. `STACKY_HOME` — override explícito (deploys que apuntan a otra ruta).
      2. `<app_root>/Stacky` — comportamiento por defecto. En un deploy frozen
         esto resuelve a `<execution_root>/Stacky`; en dev queda dentro del
         backend, lo cual es aceptable porque el dir está gitignorado.

    El directorio NO se crea acá: usá `ensure_stacky_home()` cuando necesités
    que exista. Mantener la función pura permite testear la resolución sin
    side-effects.
    """
    configured = os.getenv("STACKY_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (app_root() / "Stacky").resolve()


def stacky_agents_dir() -> Path:
    """Carpeta canónica `Stacky/agents` con los `.agent.md` bundleados.

    Prioridad:
      1. `STACKY_AGENTS_DIR` — override explícito.
      2. `<stacky_home>/agents` — default.

    Plan: plan-agentes-bundled-en-stacky-2026-05-29.md §2.2.
    """
    configured = os.getenv("STACKY_AGENTS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (stacky_home() / "agents").resolve()


def ensure_stacky_home() -> Path:
    """Crea `stacky_home()` si no existe y devuelve el path resuelto."""
    home = stacky_home()
    home.mkdir(parents=True, exist_ok=True)
    return home


def ensure_stacky_agents_dir() -> Path:
    """Crea `stacky_agents_dir()` si no existe y devuelve el path resuelto."""
    agents = stacky_agents_dir()
    agents.mkdir(parents=True, exist_ok=True)
    return agents


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
