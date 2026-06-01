"""
api/config_transfer.py — Exportación / importación portable de configuración
de proyecto (plan 2026-05-27, Requerimiento A).

Endpoints:
  POST   /api/config/export
         body opcional: { "sections": ["settings", "integrations", ...] }
         → { ok, bundle } para todos los proyectos

  POST   /api/config/import?mode=dry-run|merge|overwrite
         body: bundle multi-proyecto, o { "bundle": {...} }
         → importa/crea todos los proyectos incluidos

  POST   /api/projects/<name>/config/export
         body opcional: { "sections": ["settings", "integrations", ...] }
         → { ok, bundle }

  POST   /api/projects/<name>/config/import?mode=dry-run|merge|overwrite
         body: el bundle, o { "bundle": {...} }
         → dry-run: { ok, validation, mode, applied:false, changes, secrets_required }
           merge/overwrite: { ok, validation, mode, applied:true, changes, ... }

  GET    /api/projects/<name>/config/transfer-events?limit=100
         → { ok, events }
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from project_manager import get_project_config
from services.config_transfer import (
    ALL_SECTIONS,
    ConfigTransferError,
    apply_all_projects_import,
    apply_import,
    build_all_projects_export,
    build_export,
    is_all_projects_bundle,
    list_events,
    record_event,
    validate_import,
)

logger = logging.getLogger("stacky_agents.api.config_transfer")

bp = Blueprint("config_transfer", __name__, url_prefix="")

_VALID_MODES = {"dry-run", "merge", "overwrite"}


def _actor() -> str:
    return (request.headers.get("X-User-Email") or "operator").strip() or "operator"


def _read_sections_payload() -> list[str] | None:
    data = request.get_json(force=True, silent=True) or {}
    sections = data.get("sections")
    if sections is not None and not isinstance(sections, list):
        raise ConfigTransferError("sections debe ser una lista")
    return sections


def _read_import_bundle() -> dict:
    payload = request.get_json(force=True, silent=True) or {}
    return payload.get("bundle") if isinstance(payload, dict) and "bundle" in payload else payload


@bp.post("/config/export")
def export_all_projects_config():
    try:
        bundle = build_all_projects_export(sections=_read_sections_payload())
    except ConfigTransferError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error exportando config multi-proyecto")
        return jsonify({"ok": False, "error": str(exc)}), 500

    meta = bundle.get("meta", {})
    record_event(
        action="export-all",
        project="*",
        result="ok",
        actor=_actor(),
        schema_version=meta.get("schemaVersion"),
        app_version=meta.get("appVersion"),
        checksum=meta.get("checksum"),
        sections=meta.get("sections"),
        detail={"project_count": meta.get("projectCount")},
    )

    filename = f"stacky-projects-config-all-v{meta.get('schemaVersion')}.json"
    return jsonify({"ok": True, "bundle": bundle, "filename": filename})


@bp.post("/config/import")
def import_all_projects_config():
    mode = (request.args.get("mode") or "dry-run").strip().lower()
    if mode not in _VALID_MODES:
        return jsonify({"ok": False, "error": f"mode inválido: {mode} (válidos: {sorted(_VALID_MODES)})"}), 400

    bundle = _read_import_bundle()
    validation = validate_import(bundle)
    if not validation.ok or validation.normalized_bundle is None:
        record_event(
            action="import-all",
            project="*",
            result="rejected",
            actor=_actor(),
            mode=mode,
            schema_version=validation.schema_version,
            app_version=validation.app_version,
            detail={"errors": validation.errors},
        )
        return jsonify({"ok": False, "mode": mode, "validation": validation.to_dict()}), 400

    if not is_all_projects_bundle(validation.normalized_bundle):
        return jsonify({
            "ok": False,
            "mode": mode,
            "error": "Este endpoint espera un bundle multi-proyecto. Para un proyecto usá /projects/<name>/config/import.",
            "validation": validation.to_dict(),
        }), 400

    try:
        result = apply_all_projects_import(validation.normalized_bundle, mode=mode)
    except ConfigTransferError as exc:
        return jsonify({"ok": False, "mode": mode, "error": str(exc),
                        "validation": validation.to_dict()}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error importando config multi-proyecto (mode=%s)", mode)
        return jsonify({"ok": False, "mode": mode, "error": str(exc),
                        "validation": validation.to_dict()}), 500

    if mode != "dry-run":
        meta = (validation.normalized_bundle or {}).get("meta", {})
        record_event(
            action="import-all",
            project="*",
            result="applied" if result.get("applied") else "noop",
            actor=_actor(),
            mode=mode,
            schema_version=validation.schema_version,
            app_version=validation.app_version,
            checksum=meta.get("checksum"),
            sections=meta.get("sections"),
            detail={
                "project_count": len(result.get("projects") or []),
                "changes": len(result.get("changes") or []),
                "secrets_required": result.get("secrets_required") or [],
                "migration_notes": validation.migration_notes,
            },
        )

    return jsonify({"ok": True, "validation": validation.to_dict(), **result})


@bp.post("/projects/<string:project_name>/config/export")
def export_config(project_name: str):
    if not get_project_config(project_name):
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    try:
        bundle = build_export(project_name, sections=_read_sections_payload())
    except ConfigTransferError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error exportando config de %s", project_name)
        return jsonify({"ok": False, "error": str(exc)}), 500

    meta = bundle.get("meta", {})
    record_event(
        action="export",
        project=project_name,
        result="ok",
        actor=_actor(),
        schema_version=meta.get("schemaVersion"),
        app_version=meta.get("appVersion"),
        checksum=meta.get("checksum"),
        sections=meta.get("sections"),
    )

    filename = f"stacky-project-config-{meta.get('projectId', project_name)}-v{meta.get('schemaVersion')}.json"
    return jsonify({"ok": True, "bundle": bundle, "filename": filename})


@bp.post("/projects/<string:project_name>/config/import")
def import_config(project_name: str):
    if not get_project_config(project_name):
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    mode = (request.args.get("mode") or "dry-run").strip().lower()
    if mode not in _VALID_MODES:
        return jsonify({"ok": False, "error": f"mode inválido: {mode} (válidos: {sorted(_VALID_MODES)})"}), 400

    # Aceptar tanto el bundle directo como { "bundle": {...} }.
    bundle = _read_import_bundle()

    validation = validate_import(bundle)
    if not validation.ok or validation.normalized_bundle is None:
        record_event(
            action="import",
            project=project_name,
            result="rejected",
            actor=_actor(),
            mode=mode,
            schema_version=validation.schema_version,
            app_version=validation.app_version,
            detail={"errors": validation.errors},
        )
        return jsonify({"ok": False, "mode": mode, "validation": validation.to_dict()}), 400

    try:
        result = apply_import(project_name, validation.normalized_bundle, mode=mode)
    except ConfigTransferError as exc:
        return jsonify({"ok": False, "mode": mode, "error": str(exc),
                        "validation": validation.to_dict()}), 400
    except ValueError as exc:
        return jsonify({"ok": False, "mode": mode, "error": str(exc),
                        "validation": validation.to_dict()}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error importando config a %s (mode=%s)", project_name, mode)
        return jsonify({"ok": False, "mode": mode, "error": str(exc),
                        "validation": validation.to_dict()}), 500

    # Sólo dejamos auditoría persistente cuando efectivamente se aplica.
    if mode != "dry-run":
        meta = (validation.normalized_bundle or {}).get("meta", {})
        record_event(
            action="import",
            project=project_name,
            result="applied" if result.get("applied") else "noop",
            actor=_actor(),
            mode=mode,
            schema_version=validation.schema_version,
            app_version=validation.app_version,
            checksum=meta.get("checksum"),
            sections=meta.get("sections"),
            detail={
                "changes": len(result.get("changes") or []),
                "secrets_required": result.get("secrets_required") or [],
                "migration_notes": validation.migration_notes,
            },
        )

    return jsonify({"ok": True, "validation": validation.to_dict(), **result})


@bp.get("/projects/<string:project_name>/config/transfer-events")
def transfer_events(project_name: str):
    if not get_project_config(project_name):
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404
    try:
        limit = int(request.args.get("limit", 100))
    except ValueError:
        limit = 100
    events = list_events(project=project_name, limit=max(1, min(limit, 1000)))
    return jsonify({"ok": True, "events": events})


@bp.get("/config/sections")
def list_sections():
    """Catálogo de secciones exportables (para la UI de export selectivo)."""
    return jsonify({"ok": True, "sections": list(ALL_SECTIONS)})
