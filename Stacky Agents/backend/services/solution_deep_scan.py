"""Plan 215 F3 — escaneo profundo de .sln con presupuesto de tiempo (PURO).

Escalon 2 de la escalera de fallback cuando el walk acotado del Plan 201 no
encontro (todas) las soluciones. Solo busca NOMBRES *.sln (no parsea proyectos),
asi que es barato, y corta por presupuesto de tiempo para no colgar el request.
"""
from __future__ import annotations

import os
import time

_DEEP_MAX_DEPTH = 16
# Lista corta A PROPOSITO: una .sln nunca vive en bin/obj, pero venv/dist de
# repos mixtos si pueden esconder carpetas hondas.
_DEEP_IGNORE_DIRS = ("node_modules", ".git", "__pycache__", ".vs", "packages")
_DEEP_TIME_BUDGET_SEC = 45


def deep_scan_sln_paths(workspace_root: str, time_budget_sec: int = _DEEP_TIME_BUDGET_SEC) -> dict:
    """{"paths": [rutas absolutas ordenadas], "timed_out": bool}. No lanza nunca."""
    try:
        if not workspace_root or not os.path.isdir(workspace_root):
            return {"paths": [], "timed_out": False}
    except (OSError, ValueError):
        return {"paths": [], "timed_out": False}

    root = os.path.normpath(workspace_root)
    budget = max(0, int(time_budget_sec or 0))
    deadline = time.monotonic() + budget
    paths: list = []
    timed_out = False

    for dirpath, dirnames, filenames in os.walk(root):
        if time.monotonic() > deadline:
            timed_out = True
            break
        depth = dirpath[len(root):].count(os.sep)
        if depth >= _DEEP_MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in _DEEP_IGNORE_DIRS]
        for fname in filenames:
            if fname.lower().endswith(".sln"):
                paths.append(os.path.join(dirpath, fname))

    return {"paths": sorted(paths), "timed_out": timed_out}
