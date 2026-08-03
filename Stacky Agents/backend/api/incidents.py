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


def _pidio_refrescar() -> bool:
    """`?refresh=1` — el operador quiere que se vuelva a mirar el disco.

    Es opt-in a propósito: si cada consulta tirara el memo, la detección se
    convertiría en un `git rev-parse` por render y por poll, que es justo lo que
    el memo viene a evitar.
    """
    return (request.args.get("refresh") or "").strip().lower() in ("1", "true", "on", "yes")


@bp.get("/dev-pr/preflight")
def dev_pr_preflight():
    """Chequeo PREVIO de repo git para el tilde "Abrir PR" del ticket.

    200 SIEMPRE, incluso con la flag apagada o el proyecto roto: el wrapper
    `api.*` del frontend LANZA en non-2xx (client.ts) y dejaria el control en el
    limbo. El fallo viaja en el body (`ok`/`reason`/`message`) para que el tilde
    se muestre DESHABILITADO con el motivo a la vista.
    """
    from services import incident_dev_pr
    project = (request.args.get("project") or "").strip() or None
    try:
        if _pidio_refrescar():
            # El operador pide re-mirar el disco (recién hizo `git init`, o
            # arregló la ruta): sin esto contestaría el memo y el resultado
            # seguiría siendo el viejo.
            incident_dev_pr.invalidate_repo_detection()
        return jsonify(incident_dev_pr.preflight_repo(project))
    except Exception as exc:  # noqa: BLE001 — nunca 500: rompería el board entero
        return jsonify({
            "ok": False, "reason": "error_interno",
            "message": f"No se pudo verificar el repositorio git: {exc}",
            "warning": None, "warning_message": "",
            "repo_root": None, "origin": None, "workspace_root": None,
            "tracker_type": None, "provider_label": None, "project": project,
        })


@bp.get("/dev-pr/result/<int:execution_id>")
def dev_pr_result(execution_id: int):
    """Resultado del auto-PR de un run: creado (con URL), no creado (con motivo)
    o fallado (con el error). 200 siempre, por la misma razón que el preflight."""
    from services import incident_dev_pr
    try:
        return jsonify(incident_dev_pr.result_for_execution(execution_id))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "found": False, "status": "error",
                        "terminal": True, "execution_id": int(execution_id),
                        "error": str(exc)})


@bp.get("/dev-pr/preflight-all")
def dev_pr_preflight_all():
    """Estado del auto-PR de TODOS los proyectos configurados, de un vistazo.

    Existe para que el operador no tenga que ir cambiando de proyecto activo y
    tildando de a uno para descubrir cuáles tienen git reconocido. El estado de
    git se calcula aunque el auto-PR esté apagado: son dos preguntas distintas
    y `dev_pr_enabled` viaja aparte.
    """
    from config import config as _cfg
    from services import incident_dev_pr
    habilitado = bool(getattr(_cfg, "STACKY_INCIDENT_DEV_PR_ENABLED", False))
    try:
        if _pidio_refrescar():
            incident_dev_pr.invalidate_repo_detection()
        filas = incident_dev_pr.preflight_all_projects()
    except Exception as exc:  # noqa: BLE001 — 200 siempre: no rompe la pantalla
        return jsonify({
            "ok": False, "projects": [], "total": 0, "con_git": 0,
            "dev_pr_enabled": habilitado,
            "message": f"No se pudo verificar el estado de los proyectos: {exc}",
        })
    return jsonify({
        "ok": True,
        "projects": filas,
        "total": len(filas),
        "con_git": sum(1 for f in filas if f.get("ok")),
        "dev_pr_enabled": habilitado,
        "message": "",
    })


@bp.get("/dev-pr/result-by-ticket/<int:ticket_id>")
def dev_pr_result_by_ticket(ticket_id: int):
    """Resultado del auto-PR del ÚLTIMO run del Dev Resolutor sobre este ticket.

    Existe para que el resultado sobreviva a un refresh: consultarlo sólo por
    `execution_id` obligaría a la UI a recordarlo en memoria y el operador que
    recarga la página perdería el resultado del PR para siempre.
    """
    from services import incident_dev_pr
    _vacio = {"ok": True, "found": False, "status": "no_solicitado",
              "terminal": True, "execution_id": None}
    try:
        from db import session_scope
        from models import AgentExecution
        with session_scope() as session:
            fila = (
                session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == ticket_id,
                        AgentExecution.agent_type == "incident_dev")
                .order_by(AgentExecution.id.desc())
                .first()
            )
            execution_id = fila.id if fila is not None else None
        if execution_id is None:
            return jsonify(_vacio)
        return jsonify(incident_dev_pr.result_for_execution(execution_id))
    except Exception as exc:  # noqa: BLE001 — 200 siempre; nunca rompe el board
        return jsonify({**_vacio, "ok": False, "status": "error", "error": str(exc)})


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
