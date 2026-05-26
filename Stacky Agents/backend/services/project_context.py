from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, replace
from pathlib import Path

from project_manager import (
    PROJECTS_DIR,
    find_project_for_tracker,
    get_active_project,
    get_project_config,
)
from services.vscode_instance_manager import (
    get_instance_info,
    get_or_assign_port,
    health_details,
    is_alive,
    launch_vscode,
    wait_until_healthy,
    write_vscode_settings,
)

logger = logging.getLogger("stacky_agents.project_context")

_LEGACY_BRIDGE_WARNED = False


def _warn_legacy_bridge_once() -> None:
    global _LEGACY_BRIDGE_WARNED
    if not _LEGACY_BRIDGE_WARNED:
        logger.warning(
            "Bridge VS Code no expone 'workspace_root' en /health "
            "(extensión Stacky desactualizada). Asumiendo match por settings.json. "
            "Recompilá e instalá la extensión desde vscode_extension/ para validación estricta."
        )
        _LEGACY_BRIDGE_WARNED = True


class ProjectContextError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectContext:
    stacky_project_name: str
    tracker_type: str
    tracker_project: str
    organization: str | None = None
    workspace_root: str | None = None
    auth_path: str | None = None
    vscode_port: int | None = None

    def with_vscode_port(self, port: int | None) -> "ProjectContext":
        return replace(self, vscode_port=port)


def _normalize_project_name(name: str | None) -> str | None:
    raw = (name or "").strip()
    return raw.upper() if raw else None


def _normalize_workspace_root(path: str | None) -> str | None:
    raw = (path or "").strip()
    if not raw:
        return None
    return str(Path(raw).expanduser().resolve(strict=False)).replace("\\", "/").lower()


def _tracker_project_for(cfg: dict) -> str:
    tracker = cfg.get("issue_tracker") or {}
    tracker_type = (tracker.get("type") or "azure_devops").strip().lower()
    if tracker_type == "jira":
        return (tracker.get("project_key") or tracker.get("project") or cfg.get("name") or "").strip()
    if tracker_type == "mantis":
        project_id = str(tracker.get("project_id") or "").strip()
        return f"mantis-{project_id}" if project_id else str(cfg.get("name") or "").strip()
    return (tracker.get("project") or cfg.get("name") or "").strip()


def _organization_for(cfg: dict) -> str | None:
    tracker = cfg.get("issue_tracker") or {}
    org = (tracker.get("organization") or "").strip()
    return org or None


def _auth_path_for(cfg: dict) -> str | None:
    tracker = cfg.get("issue_tracker") or {}
    project_name = _normalize_project_name(cfg.get("name"))
    if not project_name:
        return None
    tracker_type = (tracker.get("type") or "azure_devops").strip().lower()
    if tracker_type == "jira":
        default_auth = "auth/jira_auth.json"
    elif tracker_type == "mantis":
        default_auth = "auth/mantis_auth.json"
    else:
        default_auth = "auth/ado_auth.json"
    rel = (tracker.get("auth_file") or default_auth).strip()
    if not rel:
        return None
    return str((PROJECTS_DIR / project_name / rel).resolve(strict=False))


def _config_for_project_name(project_name: str | None) -> dict | None:
    normalized = _normalize_project_name(project_name)
    if not normalized:
        return None
    cfg = get_project_config(normalized)
    if cfg:
        return cfg
    return get_project_config(project_name or "")


def resolve_project_context(
    project_name: str | None = None,
    *,
    tracker_project: str | None = None,
    ticket=None,
) -> ProjectContext | None:
    """Resuelve el contexto multi-proyecto para el request actual.

    Prioridad:
      1. project_name explícito (Stacky project o tracker_project)
      2. ticket.stacky_project_name / ticket.project
      3. tracker_project explícito
      4. proyecto activo
    """
    explicit_name = _normalize_project_name(project_name)
    ticket_stacky = _normalize_project_name(getattr(ticket, "stacky_project_name", None))
    ticket_tracker = (getattr(ticket, "project", None) or "").strip() or None
    explicit_tracker = (tracker_project or "").strip() or None

    cfg: dict | None = None
    stacky_name: str | None = None

    if explicit_name:
        cfg = _config_for_project_name(explicit_name)
        if cfg:
            stacky_name = _normalize_project_name(cfg.get("name")) or explicit_name
        else:
            found_name, found_cfg = find_project_for_tracker(explicit_name)
            if found_name and found_cfg:
                stacky_name = _normalize_project_name(found_name)
                cfg = found_cfg

    if cfg is None and ticket_stacky:
        cfg = _config_for_project_name(ticket_stacky)
        if cfg:
            stacky_name = _normalize_project_name(cfg.get("name")) or ticket_stacky

    for tracker_name in (ticket_tracker, explicit_tracker):
        if cfg is not None or not tracker_name:
            continue
        cfg = _config_for_project_name(tracker_name)
        if cfg:
            stacky_name = _normalize_project_name(cfg.get("name")) or _normalize_project_name(tracker_name)
            break
        found_name, found_cfg = find_project_for_tracker(tracker_name)
        if found_name and found_cfg:
            stacky_name = _normalize_project_name(found_name)
            cfg = found_cfg

    if cfg is None:
        active = get_active_project()
        if active:
            cfg = _config_for_project_name(active)
            if cfg:
                stacky_name = _normalize_project_name(cfg.get("name")) or _normalize_project_name(active)

    if not cfg or not stacky_name:
        return None

    tracker_type = ((cfg.get("issue_tracker") or {}).get("type") or "azure_devops").strip().lower()
    tracker_project_name = _tracker_project_for(cfg)
    workspace_root = (cfg.get("workspace_root") or "").strip() or None
    auth_path = _auth_path_for(cfg)
    vscode_port = None
    instance_info = get_instance_info(stacky_name)
    if instance_info and isinstance(instance_info.get("port"), int):
        vscode_port = int(instance_info["port"])

    return ProjectContext(
        stacky_project_name=stacky_name,
        tracker_type=tracker_type,
        tracker_project=tracker_project_name,
        organization=_organization_for(cfg),
        workspace_root=workspace_root,
        auth_path=auth_path,
        vscode_port=vscode_port,
    )


def require_project_context(
    project_name: str | None = None,
    *,
    tracker_project: str | None = None,
    ticket=None,
) -> ProjectContext:
    ctx = resolve_project_context(project_name, tracker_project=tracker_project, ticket=ticket)
    if ctx is None:
        detail = project_name or tracker_project or getattr(ticket, "project", None) or "<sin proyecto>"
        raise ProjectContextError(f"No se pudo resolver el contexto del proyecto: {detail}")
    return ctx


def build_ado_client(
    project_name: str | None = None,
    *,
    tracker_project: str | None = None,
    ticket=None,
):
    from services.ado_client import AdoClient, AdoConfigError

    ctx = require_project_context(project_name, tracker_project=tracker_project, ticket=ticket)
    if ctx.tracker_type != "azure_devops":
        raise AdoConfigError(
            f"El proyecto '{ctx.stacky_project_name}' no usa Azure DevOps (tracker_type={ctx.tracker_type})."
        )
    client = AdoClient(
        org=ctx.organization,
        project=ctx.tracker_project,
        auth_path=ctx.auth_path,
    )
    client.stacky_project_name = ctx.stacky_project_name
    client.tracker_type = ctx.tracker_type
    client.workspace_root = ctx.workspace_root
    client.auth_path = ctx.auth_path
    return client


def ensure_project_vscode(project_name: str, timeout_sec: float = 45.0) -> ProjectContext:
    ctx = require_project_context(project_name)
    if not ctx.workspace_root:
        raise ProjectContextError(
            f"El proyecto '{ctx.stacky_project_name}' no tiene workspace_root configurado."
        )

    port = get_or_assign_port(ctx.stacky_project_name, ctx.workspace_root)
    ctx = ctx.with_vscode_port(port)

    try:
        write_vscode_settings(ctx.workspace_root, port)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "No se pudo escribir .vscode/settings.json en %s: %s",
            ctx.workspace_root,
            exc,
        )

    current_health = health_details(port)
    if current_health and _workspace_matches(current_health, ctx.workspace_root):
        return ctx

    was_running = is_alive(port)
    launch_vscode(ctx.workspace_root)
    health = wait_until_healthy(
        port,
        workspace_root=ctx.workspace_root,
        timeout_sec=timeout_sec,
    )
    if not health:
        state = "abierta" if was_running else "lanzada"
        raise ProjectContextError(
            f"VS Code del proyecto '{ctx.stacky_project_name}' fue {state}, "
            f"pero el bridge {port} no respondió con el workspace correcto."
        )

    logger.info(
        "VS Code listo para %s (workspace_root=%s, bridge_port=%s)",
        ctx.stacky_project_name,
        ctx.workspace_root,
        port,
    )
    return ctx


def _workspace_matches(health_payload: dict, workspace_root: str | None) -> bool:
    expected = _normalize_workspace_root(workspace_root)
    if not expected:
        return True
    # Extensión vieja: no expone workspace_root en /health → asumir match.
    # El binding workspace↔puerto está garantizado por .vscode/settings.json
    # (stackyAgents.bridgePort), así que el bridge responde solo desde ese workspace.
    if "workspace_root" not in health_payload:
        _warn_legacy_bridge_once()
        return True
    actual = _normalize_workspace_root(health_payload.get("workspace_root"))
    return actual == expected


__all__ = [
    "ProjectContext",
    "ProjectContextError",
    "build_ado_client",
    "ensure_project_vscode",
    "require_project_context",
    "resolve_project_context",
]
