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

# Tracker por defecto cuando el proyecto no declara `issue_tracker.type`.
# Plan 218 F1/F4: estaba repetido en 5 sitios de este archivo; centralizarlo baja el
# censo de acoplamiento (K4) sin cambiar una sola decisión de comportamiento.
_DEFAULT_TRACKER_TYPE = "azure_devops"

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


def tracker_is_azure_devops(project_name: str | None) -> bool:
    """¿El tracker declarado del proyecto es Azure DevOps? Resolvedor canónico.

    Fuente de verdad: `issue_tracker.type` del config del proyecto — lo que el
    operador setea por UI. Deliberadamente NO mira `ticket.tracker_type`: la
    columna tiene default `azure_devops` y las filas sintéticas (Brief Pool
    Ticket, `api/agents.py:777-785`) se crean sin ese campo, así que MIENTEN
    para cualquier proyecto no-ADO.

    Fail-closed: sin config resoluble devuelve True (asume ADO), de modo que
    todo gate construido sobre este helper conserve su comportamiento previo.

    `get_project_config` se importa dentro de la función a propósito: resuelto
    por referencia en cada llamada, sigue siendo interceptable parcheando
    `project_manager.get_project_config` (un alias capturado en el import de
    módulo haría que ese parche no tuviera efecto).
    """
    raw = (project_name or "").strip()
    if not raw:
        return True
    try:
        from project_manager import get_project_config as _get_cfg
        cfg = _get_cfg(raw) or {}
        tracker = cfg.get("issue_tracker") or {}
        declared = (tracker.get("type") or "").strip().lower()
        if not declared:
            return True
        return declared == _DEFAULT_TRACKER_TYPE
    except Exception:  # noqa: BLE001
        return True


def ruteo_estricto_por_tracker() -> bool:
    """Plan 281 — ¿está encendido el ruteo estricto por tipo de tracker?

    Kill-switch de rollback de los guards del Plan 281 F7: apagada la flag, los
    ocho sitios vuelven a construir el cliente de Azure DevOps como hoy (y a
    degradar por su `except`), en vez de cortar antes con el valor neutro.

    Vive acá, al lado del resolvedor canónico, para que la flag se lea en UN solo
    lugar: ocho copias del `getattr` son ocho oportunidades de equivocarse con el
    estilo de lectura. Se lee del OBJETO config (la instancia) y NUNCA con
    `os.getenv`: `tests/test_flags_env_read_meta.py` falla si una flag registrada
    se lee del entorno fuera de su allowlist congelada.

    Fail-open a True: si `config` no se puede importar, el comportamiento nuevo
    (que es el correcto) es el que queda.
    """
    try:
        from config import config as _cfg

        return bool(getattr(_cfg, "STACKY_TRACKER_ROUTING_STRICT_ENABLED", True))
    except Exception:  # noqa: BLE001
        return True


# Plan 286 F1 (C5) — memo {proyecto: (st_mtime_ns, st_size, tipo|None)}.
# Modulo-level a proposito: el ciclo de vida es el del proceso, igual que el del
# resto del modulo. `_reset_memo_tracker_declarado()` existe SOLO para los tests
# (un memo que los tests no pueden vaciar produce falsos verdes por orden).
_TRACKER_DECLARADO_MEMO: dict[str, tuple[int, int, str | None]] = {}


def _reset_memo_tracker_declarado() -> None:
    """Plan 286 F1 — vacia el memo. Uso: tests. NUNCA en camino de produccion."""
    _TRACKER_DECLARADO_MEMO.clear()


def tracker_declarado_del_proyecto(project_name: str | None) -> str | None:
    """Plan 286 — Tipo de tracker DECLARADO por el config del proyecto, o None.

    Hermano en minúscula de `tracker_is_azure_devops`: mismo origen de verdad
    (`issue_tracker.type`, lo que el operador setea por UI), mismo idioma de
    import local para seguir siendo interceptable con monkeypatch, misma
    defensa a prueba de todo. La diferencia es el retorno: acá hace falta el
    NOMBRE del tracker, no un booleano, porque el llamador tiene que rutear a
    GitLab, no solo descartar ADO.

    Devuelve None (no "azure_devops") cuando no se puede resolver: quien decide
    qué hacer con la ausencia es `tracker_efectivo_de_ticket`, en un solo lugar.
    """
    raw = (project_name or "").strip()
    if not raw:
        return None
    try:
        import os
        from project_manager import PROJECTS_DIR, get_project_config as _get_cfg

        # Plan 286 F1 (C5) — memo revalidado por mtime. `get_project_config`
        # relee y reparsea el JSON entero en cada llamada (medido: 858-1074 us,
        # project_manager.py:55-62) y este helper corre POR TICKET dentro de un
        # loop (api/tickets.py:1499). Un `os.stat` cuesta 132 us y NO puede
        # quedar stale: el operador cambia el tracker por UI, y cualquier
        # escritura del archivo mueve st_mtime_ns/st_size. NO cambiar por TTL ni
        # por lru_cache: eso rutearia al tracker viejo, que es el defecto que
        # este plan mata.
        try:
            st = os.stat(PROJECTS_DIR / raw / "config.json")
            firma = (st.st_mtime_ns, st.st_size)
        except OSError:
            firma = None  # sin archivo (o sin permiso) -> camino sin memo

        if firma is not None:
            cacheado = _TRACKER_DECLARADO_MEMO.get(raw)
            if cacheado is not None and cacheado[:2] == firma:
                return cacheado[2]

        cfg = _get_cfg(raw) or {}
        tracker = cfg.get("issue_tracker") or {}
        declarado = (tracker.get("type") or "").strip().lower() or None

        if firma is not None:
            _TRACKER_DECLARADO_MEMO[raw] = (firma[0], firma[1], declarado)
        return declarado
    except Exception:  # noqa: BLE001
        return None


def tracker_efectivo_de_ticket(ticket) -> str:
    """Plan 286 — A qué tracker le corresponde ESCRIBIR este ticket.

    PRECEDENCIA (este orden y no otro):

      1. La columna, SOLO si es EXPLÍCITA. Explícita = valor no vacío Y
         DISTINTO de `_DEFAULT_TRACKER_TYPE`. Motivo, y es el corazón del plan:
         `models.py:49` declara `default="azure_devops"`, así que ese valor en
         la columna es indistinguible de "nadie la seteó". Un valor como
         "gitlab", "jira", "mantis" o "demo" solo pudo escribirlo un sync a
         propósito: ese SÍ manda, y por eso gana incluso sobre el config (un
         ticket importado de Jira dentro de un proyecto ADO sigue siendo de
         Jira).
      2. El config del proyecto (`issue_tracker.type`). Es la fuente que el
         operador controla por UI y la que ya usan los 17 consumidores de
         `tracker_is_azure_devops`.
      3. `_DEFAULT_TRACKER_TYPE`. Fail-closed a Azure DevOps, IGUAL que hoy:
         un ticket sin `stacky_project_name` o de un proyecto sin config
         resoluble se comporta exactamente como antes de este plan. NO es una
         regresión y NO se "arregla" acá.

    Kill-switch: apagado `ruteo_estricto_por_tracker()` (Plan 281 F7), devuelve
    la columna cruda con el default de siempre — camino byte-idéntico al previo
    a este plan para los cuatro consumidores. No se registra flag nueva.

    NUNCA levanta y NUNCA devuelve cadena vacía.
    """
    bruto = getattr(ticket, "tracker_type", None)
    columna = bruto.strip().lower() if isinstance(bruto, str) else ""

    if not ruteo_estricto_por_tracker():
        return columna or _DEFAULT_TRACKER_TYPE

    if columna and columna != _DEFAULT_TRACKER_TYPE:
        return columna

    declarado = tracker_declarado_del_proyecto(
        getattr(ticket, "stacky_project_name", None)
    )
    if declarado:
        return declarado

    return _DEFAULT_TRACKER_TYPE


class ProjectContextError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectContext:
    stacky_project_name: str
    tracker_type: str
    tracker_project: str
    organization: str | None = None
    base_url: str | None = None          # URL de instancia (GitLab self-managed, Mantis, Jira)
    tracker_group: str | None = None     # grupo/namespace (GitLab epics)
    workspace_root: str | None = None
    auth_path: str | None = None
    vscode_port: int | None = None

    def with_vscode_port(self, port: int | None) -> "ProjectContext":
        return replace(self, vscode_port=port)


@dataclass(frozen=True)
class TrackerTarget:
    """Destino resuelto de escritura/lectura. CONGELADO por el Plan 218 (§3.1)."""

    tracker_type: str
    project_path: str          # ADO: nombre de proyecto | GitLab: 'grupo/proyecto'
    base_url: str | None
    organization: str | None
    group: str | None
    auth_path: str | None
    # Ampliación ADITIVA (default None): sin esto el bundle llegaba solo a la sonda
    # de diagnóstico y el listador de tickets moría con SSLError contra un GitLab
    # cuya CA no está en el almacén de la máquina.
    ca_bundle: str | None = None


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
    tracker_type = (tracker.get("type") or _DEFAULT_TRACKER_TYPE).strip().lower()
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


def _base_url_for(cfg: dict) -> str | None:
    """URL de instancia declarada por el proyecto (Plan 218 F4). None = usar la global."""
    tracker = cfg.get("issue_tracker") or {}
    return (tracker.get("base_url") or "").strip() or None


def _tracker_group_for(cfg: dict) -> str | None:
    """Grupo/namespace del tracker (GitLab epics). Plan 218 F4."""
    tracker = cfg.get("issue_tracker") or {}
    return (tracker.get("group") or "").strip() or None


def _auth_path_for(cfg: dict) -> str | None:
    tracker = cfg.get("issue_tracker") or {}
    project_name = _normalize_project_name(cfg.get("name"))
    if not project_name:
        return None
    tracker_type = (tracker.get("type") or _DEFAULT_TRACKER_TYPE).strip().lower()
    if tracker_type == "jira":
        default_auth = "auth/jira_auth.json"
    elif tracker_type == "mantis":
        default_auth = "auth/mantis_auth.json"
    elif tracker_type == "gitlab":
        # Plan 218 F4 (B1): sin esta rama, todo proyecto GitLab caía en el `else` y
        # apuntaba a las credenciales de Azure DevOps.
        default_auth = "auth/gitlab_auth.json"
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

    tracker_type = ((cfg.get("issue_tracker") or {}).get("type") or _DEFAULT_TRACKER_TYPE).strip().lower()
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
        base_url=_base_url_for(cfg),
        tracker_group=_tracker_group_for(cfg),
        workspace_root=workspace_root,
        auth_path=auth_path,
        vscode_port=vscode_port,
    )


def build_tracker_target(project_name: str | None = None) -> TrackerTarget:
    """Resuelve el destino desde issue_tracker del config.json del proyecto.

    Plan 218 F4. Compatibilidad: si el proyecto NO declara base_url/project para
    gitlab, cae a config.config.GITLAB_URL / GITLAB_PROJECT (comportamiento actual),
    de modo que los proyectos existentes siguen funcionando sin declarar nada nuevo.
    """
    import config as _config  # noqa: PLC0415

    ctx = resolve_project_context(project_name=project_name)
    tracker_type = (getattr(ctx, "tracker_type", None) or _DEFAULT_TRACKER_TYPE).strip().lower()
    project_path = (getattr(ctx, "tracker_project", None) or "").strip()
    base_url = getattr(ctx, "base_url", None)
    group = getattr(ctx, "tracker_group", None)
    ca_bundle = None

    if tracker_type == "gitlab":
        # B1: `_tracker_project_for` cae al NOMBRE Stacky cuando el proyecto no declara
        # `issue_tracker.project` — y un nombre Stacky NUNCA es un path 'grupo/proyecto'
        # de GitLab. Acá se usa el valor DECLARADO (sin ese fallback) para poder caer
        # a la config global, que es el comportamiento compatible.
        cfg = _config_for_project_name(project_name) if project_name else None
        if cfg is None:
            activo = get_active_project()
            cfg = _config_for_project_name(activo) if activo else None
        declarado = ((cfg or {}).get("issue_tracker") or {}).get("project")
        project_path = (declarado or "").strip()
        # El bundle se declara POR PROYECTO. Si falta, `preparar_verificacion`
        # cae a STACKY_GITLAB_CA_BUNDLE / REQUESTS_CA_BUNDLE y, sin ninguno, a
        # la verificación estándar: acá NO se inventa un fallback.
        ca_bundle = (((cfg or {}).get("issue_tracker") or {}).get("ca_bundle") or "").strip() or None

        if not base_url:
            base_url = (getattr(_config.config, "GITLAB_URL", "") or "").strip() or None
        if not project_path:
            project_path = (getattr(_config.config, "GITLAB_PROJECT", "") or "").strip()
        if not group:
            group = (getattr(_config.config, "STACKY_GITLAB_GROUP", "") or "").strip() or None

    return TrackerTarget(
        tracker_type=tracker_type,
        project_path=project_path,
        base_url=base_url,
        organization=getattr(ctx, "organization", None),
        group=group,
        auth_path=getattr(ctx, "auth_path", None),
        ca_bundle=ca_bundle,
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
    if ctx.tracker_type != _DEFAULT_TRACKER_TYPE:
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
