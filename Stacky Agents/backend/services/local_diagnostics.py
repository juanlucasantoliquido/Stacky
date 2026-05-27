from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from config import config
from project_manager import get_active_project, get_project_config
from runtime_paths import app_root, data_dir
from services import db_backup
from services.local_file_logging import logs_dir, recent_log_files

Status = str


def run_local_diagnostics() -> dict:
    started = time.monotonic()
    checks = [
        _check_backend(),
        _check_tracker(),
        _check_gh_auth(),
        _check_vscode_installation(),
        _check_vscode_bridge(),
        _check_database_storage(),
        _check_orphan_runs(),
    ]
    summary = {
        "ok": sum(1 for c in checks if c["status"] == "ok"),
        "warning": sum(1 for c in checks if c["status"] == "warning"),
        "error": sum(1 for c in checks if c["status"] == "error"),
    }
    return {
        "ok": summary["error"] == 0,
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "duration_ms": int((time.monotonic() - started) * 1000),
        "summary": summary,
        "checks": checks,
        "logs": {
            "directory": str(logs_dir()),
            "recent_files": [str(p) for p in recent_log_files()],
        },
        "backups": db_backup.list_backups(),
    }


def _check_backend() -> dict:
    return _result("backend", "Backend up", "ok", "El backend respondió esta misma request.")


def _check_tracker() -> dict:
    active = get_active_project()
    if not active:
        return _result("tracker", "Tracker", "warning", "No hay proyecto activo configurado.")

    cfg = get_project_config(active) or {}
    tracker = cfg.get("issue_tracker") or {}
    tracker_type = (tracker.get("type") or "azure_devops").strip().lower()
    label = {
        "azure_devops": "Azure DevOps",
        "jira": "Jira",
        "mantis": "Mantis",
    }.get(tracker_type, tracker_type or "Tracker")

    try:
        if tracker_type == "jira":
            _probe_jira(active, tracker)
        elif tracker_type == "mantis":
            _probe_mantis(active, tracker)
        else:
            _probe_ado(active)
        return _result("tracker", f"{label} alcanzable", "ok", f"Credenciales válidas para {active}.")
    except Exception as exc:
        return _result(
            "tracker",
            f"{label} alcanzable",
            "error",
            f"No se pudo validar {label}: {exc}",
            {"project": active, "tracker_type": tracker_type},
        )


def _probe_ado(project_name: str) -> None:
    from services.project_context import build_ado_client

    client = build_ado_client(project_name=project_name)
    org = urllib.parse.quote(client.org)
    project = urllib.parse.quote(client.project)
    url = f"https://dev.azure.com/{org}/_apis/projects/{project}?api-version=7.1"
    client._request("GET", url)


def _probe_jira(project_name: str, tracker: dict) -> None:
    from services.jira_client import JiraClient
    from services.project_context import resolve_project_context

    ctx = resolve_project_context(project_name)
    client = JiraClient(
        url=tracker.get("url", ""),
        project_key=tracker.get("project_key") or tracker.get("project") or "",
        api_version=str(tracker.get("api_version") or "3"),
        jql=tracker.get("jql") or "",
        auth_file=(ctx.auth_path if ctx else None) or tracker.get("auth_file") or "auth/jira_auth.json",
        verify_ssl=bool(tracker.get("verify_ssl", True)),
    )
    key = urllib.parse.quote(client.project_key)
    client._request("GET", f"{client._api_base}/project/{key}")


def _probe_mantis(project_name: str, tracker: dict) -> None:
    from services.mantis_client import get_mantis_client
    from services.project_context import resolve_project_context

    ctx = resolve_project_context(project_name)
    client = get_mantis_client(
        url=tracker.get("url", ""),
        project_id=tracker.get("project_id", ""),
        protocol=tracker.get("protocol", "rest"),
        auth_file=(ctx.auth_path if ctx else None) or tracker.get("auth_file") or "auth/mantis_auth.json",
        verify_ssl=bool(tracker.get("verify_ssl", True)),
    )
    client.list_projects()


def _check_gh_auth() -> dict:
    gh = _find_executable("gh", ["C:/Program Files/GitHub CLI/gh.exe"])
    if not gh:
        return _result("gh_auth", "GitHub CLI autenticado", "error", "No se encontró gh en PATH.")

    try:
        completed = subprocess.run(
            [gh, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        return _result("gh_auth", "GitHub CLI autenticado", "error", f"No se pudo ejecutar gh: {exc}")

    if completed.returncode == 0:
        return _result("gh_auth", "GitHub CLI autenticado", "ok", "gh auth status respondió correctamente.")
    detail = (completed.stderr or completed.stdout or "").strip()[:500]
    return _result("gh_auth", "GitHub CLI autenticado", "error", detail or "gh no tiene sesión activa.")


def _check_vscode_installation() -> dict:
    code = _find_executable(
        "code",
        [
            "C:/Program Files/Microsoft VS Code/bin/code.cmd",
            str(Path.home() / "AppData/Local/Programs/Microsoft VS Code/bin/code.cmd"),
        ],
    )
    vsix_files = _find_vsix_files()

    if code and vsix_files:
        return _result(
            "vscode_vsix",
            "VS Code y VSIX",
            "ok",
            f"VS Code encontrado; VSIX más reciente: {vsix_files[0].name}.",
            {"code": code, "vsix": [str(p) for p in vsix_files[:3]]},
        )
    missing = []
    if not code:
        missing.append("VS Code CLI")
    if not vsix_files:
        missing.append("stacky-agents-*.vsix")
    return _result("vscode_vsix", "VS Code y VSIX", "error", "Falta: " + ", ".join(missing))


def _find_vsix_files() -> list[Path]:
    candidates = [
        app_root() / "vscode_extension",
        Path(__file__).resolve().parents[1] / "vscode_extension",
        Path(__file__).resolve().parents[2] / "vscode_extension",
    ]
    files: list[Path] = []
    for base in candidates:
        if base.exists():
            files.extend(base.glob("stacky-agents-*.vsix"))
    return sorted(set(files), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)


def _check_vscode_bridge() -> dict:
    from services.vscode_instance_manager import get_instance_info, health_details

    # Resolver puerto: primero intentar por proyecto activo, luego fallback global.
    active = get_active_project()
    port: int = config.VSCODE_BRIDGE_PORT
    port_origin: str = "global"

    if active:
        info = get_instance_info(active)
        if info and isinstance(info.get("port"), int):
            port = info["port"]
            port_origin = f"proyecto '{active}'"

    payload = health_details(port, timeout=2.0)
    if payload is not None:
        return _result(
            "vscode_bridge",
            "Bridge VS Code",
            "ok",
            f"Bridge respondió en :{port} (origen: {port_origin}).",
            {**payload, "port": port, "port_origin": port_origin},
        )

    # No responde — mensaje accionable con puerto real y origen
    return _result(
        "vscode_bridge",
        "Bridge VS Code",
        "error",
        (
            f"El bridge no responde en :{port} (origen: {port_origin}). "
            "Acciones: 1) Abrí VS Code con el workspace del proyecto. "
            "2) Si ya está abierto: Ctrl+Shift+P → 'Developer: Reload Window'. "
            "3) Verificá que la extensión Stacky Agents esté instalada y habilitada."
        ),
        {"port": port, "port_origin": port_origin},
    )


def _check_database_storage() -> dict:
    db_path = db_backup.sqlite_db_path()
    if db_path is None:
        return _result("database", "DB escribible y con espacio", "warning", "La DB no es SQLite en archivo local.")

    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".stacky-write-test-", dir=parent, delete=True) as handle:
            handle.write(b"ok")
            handle.flush()
        usage = shutil.disk_usage(parent)
    except Exception as exc:
        return _result("database", "DB escribible y con espacio", "error", f"No se puede escribir en {parent}: {exc}")

    free_mb = int(usage.free / (1024 * 1024))
    status: Status = "ok" if free_mb >= 100 else "warning"
    message = f"{db_path} escribible. Espacio libre: {free_mb} MB."
    return _result(
        "database",
        "DB escribible y con espacio",
        status,
        message,
        {"database_path": str(db_path), "free_bytes": usage.free},
    )


def _check_orphan_runs() -> dict:
    """Detecta posibles runs huérfanos (Fase P5).

    Señal temprana para el operador: ejecuciones `running` más viejas que el
    umbral de alerta, especialmente del flujo open-chat. Si además el directorio
    que vigila el output_watcher no existe, el cierre automático no va a ocurrir
    (causa raíz C1) — se eleva a warning con mensaje accionable.
    """
    alert_minutes = int(os.getenv("STACKY_RUNNING_ALERT_MINUTES", "30"))
    try:
        from db import session_scope
        from models import AgentExecution

        cutoff = datetime.utcnow() - timedelta(minutes=alert_minutes)
        with session_scope() as session:
            stale = (
                session.query(AgentExecution)
                .filter(
                    AgentExecution.status == "running",
                    AgentExecution.started_at < cutoff,
                )
                .count()
            )
    except Exception as exc:  # noqa: BLE001
        return _result(
            "orphan_runs", "Runs huérfanos", "ok",
            f"No se pudo evaluar (no crítico): {exc}",
        )

    # ¿El watcher está mirando un dir que existe?
    watcher_dir: str | None = None
    watcher_dir_exists = True
    try:
        from services.output_watcher import get_output_watcher

        ow = get_output_watcher()
        if ow is not None:
            watcher_dir = str(ow.outputs_dir)
            watcher_dir_exists = ow.outputs_dir.exists()
    except Exception:
        pass

    if stale == 0 and watcher_dir_exists:
        return _result("orphan_runs", "Runs huérfanos", "ok", "Sin ejecuciones running estancadas.")

    detail = {
        "running_over_threshold": stale,
        "alert_minutes": alert_minutes,
        "watcher_dir": watcher_dir,
        "watcher_dir_exists": watcher_dir_exists,
    }
    if not watcher_dir_exists:
        return _result(
            "orphan_runs", "Runs huérfanos", "warning",
            (
                f"{stale} ejecución(es) running > {alert_minutes} min y el directorio "
                f"vigilado por el watcher no existe ({watcher_dir}). El cierre automático "
                "no ocurrirá: revisá el proyecto activo / STACKY_REPO_ROOT en Diagnóstico, "
                "o usá scan-now."
            ),
            detail,
        )
    return _result(
        "orphan_runs", "Runs huérfanos", "warning",
        (
            f"{stale} ejecución(es) llevan más de {alert_minutes} min en 'running'. "
            "Posible run huérfano — revisá Diagnóstico (GET /api/diag/metrics) o forzá "
            "el cierre con scan-now."
        ),
        detail,
    )


def _find_executable(name: str, fallbacks: list[str]) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in fallbacks:
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def _result(
    check_id: str,
    label: str,
    status: Status,
    message: str,
    detail: dict | list | str | None = None,
) -> dict:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "message": message,
        "detail": detail,
    }
