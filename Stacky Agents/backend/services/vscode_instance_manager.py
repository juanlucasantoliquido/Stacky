"""
Gestiona instancias únicas de VS Code por proyecto (Stacky Agents).

Cada proyecto recibe un puerto dedicado en el rango PORT_BASE..PORT_BASE+MAX_PROJECTS.
El estado se persiste en backend/projects/<name>/vscode_instance.json.

Flujo principal:
  1. get_or_assign_port(name, workspace_root)  →  devuelve el puerto asignado
  2. is_alive(port)                            →  comprueba si el bridge responde
  3. write_vscode_settings(root, port)         →  escribe <root>/.vscode/settings.json
  4. launch_vscode(workspace_root)             →  abre VS Code en modo detachado

Cuando VS Code arranca con ese workspace, la extensión Stacky lee
`stackyAgents.bridgePort` del workspace settings y crea el servidor HTTP
en el puerto asignado, lo que permite ejecuciones completamente paralelas e
independientes por proyecto.
"""
from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

PORT_BASE    = 5060   # primer puerto del rango
MAX_PROJECTS = 40     # soporta hasta 40 proyectos simultáneos (5060–5099)

PROJECTS_DIR = Path(__file__).resolve().parent.parent / "projects"


# ── Asignación de puertos ─────────────────────────────────────────────────────

def _used_ports() -> set[int]:
    """Devuelve los puertos ya asignados a cualquier proyecto."""
    used: set[int] = set()
    if not PROJECTS_DIR.is_dir():
        return used
    for f in PROJECTS_DIR.glob("*/vscode_instance.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            p = data.get("port")
            if isinstance(p, int):
                used.add(p)
        except Exception:
            pass
    return used


def get_or_assign_port(project_name: str, workspace_root: str) -> int:
    """
    Devuelve el puerto ya asignado al proyecto o asigna uno nuevo.
    El resultado se persiste en projects/<name>/vscode_instance.json.
    """
    instance_file = PROJECTS_DIR / project_name / "vscode_instance.json"

    # Intentar leer puerto existente
    if instance_file.exists():
        try:
            data = json.loads(instance_file.read_text(encoding="utf-8"))
            p = data.get("port")
            if isinstance(p, int) and PORT_BASE <= p < PORT_BASE + MAX_PROJECTS:
                # Actualizar workspace_root si cambió
                if data.get("workspace_root") != workspace_root:
                    data["workspace_root"] = workspace_root
                    instance_file.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                return p
        except Exception:
            pass

    # Asignar un puerto libre
    used = _used_ports()
    for offset in range(MAX_PROJECTS):
        candidate = PORT_BASE + offset
        if candidate not in used:
            info = {
                "port": candidate,
                "workspace_root": workspace_root,
                "assigned_at": datetime.now(timezone.utc).isoformat(),
            }
            instance_file.parent.mkdir(parents=True, exist_ok=True)
            instance_file.write_text(
                json.dumps(info, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Proyecto %s → puerto %d asignado", project_name, candidate)
            return candidate

    raise RuntimeError(
        f"No hay puertos disponibles en el rango {PORT_BASE}–{PORT_BASE + MAX_PROJECTS - 1}. "
        "Demasiados proyectos con instancias VS Code."
    )


def get_instance_info(project_name: str) -> dict | None:
    """Lee la info de instancia persistida o devuelve None."""
    f = PROJECTS_DIR / project_name / "vscode_instance.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Liveness check ────────────────────────────────────────────────────────────

def is_alive(port: int, timeout: float = 2.0) -> bool:
    """
    Devuelve True si el bridge HTTP de la extensión Stacky responde en ese puerto.
    """
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/health",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Workspace settings ────────────────────────────────────────────────────────

def write_vscode_settings(workspace_root: str | Path, port: int) -> None:
    """
    Escribe/actualiza <workspace_root>/.vscode/settings.json con
    `stackyAgents.bridgePort = port` de modo que la extensión Stacky
    en esa ventana de VS Code use el puerto exclusivo del proyecto.
    Preserva todos los settings existentes.
    """
    vscode_dir = Path(workspace_root) / ".vscode"
    settings_file = vscode_dir / "settings.json"
    vscode_dir.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if settings_file.exists():
        try:
            existing = json.loads(settings_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing["stackyAgents.bridgePort"] = port
    settings_file.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "Escribió .vscode/settings.json en %s → bridgePort=%d",
        workspace_root,
        port,
    )


# ── Lanzamiento de VS Code ────────────────────────────────────────────────────

def launch_vscode(workspace_root: str | Path) -> None:
    """
    Abre VS Code con la carpeta del proyecto de forma detachada.
    - Si VS Code ya tiene esa carpeta abierta, la traerá al frente (comportamiento nativo).
    - El proceso se lanza de forma independiente: el backend no espera su cierre.
    - En Windows usa DETACHED_PROCESS para que el proceso sobreviva al padre.
    """
    path_str = str(workspace_root)
    logger.info("Lanzando VS Code en: %s", path_str)

    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        # Windows
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    def _spawn(code_cmd: str) -> None:
        subprocess.Popen(
            [code_cmd, path_str],
            creationflags=flags,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Intentar 'code' en PATH primero
    try:
        _spawn("code")
        return
    except FileNotFoundError:
        pass

    # Rutas alternativas en Windows
    fallback_paths = [
        Path.home() / "AppData/Local/Programs/Microsoft VS Code/bin/code.cmd",
        Path("C:/Program Files/Microsoft VS Code/bin/code.cmd"),
        Path("C:/Program Files (x86)/Microsoft VS Code/bin/code.cmd"),
    ]
    for cp in fallback_paths:
        if cp.exists():
            _spawn(str(cp))
            return

    raise RuntimeError(
        "No se encontró el comando 'code'. "
        "Instala VS Code y ejecuta 'Shell Command: Install code command in PATH' "
        "(menú Help de VS Code)."
    )
