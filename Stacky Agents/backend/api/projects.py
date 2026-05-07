"""
api/projects.py — Endpoints de gestión multi-proyecto para Stacky Agents.

GET    /api/projects              → lista todos los proyectos inicializados
GET    /api/active_project        → proyecto activo actual
POST   /api/active_project        → cambiar proyecto activo  { "name": "RSPACIFICO" }
POST   /api/init_project          → crear / inicializar un proyecto nuevo
PATCH  /api/projects/<name>       → actualizar configuración de un proyecto
DELETE /api/projects/<name>       → eliminar un proyecto

Body de POST /api/init_project (campos comunes):
  {
    "name":           "RSPACIFICO",
    "display_name":   "RS Pacífico",
    "workspace_root": "N:/GIT/RS/RSPacifico/trunk",
    "tracker_type":   "azure_devops" | "jira"
  }

Campos adicionales para Azure DevOps:
  { "organization": "UbimiaPacifico", "ado_project": "Strategist_Pacifico",
    "area_path": "Strategist_Pacifico\\AgendaWeb",
    "pat": "TOKEN_AQUI" }

Campos adicionales para Jira:
  { "jira_url": "https://empresa.atlassian.net", "jira_key": "B2IM",
    "api_version": "3", "jql": "...", "verify_ssl": true,
    "jira_user": "me@company.com", "jira_token": "ATATT..." }
"""

from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request

from project_manager import (
    PROJECTS_DIR,
    delete_project,
    get_active_project,
    get_agent_workflow_config,
    get_all_projects,
    get_project_config,
    get_project_pinned_agents,
    initialize_ado_project,
    initialize_jira_project,
    initialize_mantis_project,
    set_active_project,
    set_agent_workflow_config,
    set_project_pinned_agents,
    write_ado_auth,
    write_jira_auth,
    write_mantis_auth,
)

logger = logging.getLogger("stacky_agents.api.projects")

bp = Blueprint("projects", __name__, url_prefix="")


# ── Helpers internos ─────────────────────────────────────────────────────────

def _has_credentials(name: str, tracker_type: str) -> bool:
    """Indica si el proyecto tiene archivo de credenciales almacenado."""
    if tracker_type == "azure_devops":
        auth_filename = "ado_auth.json"
    elif tracker_type == "jira":
        auth_filename = "jira_auth.json"
    else:  # mantis
        auth_filename = "mantis_auth.json"
    return (PROJECTS_DIR / name / "auth" / auth_filename).exists()


def _project_to_dict(cfg: dict, active_name: str | None) -> dict:
    tracker = cfg.get("issue_tracker") or {}
    t_type  = tracker.get("type", "azure_devops")
    return {
        "name":              cfg["name"],
        "display_name":      cfg.get("display_name", cfg["name"]),
        "workspace_root":    cfg.get("workspace_root", ""),
        "tracker_type":      t_type,
        # ADO fields
        "organization":      tracker.get("organization", ""),
        "ado_project":       tracker.get("project", ""),
        # Jira fields
        "jira_url":          tracker.get("url", "") if t_type == "jira" else "",
        "jira_key":          tracker.get("project_key", ""),
        # Mantis fields
        "mantis_url":        tracker.get("url", "") if t_type == "mantis" else "",
        "mantis_project_id": tracker.get("project_id", ""),
        "mantis_project_name": tracker.get("project_name", ""),
        "mantis_protocol":   tracker.get("protocol", "rest") if t_type == "mantis" else "rest",
        "active":            cfg["name"] == active_name,
        "initialized":       True,
        "has_credentials":   _has_credentials(cfg["name"], t_type),
    }


# ── GET /api/projects ─────────────────────────────────────────────────────────

@bp.get("/projects")
def list_projects():
    """Lista todos los proyectos inicializados con su metadata."""
    projects    = get_all_projects()
    active_name = get_active_project()

    result = [_project_to_dict(p, active_name) for p in projects]
    return jsonify({"ok": True, "projects": result, "active": active_name})


# ── GET / POST /api/active_project ────────────────────────────────────────────

@bp.get("/active_project")
def get_active():
    name = get_active_project()
    cfg  = get_project_config(name) if name else None
    tracker = (cfg or {}).get("issue_tracker") or {}
    return jsonify({
        "ok":           True,
        "active":       name,
        "display_name": (cfg or {}).get("display_name", name or ""),
        "tracker_type": tracker.get("type", "azure_devops"),
    })


@bp.post("/active_project")
def set_active():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name requerido"}), 400
    cfg = get_project_config(name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{name}' no inicializado"}), 404
    set_active_project(name)
    return jsonify({
        "ok":      True,
        "active":  name,
        "project": _project_to_dict(cfg, name),
    })


# ── POST /api/init_project ────────────────────────────────────────────────────

@bp.post("/init_project")
def init_project():
    """
    Inicializa un proyecto ADO, Jira o Mantis.
    Si el proyecto ya existe, actualiza su config.json.
    """
    data           = request.get_json(force=True, silent=True) or {}
    name           = (data.get("name") or "").strip()
    display_name   = (data.get("display_name") or "").strip()
    workspace_root = (data.get("workspace_root") or "").strip()
    tracker_type   = (data.get("tracker_type") or "azure_devops").strip().lower()

    if not name:
        return jsonify({"ok": False, "error": "name requerido"}), 400
    if not workspace_root:
        return jsonify({"ok": False, "error": "workspace_root requerido"}), 400

    try:
        if tracker_type == "jira":
            jira_url    = (data.get("jira_url") or "").strip()
            jira_key    = (data.get("jira_key") or "").strip()
            api_version = str(data.get("api_version") or "3").strip()
            jql         = (data.get("jql") or "").strip()
            verify_ssl  = data.get("verify_ssl", True)
            jira_user   = (data.get("jira_user") or "").strip()
            jira_token  = (data.get("jira_token") or "").strip()

            if not jira_url:
                return jsonify({"ok": False, "error": "jira_url requerida"}), 400
            if not jira_key:
                return jsonify({"ok": False, "error": "jira_key requerida"}), 400

            cfg = initialize_jira_project(
                name=name,
                display_name=display_name or name,
                workspace_root=workspace_root,
                url=jira_url,
                project_key=jira_key,
                api_version=api_version,
                jql=jql,
                verify_ssl=bool(verify_ssl),
                auth_file="auth/jira_auth.json",
            )
            if jira_user and jira_token:
                write_jira_auth(name=name, url=jira_url, user=jira_user, token=jira_token)

        elif tracker_type == "mantis":
            mantis_url          = (data.get("mantis_url") or "").strip()
            mantis_project_id   = str(data.get("mantis_project_id") or "").strip()
            mantis_project_name = (data.get("mantis_project_name") or "").strip()
            mantis_protocol     = (data.get("mantis_protocol") or "rest").strip().lower()
            mantis_token        = (data.get("mantis_token") or "").strip()
            mantis_username     = (data.get("mantis_username") or "").strip()
            mantis_password     = (data.get("mantis_password") or "").strip()
            verify_ssl          = data.get("verify_ssl", True)

            if not mantis_url:
                return jsonify({"ok": False, "error": "mantis_url requerida"}), 400
            if not mantis_project_id:
                return jsonify({"ok": False, "error": "mantis_project_id requerido"}), 400

            cfg = initialize_mantis_project(
                name=name,
                display_name=display_name or name,
                workspace_root=workspace_root,
                url=mantis_url,
                project_id=mantis_project_id,
                project_name=mantis_project_name,
                protocol=mantis_protocol,
                verify_ssl=bool(verify_ssl),
                auth_file="auth/mantis_auth.json",
            )
            if mantis_protocol == "soap" and mantis_username:
                write_mantis_auth(
                    name=name, url=mantis_url, protocol="soap",
                    username=mantis_username, password=mantis_password,
                    project_id=mantis_project_id,
                )
            elif mantis_protocol != "soap" and mantis_token:
                write_mantis_auth(
                    name=name, url=mantis_url, protocol="rest",
                    token=mantis_token, project_id=mantis_project_id,
                )

        else:  # azure_devops
            organization = (data.get("organization") or "").strip()
            ado_project  = (data.get("ado_project") or "").strip()
            area_path    = (data.get("area_path") or "").strip()
            pat          = (data.get("pat") or "").strip()

            if not organization:
                return jsonify({"ok": False, "error": "organization requerida"}), 400
            if not ado_project:
                return jsonify({"ok": False, "error": "ado_project requerido"}), 400

            cfg = initialize_ado_project(
                name=name,
                display_name=display_name or name,
                workspace_root=workspace_root,
                organization=organization,
                ado_project=ado_project,
                area_path=area_path,
                auth_file="auth/ado_auth.json",
            )
            if pat:
                write_ado_auth(name=name, pat=pat)

        active_name = get_active_project()
        return jsonify({"ok": True, "project": _project_to_dict(cfg, active_name)})

    except Exception as e:
        logger.exception("Error al inicializar proyecto %s", name)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── GET / PATCH / DELETE /api/projects/{name} ─────────────────────────────────

@bp.get("/projects/<string:project_name>")
def get_project(project_name: str):
    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    active_name = get_active_project()
    return jsonify({"ok": True, "project": _project_to_dict(cfg, active_name)})


@bp.route("/projects/<string:project_name>", methods=["PATCH"])
def update_project(project_name: str):
    """
    Actualiza la configuración de un proyecto existente.
    Acepta los mismos campos que init_project. Solo actualiza los campos enviados.
    """
    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    data         = request.get_json(force=True, silent=True) or {}
    tracker_type = (data.get("tracker_type") or cfg.get("issue_tracker", {}).get("type", "azure_devops")).lower()

    try:
        if tracker_type == "jira":
            tracker   = cfg.get("issue_tracker") or {}
            jira_url  = (data.get("jira_url") or tracker.get("url", "")).strip()
            jira_key  = (data.get("jira_key") or tracker.get("project_key", "")).strip()
            new_cfg   = initialize_jira_project(
                name=project_name,
                display_name=(data.get("display_name") or cfg.get("display_name", project_name)).strip(),
                workspace_root=(data.get("workspace_root") or cfg.get("workspace_root", "")).strip(),
                url=jira_url,
                project_key=jira_key,
                api_version=str(data.get("api_version") or tracker.get("api_version", "3")),
                jql=(data.get("jql") or tracker.get("jql", "")),
                verify_ssl=data.get("verify_ssl", tracker.get("verify_ssl", True)),
                auth_file="auth/jira_auth.json",
            )
            jira_user  = (data.get("jira_user") or "").strip()
            jira_token = (data.get("jira_token") or "").strip()
            auth_url = jira_url or (cfg.get("issue_tracker") or {}).get("url", "")
            if jira_user and jira_token:
                write_jira_auth(name=project_name, url=auth_url, user=jira_user, token=jira_token)
            elif jira_user:
                auth_path = PROJECTS_DIR / project_name / "auth" / "jira_auth.json"
                existing_token = ""
                if auth_path.exists():
                    try:
                        existing_creds = json.loads(auth_path.read_text(encoding="utf-8"))
                        existing_token = existing_creds.get("token", "")
                    except Exception:
                        pass
                if existing_token:
                    write_jira_auth(name=project_name, url=auth_url, user=jira_user, token=existing_token)

        elif tracker_type == "mantis":
            tracker             = cfg.get("issue_tracker") or {}
            mantis_url          = (data.get("mantis_url") or tracker.get("url", "")).strip()
            mantis_project_id   = str(data.get("mantis_project_id") or tracker.get("project_id", "")).strip()
            mantis_project_name = (data.get("mantis_project_name") or tracker.get("project_name", "")).strip()
            mantis_protocol     = (data.get("mantis_protocol") or tracker.get("protocol", "rest")).strip().lower()
            mantis_token        = (data.get("mantis_token") or "").strip()
            mantis_username     = (data.get("mantis_username") or "").strip()
            mantis_password     = (data.get("mantis_password") or "").strip()
            new_cfg = initialize_mantis_project(
                name=project_name,
                display_name=(data.get("display_name") or cfg.get("display_name", project_name)).strip(),
                workspace_root=(data.get("workspace_root") or cfg.get("workspace_root", "")).strip(),
                url=mantis_url,
                project_id=mantis_project_id,
                project_name=mantis_project_name,
                protocol=mantis_protocol,
                verify_ssl=data.get("verify_ssl", tracker.get("verify_ssl", True)),
                auth_file="auth/mantis_auth.json",
            )
            auth_path = PROJECTS_DIR / project_name / "auth" / "mantis_auth.json"
            if mantis_protocol == "soap" and mantis_username:
                write_mantis_auth(
                    name=project_name, url=mantis_url, protocol="soap",
                    username=mantis_username, password=mantis_password,
                    project_id=mantis_project_id,
                )
            elif mantis_protocol != "soap" and mantis_token:
                write_mantis_auth(
                    name=project_name, url=mantis_url, protocol="rest",
                    token=mantis_token, project_id=mantis_project_id,
                )
            elif mantis_project_id and auth_path.exists():
                try:
                    existing_auth = json.loads(auth_path.read_text(encoding="utf-8"))
                    existing_auth["project_id"] = mantis_project_id
                    auth_path.write_text(
                        json.dumps(existing_auth, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                except Exception:
                    pass

        else:
            tracker      = cfg.get("issue_tracker") or {}
            organization = (data.get("organization") or tracker.get("organization", "")).strip()
            ado_project  = (data.get("ado_project") or tracker.get("project", "")).strip()
            new_cfg      = initialize_ado_project(
                name=project_name,
                display_name=(data.get("display_name") or cfg.get("display_name", project_name)).strip(),
                workspace_root=(data.get("workspace_root") or cfg.get("workspace_root", "")).strip(),
                organization=organization,
                ado_project=ado_project,
                area_path=(data.get("area_path") or tracker.get("area_path", "")),
                auth_file="auth/ado_auth.json",
            )
            pat = (data.get("pat") or "").strip()
            if pat:
                write_ado_auth(name=project_name, pat=pat)

        active_name = get_active_project()
        return jsonify({"ok": True, "project": _project_to_dict(new_cfg, active_name)})

    except Exception as e:
        logger.exception("Error al actualizar proyecto %s", project_name)
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/projects/<string:project_name>", methods=["DELETE"])
def remove_project(project_name: str):
    """Elimina un proyecto y todos sus archivos de configuración."""
    from project_manager import delete_project as _delete
    existed = _delete(project_name)
    if not existed:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    return jsonify({"ok": True, "deleted": project_name})


@bp.get("/projects/<string:project_name>/credentials")
def get_project_credentials(project_name: str):
    """
    Devuelve los metadatos de credenciales del proyecto (usuario/email visible,
    nunca el token/PAT). Útil para pre-popular el formulario de edición.
    """
    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": "not_found"}), 404

    tracker = cfg.get("issue_tracker") or {}
    t_type  = tracker.get("type", "azure_devops")

    result: dict = {"ok": True, "tracker_type": t_type, "has_credentials": False,
                    "jira_user": None, "ado_user": None,
                    "mantis_token_saved": False, "mantis_username_saved": False,
                    "mantis_protocol": "rest"}

    if t_type == "mantis":
        auth_filename = "mantis_auth.json"
    elif t_type == "jira":
        auth_filename = "jira_auth.json"
    else:
        auth_filename = "ado_auth.json"

    auth_file_rel = tracker.get("auth_file", f"auth/{auth_filename}")
    auth_path = PROJECTS_DIR / project_name / auth_file_rel

    if auth_path.exists():
        try:
            import json as _json
            auth_data = _json.loads(auth_path.read_text(encoding="utf-8"))
            result["has_credentials"] = True
            if t_type == "jira":
                result["jira_user"] = auth_data.get("user") or auth_data.get("email") or None
            elif t_type == "mantis":
                result["mantis_protocol"] = auth_data.get("protocol", "rest")
                if auth_data.get("protocol", "rest") == "soap":
                    result["mantis_username_saved"] = bool(auth_data.get("username"))
                else:
                    result["mantis_token_saved"] = bool(auth_data.get("token"))
                result["mantis_project_id"]  = auth_data.get("project_id") or tracker.get("project_id") or ""
            else:
                result["ado_user"] = "(PAT guardado)"
        except Exception:
            pass

    return jsonify(result)


# ── POST /api/mantis/projects — listar proyectos de una instancia Mantis ──────

@bp.post("/mantis/projects")
def list_mantis_projects():
    """
    Lista los proyectos accesibles en una instancia Mantis dada URL + credenciales.
    Soporta protocolo REST (token) y SOAP (usuario/contraseña).
    No requiere que el proyecto esté inicializado.

    Body REST:  { "url": "https://...", "protocol": "rest", "token": "XXX", "verify_ssl": true }
    Body SOAP:  { "url": "https://...", "protocol": "soap", "username": "admin", "password": "...", "verify_ssl": true }
    """
    data       = request.get_json(force=True, silent=True) or {}
    url        = (data.get("url")      or "").strip().rstrip("/")
    protocol   = (data.get("protocol") or "rest").strip().lower()
    token      = (data.get("token")    or "").strip()
    username   = (data.get("username") or "").strip()
    password   = (data.get("password") or "").strip()
    verify_ssl = data.get("verify_ssl", True)

    if not url:
        return jsonify({"ok": False, "error": "url requerida"}), 400
    if protocol == "soap" and not username:
        return jsonify({"ok": False, "error": "username requerido para SOAP"}), 400
    if protocol != "soap" and not token:
        return jsonify({"ok": False, "error": "token requerido para REST"}), 400

    try:
        from services.mantis_client import get_mantis_client
        client = get_mantis_client(
            url=url, protocol=protocol,
            token=token, username=username, password=password,
            verify_ssl=bool(verify_ssl),
        )
        projects = client.list_projects()
        return jsonify({"ok": True, "projects": projects})
    except Exception as exc:
        logger.warning("Error listando proyectos Mantis: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 502


# ── GET / PUT /api/projects/{name}/agents ─────────────────────────────────────

@bp.get("/projects/<string:project_name>/agents")
def get_project_agents(project_name: str):
    """Retorna los agentes fijados del proyecto."""
    if not get_project_config(project_name):
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    pinned = get_project_pinned_agents(project_name)
    return jsonify({"ok": True, "pinned_agents": pinned})


@bp.put("/projects/<string:project_name>/agents")
def put_project_agents(project_name: str):
    """Guarda los agentes fijados del proyecto. Body: { "pinned_agents": [...] }"""
    if not get_project_config(project_name):
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    data   = request.get_json(force=True, silent=True) or {}
    pinned = data.get("pinned_agents", [])
    if not isinstance(pinned, list):
        return jsonify({"ok": False, "error": "pinned_agents debe ser una lista"}), 400
    try:
        set_project_pinned_agents(project_name, pinned)
        return jsonify({"ok": True, "pinned_agents": pinned})
    except Exception as e:
        logger.exception("Error al guardar agentes del proyecto %s", project_name)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Agent workflow config ─────────────────────────────────────────────────────

@bp.get("/projects/<string:project_name>/tracker-states")
def get_tracker_states(project_name: str):
    """Devuelve los estados disponibles para el tracker del proyecto."""
    from db import session_scope
    from models import Ticket

    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    tracker = cfg.get("issue_tracker") or {}
    t_type  = tracker.get("type", "azure_devops")

    if t_type == "jira":
        tracker_project = tracker.get("project_key") or tracker.get("project") or project_name
    elif t_type == "mantis":
        pid = tracker.get("project_id", "")
        tracker_project = f"mantis-{pid}" if pid else project_name
    else:
        tracker_project = tracker.get("project") or project_name

    with session_scope() as session:
        rows = (
            session.query(Ticket.ado_state)
            .filter(Ticket.project == tracker_project, Ticket.ado_state.isnot(None))
            .distinct()
            .all()
        )
    db_states = [r[0] for r in rows if r[0]]

    defaults: list[str] = []
    if t_type == "azure_devops":
        defaults = ["New", "Active", "Resolved", "Closed", "Removed"]
    elif t_type == "jira":
        defaults = ["To Do", "In Progress", "In Review", "Done"]
    elif t_type == "mantis":
        defaults = ["new", "feedback", "acknowledged", "confirmed", "assigned", "resolved", "closed"]

    combined = db_states + [s for s in defaults if s not in db_states]
    return jsonify({"ok": True, "states": combined, "tracker_type": t_type})


@bp.get("/projects/<string:project_name>/agent-workflow/<path:filename>")
def get_agent_workflow(project_name: str, filename: str):
    """Retorna la config de workflow de un agente en el proyecto."""
    if not get_project_config(project_name):
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    wf = get_agent_workflow_config(project_name, filename)
    return jsonify({
        "ok": True,
        "allowed_states": wf.get("allowed_states") or [],
        "transition_state": wf.get("transition_state") or "",
        "requires_prior_output": bool(wf.get("requires_prior_output", False)),
    })


@bp.put("/projects/<string:project_name>/agent-workflow/<path:filename>")
def put_agent_workflow(project_name: str, filename: str):
    """Guarda la config de workflow de un agente en el proyecto."""
    if not get_project_config(project_name):
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    data = request.get_json(force=True, silent=True) or {}
    workflow = {
        "allowed_states":       data.get("allowed_states") or [],
        "transition_state":     (data.get("transition_state") or "").strip(),
        "requires_prior_output": bool(data.get("requires_prior_output", False)),
    }
    try:
        set_agent_workflow_config(project_name, filename, workflow)
        return jsonify({"ok": True, **workflow})
    except Exception as e:
        logger.exception("Error al guardar workflow del agente %s/%s", project_name, filename)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── VS Code instance management ───────────────────────────────────────────────

@bp.post("/projects/<string:project_name>/launch-vscode")
def launch_vscode_for_project(project_name: str):
    """
    Asegura que haya una instancia exclusiva de VS Code en ejecución para el proyecto.
    Asigna un puerto dedicado por proyecto (rango 5060-5099) para el bridge HTTP
    de la extensión Stacky, permitiendo ejecuciones paralelas e independientes.
    """
    from services.vscode_instance_manager import (
        get_or_assign_port,
        is_alive,
        launch_vscode,
        write_vscode_settings,
    )

    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    workspace_root = cfg.get("workspace_root", "")
    if not workspace_root:
        return jsonify({"ok": False, "error": "El proyecto no tiene workspace_root configurado"}), 400

    try:
        port = get_or_assign_port(project_name, workspace_root)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 503

    if is_alive(port):
        return jsonify({
            "ok":             True,
            "port":           port,
            "already_running": True,
            "workspace_root": workspace_root,
        })

    try:
        write_vscode_settings(workspace_root, port)
    except Exception as e:
        logger.warning("No se pudo escribir .vscode/settings.json en %s: %s", workspace_root, e)

    try:
        launch_vscode(workspace_root)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({
        "ok":             True,
        "port":           port,
        "already_running": False,
        "launching":      True,
        "workspace_root": workspace_root,
    })
