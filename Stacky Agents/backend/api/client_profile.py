"""
api/client_profile.py — Endpoints para gestionar el `client_profile` de un
proyecto (plan 2026-05-28, generalización multi-cliente de agentes).

Endpoints:
  GET    /api/projects/<name>/client-profile
         → { ok, has_profile, profile, default_template, tracker_type }

  PUT    /api/projects/<name>/client-profile
         body: { profile: { ... } }
         → { ok, profile, warnings }

  DELETE /api/projects/<name>/client-profile
         → { ok, cleared: bool }

  GET    /api/client-profile/default?tracker_type=azure_devops|jira|mantis
         → { ok, template, tracker_type }

  POST   /api/projects/<name>/db-readonly-auth
         body: { server?, user?, password, database? }
         → { ok, auth_file }
         Guarda la credencial BD readonly cifrada en `auth/db_readonly.json`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from flask import Blueprint, jsonify, request

from project_manager import PROJECTS_DIR, get_project_config
from services.client_profile import (
    ClientProfileError,
    clear_client_profile,
    complete_client_profile,
    get_default_client_profile,
    get_project_tracker_type,
    load_client_profile,
    resolve_layout_paths,
    save_client_profile,
    validate_client_profile,
)
from services.config_transfer import record_event
from services.secrets_store import (
    set_encrypted_secret,
    write_json_file,
)

logger = logging.getLogger("stacky_agents.api.client_profile")

bp = Blueprint("client_profile", __name__, url_prefix="")


def _actor() -> str:
    return (request.headers.get("X-User-Email") or "operator").strip() or "operator"


def _tracker_type_for(project_name: str) -> str:
    cfg = get_project_config(project_name) or {}
    tracker = cfg.get("issue_tracker") or {}
    return (tracker.get("type") or "azure_devops").lower()


def _build_path_check(project_name: str, profile: dict | None) -> list[dict]:
    """Llama a resolve_layout_paths con el workspace_root del proyecto."""
    if not profile:
        return []
    cfg = get_project_config(project_name) or {}
    workspace_root = cfg.get("workspace_root") or ""
    if not workspace_root:
        return []
    return resolve_layout_paths(profile, workspace_root)


# ── GET /api/client-profile/default ──────────────────────────────────────────

@bp.get("/client-profile/default")
def get_default_template():
    """Template default por tracker (para el botón 'Aplicar template default')."""
    tracker_type = (request.args.get("tracker_type") or "azure_devops").strip().lower()
    template = get_default_client_profile(tracker_type)
    return jsonify({"ok": True, "tracker_type": tracker_type, "template": template})


# ── GET /api/projects/<name>/client-profile ──────────────────────────────────

@bp.get("/projects/<string:project_name>/client-profile")
def get_client_profile(project_name: str):
    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    profile = load_client_profile(project_name)
    tracker_type = _tracker_type_for(project_name)
    has_profile = profile is not None

    prefilled = complete_client_profile(profile, tracker_type)
    path_check = _build_path_check(project_name, prefilled)

    validation_dict = None
    if has_profile:
        validation = validate_client_profile(prefilled)
        validation_dict = validation.to_dict()

    return jsonify({
        "ok": True,
        "project": project_name,
        "tracker_type": tracker_type,
        "has_profile": has_profile,
        "profile": profile,
        "default_template": get_default_client_profile(tracker_type),
        "prefilled_profile": prefilled,
        "path_check": path_check,
        "validation": validation_dict,
    })


# ── PUT /api/projects/<name>/client-profile ──────────────────────────────────

@bp.put("/projects/<string:project_name>/client-profile")
def put_client_profile(project_name: str):
    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    data = request.get_json(force=True, silent=True) or {}
    profile = data.get("profile") if isinstance(data, dict) and "profile" in data else data

    if not isinstance(profile, dict):
        return jsonify({"ok": False, "error": "Body debe traer 'profile' como objeto JSON."}), 400

    previous = load_client_profile(project_name)

    try:
        normalized = save_client_profile(project_name, profile)
    except ClientProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error guardando client_profile de %s", project_name)
        return jsonify({"ok": False, "error": str(exc)}), 500

    record_event(
        action="client_profile_update",
        project=project_name,
        result="applied",
        actor=_actor(),
        schema_version=int(normalized.get("schema_version") or 1),
        detail={
            "had_previous": previous is not None,
            "fields_present": sorted(normalized.keys()),
        },
    )

    tracker_type = _tracker_type_for(project_name)
    validation = validate_client_profile(complete_client_profile(normalized, tracker_type))
    return jsonify({
        "ok": True,
        "profile": normalized,
        "warnings": validation.warnings,
    })


# ── DELETE /api/projects/<name>/client-profile ───────────────────────────────

@bp.delete("/projects/<string:project_name>/client-profile")
def delete_client_profile(project_name: str):
    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    cleared = clear_client_profile(project_name)
    if cleared:
        record_event(
            action="client_profile_clear",
            project=project_name,
            result="applied",
            actor=_actor(),
        )
    return jsonify({"ok": True, "cleared": cleared})


# ── POST /api/projects/<name>/db-readonly-auth ───────────────────────────────

@bp.post("/projects/<string:project_name>/db-readonly-auth")
def save_db_readonly_auth(project_name: str):
    """Guarda la credencial BD readonly cifrada en `auth/db_readonly.json`.

    Body:
      {
        "server":   "aisbddev02.cloud.ais-int.net",   (opcional)
        "database": "Pacifico",                       (opcional)
        "user":     "RSPACIFICOREAD",                 (opcional)
        "password": "*****"                           (requerido)
      }

    El password se cifra con DPAPI (mismo patrón que ado_auth.json / jira_auth.json).
    No regresa el password ni lo devuelve en eco.
    """
    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    data = request.get_json(force=True, silent=True) or {}
    password = (data.get("password") or "").strip()
    if not password:
        return jsonify({"ok": False, "error": "password requerido"}), 400

    server = (data.get("server") or "").strip()
    database = (data.get("database") or "").strip()
    user = (data.get("user") or "").strip()

    auth_dir = PROJECTS_DIR / project_name.upper() / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    auth_file = auth_dir / "db_readonly.json"

    payload: dict = {}
    if server:
        payload["server"] = server
    if database:
        payload["database"] = database
    if user:
        payload["user"] = user
    set_encrypted_secret(payload, "password", password, format_field="password_format")

    try:
        write_json_file(auth_file, payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error guardando db_readonly auth de %s", project_name)
        return jsonify({"ok": False, "error": str(exc)}), 500

    record_event(
        action="db_readonly_auth_save",
        project=project_name,
        result="applied",
        actor=_actor(),
        detail={"has_user": bool(user), "has_server": bool(server)},
    )

    return jsonify({
        "ok": True,
        "auth_file": f"auth/{auth_file.name}",
        "saved_fields": [k for k in ("server", "database", "user") if payload.get(k)],
    })


@bp.get("/projects/<string:project_name>/db-readonly-auth")
def get_db_readonly_auth_meta(project_name: str):
    """Devuelve metadatos de la credencial BD readonly (sin password)."""
    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    auth_file = PROJECTS_DIR / project_name.upper() / "auth" / "db_readonly.json"
    if not auth_file.exists():
        return jsonify({"ok": True, "has_credentials": False})

    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
    except Exception:
        return jsonify({"ok": True, "has_credentials": False, "warning": "auth_file ilegible"})

    return jsonify({
        "ok": True,
        "has_credentials": bool(data.get("password")),
        "server": data.get("server") or "",
        "database": data.get("database") or "",
        "user": data.get("user") or "",
    })
