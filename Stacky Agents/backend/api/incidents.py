"""Plan 131 — Resolutor de incidencias multimodal."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("incidents", __name__, url_prefix="/incidents")


def _feature_disabled_response():
    return jsonify({"ok": False, "error": "feature_disabled"}), 404


@bp.get("/status")
def incidents_status():
    from config import config as _cfg
    from services.incident_store import ALLOWED_EXTENSIONS, MAX_FILES, MAX_FILE_BYTES
    return jsonify({
        "enabled": bool(_cfg.STACKY_INCIDENT_RESOLVER_ENABLED),
        "max_files": MAX_FILES,
        "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
        # Plan 166 F3 — el modal usa este campo para saltar preview+confirm y
        # entrar en modo lote (creación directa sin diálogos).
        "auto_publish_enabled": bool(getattr(_cfg, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", False)),
        # Plan 166 F5 — el board usa este campo para mostrar/ocultar el botón
        # "Resolver con agente" en las Issues.
        "dev_resolver_enabled": bool(getattr(_cfg, "STACKY_INCIDENT_DEV_RESOLVER_ENABLED", False)),
        # Plan 177 — el board usa este campo para mostrar/ocultar el checkbox
        # "Abrir PR" junto al botón "Resolver con agente".
        "dev_pr_enabled": bool(getattr(_cfg, "STACKY_INCIDENT_DEV_PR_ENABLED", False)),
    })


@bp.post("")
def create_incident_endpoint():
    from config import config as _cfg
    if not _cfg.STACKY_INCIDENT_RESOLVER_ENABLED:
        return _feature_disabled_response()

    from services import incident_store
    from services.stacky_logger import logger as stacky_logger

    # C9 — guard temprano por Content-Length ANTES de leer nada (app.py no
    # define MAX_CONTENT_LENGTH). 1 MB de margen para el overhead multipart.
    if (
        request.content_length
        and request.content_length > incident_store.MAX_TOTAL_BYTES + 1_048_576
    ):
        return jsonify({
            "ok": False, "error": "validation_error", "message": "total_too_big",
        }), 413

    text = request.form.get("text", "")
    files: list[tuple[str, bytes]] = []
    for f in request.files.getlist("files"):
        if not f or not f.filename:
            continue
        # Lectura con cap por archivo: nunca se lee más de MAX_FILE_BYTES+1.
        data = f.read(incident_store.MAX_FILE_BYTES + 1)
        if len(data) > incident_store.MAX_FILE_BYTES:
            return jsonify({
                "ok": False, "error": "validation_error",
                "message": f"file_too_big:{f.filename}",
            }), 400
        files.append((f.filename, data))

    # Plan 166 F3 — auto_publish del form ("true"/"false" string, form-data).
    auto_publish = (request.form.get("auto_publish") or "").strip().lower() == "true"

    try:
        incident = incident_store.create_incident(text, files, auto_publish=auto_publish)
    except ValueError as exc:
        return jsonify({
            "ok": False, "error": "validation_error", "message": str(exc),
        }), 400

    stacky_logger.info(
        "incidents", "incident_created",
        incident_id=incident["id"], files=len(incident["files"]),
    )
    return jsonify({"ok": True, "incident": incident}), 201


@bp.get("")
def list_incidents_endpoint():
    from config import config as _cfg
    if not _cfg.STACKY_INCIDENT_RESOLVER_ENABLED:
        return _feature_disabled_response()

    from services import incident_store
    return jsonify({"ok": True, "incidents": incident_store.list_incidents()})


@bp.get("/<incident_id>")
def get_incident_endpoint(incident_id: str):
    from config import config as _cfg
    if not _cfg.STACKY_INCIDENT_RESOLVER_ENABLED:
        return _feature_disabled_response()

    from services import incident_store
    incident = incident_store.get_incident(incident_id)
    if incident is None:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "incident": incident})


@bp.get("/<incident_id>/console")
def get_incident_console(incident_id: str):
    """Plan 200 R1 — qué ejecuciones tiene esta incidencia, para pintar su consola.

    No devuelve el transcript: el frontend pide `/api/executions/<id>/logs` por
    cada una. Reusar esa consola en vez de inventar un endpoint de transcript es
    lo que hace que esto no agregue un canal más que mantener.
    """
    from config import config as _cfg

    if not _cfg.STACKY_INCIDENT_RESOLVER_ENABLED:
        return _feature_disabled_response()
    if not getattr(_cfg, "STACKY_INCIDENT_CONSOLE_ENABLED", True):
        return _feature_disabled_response()

    from services import incident_store
    incident = incident_store.get_incident(incident_id)
    if incident is None:
        return jsonify({"ok": False, "error": "not_found"}), 404

    execs = list(incident.get("executions") or [])
    # Back-compat: las incidencias anteriores al 200 solo tienen `execution_id`.
    if not execs and incident.get("execution_id") is not None:
        execs = [{
            "execution_id": int(incident["execution_id"]),
            "kind": "analysis",
            "linked_at": None,
        }]

    return jsonify({
        "ok": True,
        "incident_id": incident_id,
        "primary_execution_id": incident.get("execution_id"),
        "executions": execs,
    })


def _sql_deploy_gates(incident_id: str):
    """Gates de las rutas R2: devuelve (respuesta_de_error, incidencia)."""
    from config import config as _cfg

    if not _cfg.STACKY_INCIDENT_RESOLVER_ENABLED:
        return _feature_disabled_response(), None
    if not getattr(_cfg, "STACKY_SQL_DEPLOY_DETECT_ENABLED", True):
        return _feature_disabled_response(), None

    from services import incident_store
    incidencia = incident_store.get_incident(incident_id)
    if incidencia is None:
        return (jsonify({"ok": False, "error": "not_found"}), 404), None
    return None, incidencia


@bp.get("/<incident_id>/sql-deploy")
def get_incident_sql_deploy(incident_id: str):
    """Plan 200 R2 — ¿esta incidencia implica desplegar SQL en otro ambiente?"""
    from dataclasses import asdict

    error, incidencia = _sql_deploy_gates(incident_id)
    if error:
        return error

    from services import sql_deploy_detector

    resultado = asdict(sql_deploy_detector.detect_for_incident(incidencia))
    resultado["ok"] = True
    return jsonify(resultado)


@bp.get("/<incident_id>/sql-script")
def get_incident_sql_script(incident_id: str):
    """Plan 200 R2 — el contenido del .sql, leído SERVER-SIDE por sha.

    Es la misma fuente que vería una ejecución: el cliente nunca manda el SQL,
    solo su sha. Así el preview y lo que se ejecutaría no pueden divergir.
    """
    error, _incidencia = _sql_deploy_gates(incident_id)
    if error:
        return error

    from services import sql_deploy_detector

    script = sql_deploy_detector.read_script({
        "source": "incident_attachment",
        "incident_id": incident_id,
        "sha256": (request.args.get("sha") or "").strip(),
    })
    if script is None:
        return jsonify({"ok": False, "error": "script_not_found"}), 404
    return jsonify({"ok": True, **script})


@bp.get("/<incident_id>/files/<stored_name>")
def get_incident_file(incident_id: str, stored_name: str):
    from config import config as _cfg
    if not _cfg.STACKY_INCIDENT_RESOLVER_ENABLED:
        return _feature_disabled_response()

    from flask import send_file
    from services import incident_store

    base = (incident_store.incidents_root() / incident_id).resolve()
    candidate = (base / stored_name).resolve()
    try:
        inside = candidate.is_relative_to(base)
    except AttributeError:  # pragma: no cover — py<3.9 fallback (repo usa 3.13)
        inside = str(candidate).startswith(str(base))

    if not inside or not candidate.is_file():
        return jsonify({"ok": False, "error": "not_found"}), 404
    return send_file(str(candidate))
