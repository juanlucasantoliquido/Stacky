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
from services.tracker_provider import get_tracker_provider  # Plan 79 F5
from services.secrets_store import (
    set_encrypted_secret,
    write_json_file,
)

logger = logging.getLogger("stacky_agents.api.client_profile")

bp = Blueprint("client_profile", __name__, url_prefix="")

# Plan 45 F5 (C5) — tipos válidos para cada entrada del catálogo de procesos.
ALLOWED_PROCESS_KINDS = {"entry", "processing", "output"}

# Kinds legacy (plan 42, en español) — perfiles guardados antes del cambio de
# allowlist (plan 45) traen estos valores y rompían CUALQUIER PUT posterior del
# perfil (el guardado de presets re-envía el perfil entero vía GET→merge→PUT).
# En vez de rechazar, se migran automáticamente al esquema vigente y se
# persisten normalizados. "otro" se mapea a vacío (tolerado como borrador; la
# materialización cae a la plantilla "default").
LEGACY_KIND_MAP = {
    "carga": "entry",
    "calculo": "processing",
    "cálculo": "processing",
    "cierre": "processing",
    "reporte": "output",
    "otro": "",
    # project_autoprofile (plan 42) emite kind="batch" — no es un kind válido
    # (batch es publish_group); se tolera como borrador sin tipo.
    "batch": "",
}

# Plan 88 F2 — grupos de publicación válidos (ortogonal a ALLOWED_PROCESS_KINDS).
ALLOWED_PUBLISH_GROUPS = {"batch", "agenda"}


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

    # Plan 45 F5 (C5) — validar process_catalog[*].kind contra la allowlist.
    # Solo se valida lo que el operador envía; si la key no viene, no hay cambio.
    catalog = profile.get("process_catalog")
    if catalog is not None:
        if not isinstance(catalog, list):
            return jsonify({"ok": False, "error": "process_catalog debe ser una lista."}), 400
        for idx, item in enumerate(catalog):
            if not isinstance(item, dict):
                return jsonify({"ok": False, "error": f"process_catalog[{idx}] debe ser un objeto."}), 400
            kind = item.get("kind")
            # Migración automática de kinds legacy en español (ver LEGACY_KIND_MAP).
            if isinstance(kind, str):
                mapped = LEGACY_KIND_MAP.get(kind.strip().lower())
                if mapped is not None:
                    kind = mapped
                    item["kind"] = mapped  # se persiste ya migrado
            # kind vacío/ausente se tolera (borrador en edición); si viene, debe ser válido.
            if kind and kind not in ALLOWED_PROCESS_KINDS:
                return jsonify({
                    "ok": False,
                    "error": "invalid_process_kind",
                    "value": kind,
                    "allowed": sorted(ALLOWED_PROCESS_KINDS),
                    "index": idx,
                }), 400
            # Plan 88 F2 — validar publish_group (ortogonal a kind; ausente se tolera).
            pg = item.get("publish_group")
            if pg and pg not in ALLOWED_PUBLISH_GROUPS:
                return jsonify({"ok": False, "error": "invalid_publish_group",
                                "value": pg, "allowed": sorted(ALLOWED_PUBLISH_GROUPS),
                                "index": idx}), 400

    # Plan 98 F1 — validadores devops (drafts/presets/settings/environment)
    # EXTRAIDOS a services/client_profile_keys.py para que el PATCH (F2) valide
    # exactamente igual sin duplicar codigo. Mismo orden que antes del refactor.
    from services.client_profile_keys import validate_profile_key
    for _key in ("devops_pipeline_drafts", "devops_publication_presets",
                 "devops_publication_settings", "devops_environment_settings"):
        _err = validate_profile_key(_key, profile.get(_key))
        if _err:
            return jsonify({"ok": False, "error": _err}), 400

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

    # Plan 79 F5 — warnings NO bloqueantes si in_progress/next_state_ok no
    # existen en el tracker activo. Defensivo: si fetch_states falla, sin
    # warnings (nunca impide guardar).
    state_warnings: list = []
    try:
        from harness.task_states import validate_states_against_tracker

        prov = get_tracker_provider(project_name)
        valid_states = prov.fetch_states() if prov else []
        state_warnings = validate_states_against_tracker(normalized, valid_states)
    except Exception:  # noqa: BLE001
        state_warnings = []

    return jsonify({
        "ok": True,
        "profile": normalized,
        "warnings": validation.warnings,
        "state_warnings": state_warnings,
    })


# ── PATCH /api/projects/<name>/client-profile/keys/<key> (Plan 98) ───────────
# Lock de proceso: serializa load→merge→save de PATCHes concurrentes (mono-operador,
# un solo proceso Flask — suficiente; NO hay lock hoy en services/client_profile.py,
# verificado por grep de threading/Lock = 0 matches).
import threading
_PROFILE_WRITE_LOCK = threading.Lock()


@bp.patch("/projects/<string:project_name>/client-profile/keys/<string:key>")
def patch_client_profile_key(project_name: str, key: str):
    import config as _config
    if not getattr(_config.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False):
        from flask import abort
        abort(404)  # guard per-request, patrón api/devops.py:47-48

    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    from services.client_profile_keys import PATCHABLE_PROFILE_KEYS, validate_profile_key
    if key not in PATCHABLE_PROFILE_KEYS:
        return jsonify({"ok": False, "error": "key_not_patchable",
                        "allowed": sorted(PATCHABLE_PROFILE_KEYS)}), 400

    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data, dict) or "value" not in data:
        return jsonify({"ok": False, "error": "Body debe traer 'value'."}), 400
    value = data["value"]

    err = validate_profile_key(key, value)
    if err:
        return jsonify({"ok": False, "error": err}), 400

    with _PROFILE_WRITE_LOCK:
        base = load_client_profile(project_name) or {}
        if value is None:
            base.pop(key, None)          # PATCH value=null ⇒ borrar la key
        else:
            base[key] = value
        try:
            normalized = save_client_profile(project_name, base)
        except ClientProfileError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error en PATCH de client_profile.%s de %s", key, project_name)
            return jsonify({"ok": False, "error": str(exc)}), 500

    record_event(
        action="client_profile_key_patch",
        project=project_name,
        result="applied",
        actor=_actor(),
        schema_version=int(normalized.get("schema_version") or 1),
        detail={"key": key},
    )
    return jsonify({"ok": True, "key": key, "value": normalized.get(key)})


# ── GET /api/projects/<name>/process-catalog/autodetect ──────────────────────
# Detección automática del catálogo de procesos (read-only, disparada por el
# operador desde la UI). Nunca escribe: el frontend persiste vía el riel
# GET→merge→PUT (human-in-the-loop). Reusa el gate de sugerencias (default ON).

_KIND_ENTRY_HINTS = ("carga", "entrada", "input", "import", "recepci", "ingesta")
_KIND_OUTPUT_HINTS = ("salida", "output", "extrae", "reporte", "export")


def _infer_kind(text: str) -> str:
    """Heurística determinista por keywords; si no hay señal, borrador sin tipo."""
    lower = (text or "").lower()
    if any(h in lower for h in _KIND_ENTRY_HINTS):
        return "entry"
    if any(h in lower for h in _KIND_OUTPUT_HINTS):
        return "output"
    return ""


@bp.get("/projects/<string:project_name>/process-catalog/autodetect")
def autodetect_process_catalog(project_name: str):
    """Agrega candidatos de proceso desde dos fuentes deterministas (best-effort):

      1. docs — headings reales de los docs del proyecto
         (services.project_autoprofile, nunca inventa nombres).
      2. executions — procesos citados en épicas publicadas
         (grounding_observatory, nunca inventa nombres).

    Excluye nombres ya presentes en el catálogo guardado. Una fuente caída no
    anula la otra.
    """
    import config as _config
    if not getattr(_config.config, "STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED", True):
        return jsonify({"ok": False, "error": "feature_disabled"}), 404

    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    existing_catalog = (load_client_profile(project_name) or {}).get("process_catalog") or []
    seen: set[str] = {
        (e.get("name") or "").strip().lower()
        for e in existing_catalog
        if isinstance(e, dict) and (e.get("name") or "").strip()
    }

    candidates: list[dict] = []
    counts = {"docs": 0, "executions": 0}

    # Fuente 1 — headings de docs (requiere docs_root configurado en el proyecto).
    try:
        docs_root_str = (cfg.get("docs_root") or "").strip()
        if docs_root_str:
            docs_root = Path(docs_root_str)
            if docs_root.is_dir():
                from services.project_autoprofile import draft_profile_from_docs
                for item in (draft_profile_from_docs(docs_root).get("process_catalog") or []):
                    name = (item.get("name") or "").strip()
                    key = name.lower()
                    if not name or key in seen:
                        continue
                    seen.add(key)
                    candidates.append({
                        "name": name,
                        "purpose": item.get("purpose") or "",
                        "kind": _infer_kind(name),
                        "source": "docs",
                    })
                    counts["docs"] += 1
    except Exception:  # noqa: BLE001 — best-effort
        logger.exception("autodetect: fuente docs falló para %s", project_name)

    # Fuente 2 — procesos citados en épicas publicadas.
    try:
        from api.agents import _collect_epic_summaries
        from services.grounding_observatory import suggest_process_catalog_entries
        summaries, _ = _collect_epic_summaries(project_name)
        for item in suggest_process_catalog_entries(summaries, existing_catalog):
            name = (item.get("name") or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            candidates.append({
                "name": name,
                "purpose": f"Citado en {item.get('occurrences', 1)} épica(s) publicada(s)",
                "kind": _infer_kind(name),
                "source": "executions",
            })
            counts["executions"] += 1
    except Exception:  # noqa: BLE001 — best-effort
        logger.exception("autodetect: fuente ejecuciones falló para %s", project_name)

    return jsonify({"ok": True, "project": project_name,
                    "candidates": candidates, "counts": counts})


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
