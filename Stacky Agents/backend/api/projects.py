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
    "workspace_root": "C:/Repos/RSPacifico/trunk",
    "tracker_type":   "azure_devops" | "jira" | "mantis"
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
from pathlib import Path

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

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
    validate_agents_dir,
    validate_docs_paths,
    validate_workspace_root,
    write_ado_auth,
    write_jira_auth,
    write_mantis_auth,
)
from services.secrets_store import load_json_file, read_secret_from_file, write_json_file

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
    docs_paths = cfg.get("docs_paths") or {}
    return {
        "name":              cfg["name"],
        "display_name":      cfg.get("display_name", cfg["name"]),
        "workspace_root":    cfg.get("workspace_root", ""),
        "agents_dir":        cfg.get("agents_dir", ""),
        "docs_paths":        {
            "technical":      docs_paths.get("technical", ""),
            "functional":     docs_paths.get("functional", ""),
        },
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
        "has_client_profile": isinstance(cfg.get("client_profile"), dict),
    }


def _resolve_workspace_root(data: dict, cfg: dict | None = None) -> str:
    if cfg is None:
        return (data.get("workspace_root") or "").strip()
    if "workspace_root" in data:
        return (data.get("workspace_root") or "").strip()
    return (cfg.get("workspace_root") or "").strip()


def _resolve_text_field(data: dict, key: str, current: object = "") -> str:
    """Respeta strings vacíos enviados en PATCH; preserva solo si el campo falta."""
    if key in data:
        return str(data.get(key) or "").strip()
    return str(current or "").strip()


def _resolve_docs_paths(data: dict, cfg: dict | None = None) -> dict:
    """Lee docs_paths desde payload nuevo o campos planos legacy del modal."""
    current = (cfg or {}).get("docs_paths") or {}
    has_nested = "docs_paths" in data
    has_flat = "docs_technical_path" in data or "docs_functional_path" in data

    if not has_nested and not has_flat:
        return {
            "technical": current.get("technical", ""),
            "functional": current.get("functional", ""),
        }

    nested = data.get("docs_paths") if isinstance(data.get("docs_paths"), dict) else {}
    if has_nested:
        return {
            "technical": nested.get("technical", current.get("technical", "")),
            "functional": nested.get("functional", current.get("functional", "")),
        }

    return {
        "technical": (
            data.get("docs_technical_path")
            if "docs_technical_path" in data
            else nested.get("technical", current.get("technical", ""))
        ),
        "functional": (
            data.get("docs_functional_path")
            if "docs_functional_path" in data
            else nested.get("functional", current.get("functional", ""))
        ),
    }


def _resolve_agents_dir(data: dict, cfg: dict | None = None) -> str:
    if cfg is None:
        return (data.get("agents_dir") or "").strip()
    if "agents_dir" in data:
        return (data.get("agents_dir") or "").strip()
    return (cfg.get("agents_dir") or "").strip()


def _resolve_validated_agents_dir_for_patch(data: dict, cfg: dict) -> str | None:
    """Valida agents_dir solo cuando viene explícito en el payload.

    Si el modal reenvía el mismo valor legacy inválido guardado en config,
    no bloquea PATCH parciales (ej. cambiar PAT). Solo se rechazan rutas
    inválidas cuando realmente cambian respecto al valor persistido.
    """
    if "agents_dir" not in data:
        return None

    raw = (data.get("agents_dir") or "").strip()
    current = (cfg.get("agents_dir") or "").strip()
    try:
        return validate_agents_dir(raw)
    except ValueError:
        if raw == current:
            logger.warning(
                "PATCH proyecto: se ignora agents_dir legacy inválido sin cambios: %s",
                raw,
            )
            return None
        raise


def _count_docs_files(root: str) -> dict:
    """Cuenta archivos soportados para feedback del modal sin indexar contenido."""
    raw = (root or "").strip()
    result = {"path": raw, "exists": False, "readable": False, "md": 0, "pdf": 0, "total": 0}
    if not raw:
        return result

    path = Path(raw).expanduser()
    if not path.exists() or not path.is_dir():
        return result

    result["exists"] = True
    try:
        for file_path in path.rglob("*"):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix == ".md":
                result["md"] += 1
            elif suffix == ".pdf":
                result["pdf"] += 1
        result["readable"] = True
        result["total"] = result["md"] + result["pdf"]
    except (OSError, PermissionError) as exc:
        result["error"] = str(exc)
    return result


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
    workspace_root = _resolve_workspace_root(data)
    docs_paths     = _resolve_docs_paths(data)
    agents_dir     = _resolve_agents_dir(data)
    tracker_type   = (data.get("tracker_type") or "azure_devops").strip().lower()

    if not name:
        return jsonify({"ok": False, "error": "name requerido"}), 400
    if not workspace_root:
        return jsonify({"ok": False, "error": "workspace_root requerido"}), 400

    try:
        workspace_root = validate_workspace_root(workspace_root)
        docs_paths = validate_docs_paths(docs_paths)
        agents_dir = validate_agents_dir(agents_dir)

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
                docs_paths=docs_paths,
                agents_dir=agents_dir,
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
                docs_paths=docs_paths,
                agents_dir=agents_dir,
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
                docs_paths=docs_paths,
                agents_dir=agents_dir,
            )
            if pat:
                write_ado_auth(name=name, pat=pat)

        active_name = get_active_project()
        return jsonify({"ok": True, "project": _project_to_dict(cfg, active_name)})

    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
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
        workspace_root = validate_workspace_root(_resolve_workspace_root(data, cfg))
        docs_paths = validate_docs_paths(_resolve_docs_paths(data, cfg))
        agents_dir = _resolve_validated_agents_dir_for_patch(data, cfg)

        if tracker_type == "jira":
            tracker   = cfg.get("issue_tracker") or {}
            jira_url  = _resolve_text_field(data, "jira_url", tracker.get("url", ""))
            jira_key  = _resolve_text_field(data, "jira_key", tracker.get("project_key", ""))
            new_cfg   = initialize_jira_project(
                name=project_name,
                display_name=(data.get("display_name") or cfg.get("display_name", project_name)).strip(),
                workspace_root=workspace_root,
                url=jira_url,
                project_key=jira_key,
                api_version=str(data.get("api_version") or tracker.get("api_version", "3")),
                jql=(data.get("jql") or tracker.get("jql", "")),
                verify_ssl=data.get("verify_ssl", tracker.get("verify_ssl", True)),
                auth_file="auth/jira_auth.json",
                docs_paths=docs_paths,
                agents_dir=agents_dir,
            )
            jira_user  = (data.get("jira_user") or "").strip()
            jira_token = (data.get("jira_token") or "").strip()
            auth_url = jira_url or (cfg.get("issue_tracker") or {}).get("url", "")
            if jira_user and jira_token:
                write_jira_auth(name=project_name, url=auth_url, user=jira_user, token=jira_token)
            elif jira_user:
                auth_path = PROJECTS_DIR / project_name / "auth" / "jira_auth.json"
                existing_token = read_secret_from_file(
                    auth_path,
                    "token",
                    format_field="token_format",
                ).value
                if not existing_token:
                    existing_token = read_secret_from_file(
                        auth_path,
                        "password",
                        format_field="password_format",
                    ).value
                if existing_token:
                    write_jira_auth(name=project_name, url=auth_url, user=jira_user, token=existing_token)

        elif tracker_type == "mantis":
            tracker             = cfg.get("issue_tracker") or {}
            mantis_url          = _resolve_text_field(data, "mantis_url", tracker.get("url", ""))
            mantis_project_id   = _resolve_text_field(data, "mantis_project_id", tracker.get("project_id", ""))
            mantis_project_name = _resolve_text_field(data, "mantis_project_name", tracker.get("project_name", ""))
            mantis_protocol     = _resolve_text_field(data, "mantis_protocol", tracker.get("protocol", "rest")).lower()
            mantis_token        = (data.get("mantis_token") or "").strip()
            mantis_username     = (data.get("mantis_username") or "").strip()
            mantis_password     = (data.get("mantis_password") or "").strip()
            new_cfg = initialize_mantis_project(
                name=project_name,
                display_name=(data.get("display_name") or cfg.get("display_name", project_name)).strip(),
                workspace_root=workspace_root,
                url=mantis_url,
                project_id=mantis_project_id,
                project_name=mantis_project_name,
                protocol=mantis_protocol,
                verify_ssl=data.get("verify_ssl", tracker.get("verify_ssl", True)),
                auth_file="auth/mantis_auth.json",
                docs_paths=docs_paths,
                agents_dir=agents_dir,
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
                    existing_auth = load_json_file(auth_path)
                    existing_auth["project_id"] = mantis_project_id
                    write_json_file(auth_path, existing_auth)
                except Exception:
                    pass

        else:
            tracker      = cfg.get("issue_tracker") or {}
            organization = _resolve_text_field(data, "organization", tracker.get("organization", ""))
            ado_project  = _resolve_text_field(data, "ado_project", tracker.get("project", ""))
            new_cfg      = initialize_ado_project(
                name=project_name,
                display_name=(data.get("display_name") or cfg.get("display_name", project_name)).strip(),
                workspace_root=workspace_root,
                organization=organization,
                ado_project=ado_project,
                area_path=_resolve_text_field(data, "area_path", tracker.get("area_path", "")),
                auth_file="auth/ado_auth.json",
                docs_paths=docs_paths,
                agents_dir=agents_dir,
            )
            pat = (data.get("pat") or "").strip()
            if pat:
                write_ado_auth(name=project_name, pat=pat)

        active_name = get_active_project()
        return jsonify({"ok": True, "project": _project_to_dict(new_cfg, active_name)})

    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
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


@bp.post("/projects/<string:project_name>/test_docs_paths")
def test_docs_paths(project_name: str):
    """
    Valida/cuenta rutas de documentación sin guardar cambios.
    Body opcional:
      { "docs_paths": { "technical": "...", "functional": "..." } }
      o { "docs_technical_path": "...", "docs_functional_path": "..." }
    """
    data = request.get_json(force=True, silent=True) or {}
    cfg = get_project_config(project_name) or {"name": project_name, "docs_paths": {}}
    docs_paths = _resolve_docs_paths(data, cfg)
    try:
        normalized = validate_docs_paths(docs_paths)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "docs_paths": docs_paths}), 400

    counts = {
        "technical": _count_docs_files(normalized.get("technical", "")),
        "functional": _count_docs_files(normalized.get("functional", "")),
    }
    return jsonify({"ok": True, "docs_paths": normalized, "counts": counts})


@bp.post("/browse_folder")
def browse_folder():
    """
    Abre un selector nativo de carpeta en la máquina local del operador.

    Este endpoint existe porque el file picker web no puede entregar rutas
    absolutas reales, y Stacky Agents corre localmente junto al backend.
    """
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "Seleccionar carpeta").strip()
    initial_dir = (data.get("initial_dir") or "").strip()

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        kwargs = {"title": title}
        if initial_dir and Path(initial_dir).expanduser().is_dir():
            kwargs["initialdir"] = str(Path(initial_dir).expanduser())
        selected = filedialog.askdirectory(**kwargs)
        root.destroy()
    except Exception as exc:
        logger.warning("No se pudo abrir selector de carpeta: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 501

    if not selected:
        return jsonify({"ok": True, "path": ""})
    try:
        selected_path = Path(selected).resolve(strict=True)
    except Exception:
        selected_path = Path(selected).absolute()
    return jsonify({"ok": True, "path": str(selected_path).replace("\\", "/")})


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
    from models import Ticket, TicketStateHistory
    from services.flow_config_store import list_rules

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
        current_rows = (
            session.query(Ticket.ado_state)
            .filter(
                Ticket.ado_state.isnot(None),
                or_(
                    Ticket.stacky_project_name == project_name,
                    Ticket.project == tracker_project,
                ),
            )
            .distinct()
            .all()
        )
        history_rows = (
            session.query(TicketStateHistory.new_state)
            .filter(
                TicketStateHistory.stacky_project_name == project_name,
                TicketStateHistory.new_state.isnot(None),
            )
            .distinct()
            .all()
        )
    db_states = [r[0] for r in current_rows if r[0]]
    history_states = [r[0] for r in history_rows if r[0]]

    # Estados definidos en el proceso del tracker (incluye estados sin tickets,
    # ej. "Technical Review"). Best-effort: si la consulta falla, caemos a las
    # fuentes derivadas de la BD + defaults.
    tracker_def_states: list[str] = []
    if t_type == "azure_devops":
        try:
            from services.project_context import build_ado_client

            tracker_def_states = build_ado_client(project_name=project_name).fetch_states()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "tracker-states: no se pudieron leer los estados de ADO para '%s': %s",
                project_name, exc,
            )

    workflow_states: list[str] = []
    for workflow in (cfg.get("agent_workflow_configs") or {}).values():
        for state in workflow.get("allowed_states") or []:
            if isinstance(state, str) and state.strip():
                workflow_states.append(state.strip())
        transition_state = (workflow.get("transition_state") or "").strip()
        if transition_state:
            workflow_states.append(transition_state)

    flow_config_states = [
        state.strip()
        for state in (rule.get("ado_state") or "" for rule in list_rules(project_name=project_name))
        if state.strip()
    ]

    defaults: list[str] = []
    if t_type == "azure_devops":
        defaults = ["New", "Active", "Resolved", "Closed", "Removed"]
    elif t_type == "jira":
        defaults = ["To Do", "In Progress", "In Review", "Done"]
    elif t_type == "mantis":
        defaults = ["new", "feedback", "acknowledged", "confirmed", "assigned", "resolved", "closed"]

    combined: list[str] = []
    seen: set[str] = set()
    for state in tracker_def_states + db_states + history_states + workflow_states + flow_config_states + defaults:
        if state not in seen:
            seen.add(state)
            combined.append(state)
    return jsonify({"ok": True, "states": combined, "tracker_type": t_type})


@bp.get("/projects/<string:project_name>/agent-workflows")
def list_agent_workflows(project_name: str):
    """Retorna todos los workflows de agentes configurados en el proyecto.

    Responde con { "ok": true, "workflows": { filename: { ...workflow_config } } }.
    Portado desde WS2 — necesario para AgentHistoryPage.tsx (Projects.getAllAgentWorkflows).
    """
    cfg = get_project_config(project_name)
    if not cfg:
        from project_manager import find_project_for_tracker
        resolved_name, _ = find_project_for_tracker(project_name)
        if resolved_name:
            project_name = resolved_name
            cfg = get_project_config(project_name) or {}
        else:
            return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    raw_map: dict = cfg.get("agent_workflow_configs") or {}
    result: dict = {}
    for fn, wf in raw_map.items():
        result[fn] = {
            "allowed_states":        wf.get("allowed_states") or [],
            "transition_state":      wf.get("transition_state") or "",
            "requires_prior_output": bool(wf.get("requires_prior_output", False)),
            "auto_publish":          bool(wf.get("auto_publish", False)),
            "input_mode":            wf.get("input_mode") or "description",
            "input_file_prefix":     wf.get("input_file_prefix") or "",
            "output_type":           wf.get("output_type") or "note",
            "output_file_prefix":    wf.get("output_file_prefix") or "AT_",
            "jql":                   wf.get("jql") or "",
        }
    return jsonify({"ok": True, "workflows": result})


@bp.get("/projects/<string:project_name>/agent-workflow/<path:filename>")
def get_agent_workflow(project_name: str, filename: str):
    """Retorna la config de workflow de un agente en el proyecto."""
    if not get_project_config(project_name):
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    wf = get_agent_workflow_config(project_name, filename)
    return jsonify({
        "ok": True,
        "allowed_states":        wf.get("allowed_states") or [],
        "transition_state":      wf.get("transition_state") or "",
        "requires_prior_output": bool(wf.get("requires_prior_output", False)),
        "auto_publish":          bool(wf.get("auto_publish", False)),
        "input_mode":            wf.get("input_mode") or "description",
        "input_file_prefix":     wf.get("input_file_prefix") or "",
        "output_type":           wf.get("output_type") or "note",
        "output_file_prefix":    wf.get("output_file_prefix") or "AT_",
        "jql":                   wf.get("jql") or "",
    })


@bp.put("/projects/<string:project_name>/agent-workflow/<path:filename>")
def put_agent_workflow(project_name: str, filename: str):
    """Guarda la config de workflow de un agente en el proyecto.

    Expandido con campos adicionales de WS2: auto_publish, input_mode,
    input_file_prefix, output_type, output_file_prefix, jql, task_creation.
    """
    if not get_project_config(project_name):
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    data = request.get_json(force=True, silent=True) or {}
    workflow = {
        "allowed_states":        data.get("allowed_states") or [],
        "transition_state":      (data.get("transition_state") or "").strip(),
        "requires_prior_output": bool(data.get("requires_prior_output", False)),
        "auto_publish":          bool(data.get("auto_publish", False)),
        "input_mode":            (data.get("input_mode") or "description").strip(),
        "input_file_prefix":     (data.get("input_file_prefix") or "").strip(),
        "output_type":           (data.get("output_type") or "note").strip(),
        "output_file_prefix":    (data.get("output_file_prefix") or "AT_").strip(),
        "jql":                   (data.get("jql") or "").strip(),
    }
    # Preservar task_creation si viene en el body
    raw_tc = data.get("task_creation") or {}
    if raw_tc:
        workflow["task_creation"] = {
            "work_item_type": (raw_tc.get("work_item_type") or "").strip(),
            "initial_state":  (raw_tc.get("initial_state") or "").strip(),
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
    from services.project_context import ensure_project_vscode
    from services.vscode_instance_manager import get_instance_info, is_alive

    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    workspace_root = cfg.get("workspace_root", "")
    if not workspace_root:
        return jsonify({"ok": False, "error": "El proyecto no tiene workspace_root configurado"}), 400

    instance_info = get_instance_info(project_name)
    current_port = instance_info.get("port") if isinstance(instance_info, dict) else None
    already_running = (
        is_alive(int(current_port), workspace_root=workspace_root)
        if isinstance(current_port, int)
        else False
    )

    try:
        ctx = ensure_project_vscode(project_name)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 503

    return jsonify({
        "ok": True,
        "port": ctx.vscode_port,
        "already_running": already_running,
        "launching": not already_running,
        "workspace_root": ctx.workspace_root,
    })


@bp.get("/projects/<string:project_name>/vscode-status")
def vscode_status_for_project(project_name: str):
    from services.project_context import resolve_project_context
    from services.vscode_instance_manager import get_instance_info, health_details

    ctx = resolve_project_context(project_name=project_name)
    if ctx is None:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    instance_info = get_instance_info(project_name)
    port = instance_info.get("port") if isinstance(instance_info, dict) else ctx.vscode_port
    ready = False
    if isinstance(port, int):
        health = health_details(port)
        ready = bool(health and health.get("ok") is True)

    return jsonify({
        "ok": True,
        "project_name": ctx.stacky_project_name,
        "port": port,
        "ready": ready,
        "workspace_root": ctx.workspace_root,
    })
