"""Plan 265 F4 — Panel de Repositorio de la consola: SOLO LECTURA.

Toda la logica de subproceso copia el patron ya usado dos veces en el repo
(services/git_context.py:60 `_git` y services/plans_board.py:644,665-681
`_GIT_TIMEOUT_SEC` + `subprocess.run` con lista de argumentos, `shell=False`,
timeout y excepciones capturadas). Este modulo NO importa de plans_board.py
(el Plan 263 lo reescribe; ver docs del Plan 265, seccion 4.bis) ni declara
ningun subcomando de escritura de git: solo lee.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import project_manager
from services.console_secret_mask import mask_secrets

_GIT_TIMEOUT_SEC = 5  # mismo criterio que services/plans_board.py:644
_MAX_DIFF_BYTES = 200 * 1024  # cota dura del diff que viaja al navegador


def _known_workspace_roots() -> set[str]:
    roots: set[str] = set()
    for cfg in project_manager.get_all_projects():
        workspace_root = (cfg or {}).get("workspace_root")
        if not workspace_root:
            continue
        try:
            roots.add(str(Path(workspace_root).resolve()).replace("\\", "/"))
        except Exception:
            continue
    return roots


def resolve_known_workspace(workspace: str) -> Path | None:
    """None si `workspace` no esta registrado por project_manager. Comparacion
    por rutas YA RESUELTAS, nunca por comparacion de strings crudos."""
    if not workspace:
        return None
    try:
        candidate = Path(workspace).resolve()
    except Exception:
        return None
    if str(candidate).replace("\\", "/") not in _known_workspace_roots():
        return None
    return candidate


def resolve_safe_path(workspace: Path, path: str) -> Path | None:
    """None si `path` es absoluto, contiene '..', o resuelve fuera de `workspace`."""
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        return None
    if ".." in p.parts:
        return None
    try:
        resolved = (workspace / p).resolve()
        resolved.relative_to(workspace.resolve())
    except (ValueError, OSError):
        return None
    return resolved


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess | None:
    """Ejecuta git como LISTA de argumentos, `shell=False` implicito, con
    timeout. None ante cualquier problema — nunca lanza."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SEC,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def repo_status(workspace: Path) -> dict:
    """git status --porcelain=v1 sobre el workspace de la corrida.

    Devuelve {"ok": bool, "available": bool, "files": [{"path","status"}], "reason": str|None}.
    `available: False` + `reason` si no hay repositorio, si git no esta
    instalado, o si expira el tiempo. NUNCA lanza. NUNCA escribe.
    """
    if (workspace / ".git" / "index.lock").exists():
        return {
            "ok": True, "available": False, "files": [],
            "reason": "hay una sesion concurrente: el indice de git esta bloqueado",
        }
    if not (workspace / ".git").exists():
        return {"ok": True, "available": False, "files": [], "reason": "este workspace no tiene repositorio"}
    result = _run_git(["status", "--porcelain=v1"], workspace)
    if result is None:
        return {
            "ok": True, "available": False, "files": [],
            "reason": "git no esta disponible o se agoto el tiempo de espera",
        }
    if result.returncode != 0:
        return {"ok": True, "available": False, "files": [], "reason": "git status devolvio un error"}
    files = []
    for line in (result.stdout or "").splitlines():
        if not line:
            continue
        status_code = line[:2].strip() or "?"
        path = line[3:].strip()
        if path:
            files.append({"path": path, "status": status_code})
    return {"ok": True, "available": True, "files": files, "reason": None}


def repo_diff(workspace: Path, path: Path) -> dict:
    """git diff -- <archivo> (unified). Devuelve
    {"ok","available","diff","truncated","masked","reason"}.

    Cota DURA de 200 KB; mas alla se trunca y `truncated: True`. El texto pasa
    por el enmascarado de secretos (Plan 265 F4.5) ANTES de volver — ver
    services/console_secret_mask.py, cableado a partir de esa fase. NUNCA
    lanza. NUNCA escribe.
    """
    if (workspace / ".git" / "index.lock").exists():
        return {
            "ok": True, "available": False, "diff": "", "truncated": False, "masked": 0,
            "reason": "hay una sesion concurrente: el indice de git esta bloqueado",
        }
    if not (workspace / ".git").exists():
        return {
            "ok": True, "available": False, "diff": "", "truncated": False, "masked": 0,
            "reason": "este workspace no tiene repositorio",
        }
    try:
        rel = path.resolve().relative_to(workspace.resolve())
    except ValueError:
        rel = path
    result = _run_git(["diff", "--", str(rel).replace("\\", "/")], workspace)
    if result is None:
        return {
            "ok": True, "available": False, "diff": "", "truncated": False, "masked": 0,
            "reason": "git no esta disponible o se agoto el tiempo de espera",
        }
    if result.returncode != 0:
        return {
            "ok": True, "available": False, "diff": "", "truncated": False, "masked": 0,
            "reason": "git diff devolvio un error",
        }
    raw = result.stdout or ""
    if "Binary files" in raw:
        return {
            "ok": True, "available": True, "diff": "", "truncated": False, "masked": 0,
            "reason": "archivo binario: el contenido no se muestra como texto",
        }
    # Orden NO negociable (Plan 265 F4.5): enmascarar ANTES de truncar. Si se
    # enmascarara despues del corte, un secreto que cayo justo en el limite de
    # los 200 KB viajaria intacto.
    masked_text, masked_count = mask_secrets(raw)
    truncated = False
    encoded = masked_text.encode("utf-8", errors="replace")
    if len(encoded) > _MAX_DIFF_BYTES:
        truncated = True
        masked_text = encoded[:_MAX_DIFF_BYTES].decode("utf-8", errors="ignore")
    return {
        "ok": True, "available": True, "diff": masked_text,
        "truncated": truncated, "masked": masked_count, "reason": None,
    }
