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
