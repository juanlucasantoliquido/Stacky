"""Plan 201 F4/F6/F7/F8 — API del Taller de Compilación.

Escanear, tildar, diagnosticar el toolchain, compilar, seguir el build, descargar
el artefacto y registrarlo como app de despliegue. Todo por clicks del operador:
cada acción con efecto (compilar, cancelar, descargar como app) exige `confirm`.

Sin toolchain no se rompe nada: `/compile` responde 200 con el doctor.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

import config as _config
from runtime_paths import _active_workspace_root, data_dir
from services import solution_builder, solution_store
from services.build_toolchain import detect_toolchain

logger = logging.getLogger(__name__)

bp = Blueprint("devops_build_workshop", __name__, url_prefix="/devops/build")

_EMPTY_CATALOG = {"scanned_at": None, "truncated": False, "solutions": []}


def _guard():
    if not bool(getattr(_config.config, "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", False)):
        abort(404)


def _workspace():
    try:
        ws = _active_workspace_root()
    except Exception:  # noqa: BLE001
        logger.debug("no se pudo resolver el workspace activo", exc_info=True)
        ws = None
    return str(ws) if ws else None


def _no_workspace_payload() -> dict:
    return {
        "workspace_root": None,
        "catalog": dict(_EMPTY_CATALOG),
        "toolchain": detect_toolchain(),
        "warning": "No hay proyecto activo con workspace_root.",
    }


def _friendly_for(slug: str) -> str:
    ws = _workspace()
    if not ws:
        return slug
    for s in solution_store.load_catalog(ws).get("solutions", []):
        if s.get("slug") == slug:
            return s.get("friendly_name") or slug
    return slug


# ── F4 — scan / catálogo / track / doctor ────────────────────────────────────

@bp.post("/scan")
def scan_route():
    _guard()
    ws = _workspace()
    if not ws:
        return jsonify(_no_workspace_payload())
    catalog = solution_store.rescan_and_save(ws)
    return jsonify({"workspace_root": ws, "catalog": catalog,
                    "toolchain": detect_toolchain()})


@bp.get("/catalog")
def catalog_route():
    _guard()
    ws = _workspace()
    if not ws:
        return jsonify(_no_workspace_payload())
    return jsonify({"workspace_root": ws, "catalog": solution_store.load_catalog(ws),
                    "toolchain": detect_toolchain()})


@bp.post("/track")
def track_route():
    _guard()
    body = request.get_json(silent=True) or {}
    slug = (body.get("slug") or "").strip()
    tracked = bool(body.get("tracked"))
    ws = _workspace()
    if not ws:
        return jsonify({"catalog": dict(_EMPTY_CATALOG)})
    return jsonify({"catalog": solution_store.set_tracked(ws, slug, tracked)})


@bp.get("/doctor")
def doctor_route():
    _guard()
    return jsonify({"toolchain": detect_toolchain()})


# ── F6 — compile / status / cancel ───────────────────────────────────────────

@bp.post("/compile")
def compile_route():
    _guard()
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm requerido"}), 400

    slugs = [s for s in (body.get("slugs") or []) if isinstance(s, str) and s.strip()]
    unified = bool(body.get("unified"))
    if not slugs:
        return jsonify({"error": "Elegí al menos una solución"}), 400
    if len(slugs) > 1 and not unified:
        return jsonify({"error": "Para varias soluciones usá 'unificado' o compilá de a una"}), 400

    ws = _workspace()
    if not ws:
        return jsonify({"error": "No hay proyecto activo con workspace_root."}), 400

    conocidos = {s.get("slug") for s in solution_store.load_catalog(ws).get("solutions", [])
                 if s.get("tracked")}
    desconocidos = [s for s in slugs if s not in conocidos]
    if desconocidos:
        return jsonify({"error": f"Soluciones no tildadas en el catálogo: {desconocidos}"}), 400

    toolchain = detect_toolchain()
    if not toolchain.get("available"):
        # 200 a propósito: el front lo renderiza como doctor, no como error.
        return jsonify({"status": "toolchain_missing", "toolchain": toolchain})

    build_id = solution_builder.start_build(slugs, unified, ws)
    return jsonify({"build_id": build_id})


@bp.get("/status/<build_id>")
def status_route(build_id: str):
    _guard()
    status = solution_builder.get_status(build_id)
    if status is None:
        abort(404)
    return jsonify(status)


@bp.post("/cancel/<build_id>")
def cancel_route(build_id: str):
    _guard()
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm requerido"}), 400
    return jsonify({"cancelled": bool(solution_builder.cancel(build_id))})


# ── F7 — descarga del artefacto ──────────────────────────────────────────────

@bp.get("/artifact/<build_id>/download")
def artifact_download_route(build_id: str):
    _guard()
    # `build_id` es SOLO una clave de búsqueda: nunca se interpola en una ruta.
    zip_path = solution_builder.artifact_zip_path(build_id)
    if not zip_path:
        abort(404)
    root = (data_dir() / "build_artifacts").resolve()
    target = Path(zip_path).resolve()
    try:
        dentro = os.path.commonpath([str(root), str(target)]) == str(root)
    except ValueError:  # rutas en unidades distintas
        dentro = False
    if not dentro:
        abort(400)
    if not target.exists():
        abort(404)
    return send_file(str(target), as_attachment=True, download_name=target.name)


# ── F8 — bridge al Centro de Despliegues ─────────────────────────────────────

@bp.post("/register-deploy-app")
def register_deploy_app_route():
    _guard()
    from services import deploy_store

    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm requerido"}), 400

    build_id = body.get("build_id")
    slug = body.get("slug")
    status = solution_builder.get_status(build_id) if build_id else None
    if not status or status.get("status") != "success":
        return jsonify({"error": "El build no está terminado con éxito"}), 400

    artifact_dir = solution_builder.artifact_dir_for(build_id, slug)
    if not artifact_dir or not os.path.isdir(artifact_dir):
        return jsonify({"error": "Artefacto no encontrado"}), 400

    # El Centro de Despliegues EXIGE al menos un destino con `install_path`
    # absoluto (`deploy_planner.validate_app`). `install_path` es a dónde se
    # COPIAN los archivos: inventarlo sería escribir en un lugar que el operador
    # no eligió. Si ya existe la app, se conservan sus destinos; si no, el
    # operador tiene que decirlos.
    existente = deploy_store.get_app(slug) or {}
    targets = body.get("targets")
    if not isinstance(targets, dict) or not targets:
        targets = existente.get("targets") or {}
    if not targets:
        return jsonify({
            "error": ("Falta el destino: indicá al menos un 'targets' con "
                      "install_path absoluto y smoke.kind (http|ps|none). "
                      "Configuralo en la sección Despliegues y volvé a registrar."),
            "needs_targets": True,
        }), 400

    payload = {
        "id": slug,
        "name": _friendly_for(slug),
        "artifact": {"kind": "folder", "path": os.path.abspath(str(artifact_dir))},
        "targets": targets,
    }
    try:
        app = deploy_store.upsert_app(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"app": app})
