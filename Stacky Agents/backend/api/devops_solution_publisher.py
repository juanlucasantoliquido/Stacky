"""Plan 215 F5/F6 — API del Publicador de Soluciones.

Catálogo lazy (se escanea UNA sola vez), config por solución, escalera de
fallback (re-scan / deep-scan / alta manual), publish 1-click con confirm,
seguimiento, descarga, historial y contexto para el asistente DevOps.

Degradación (G7): sin toolchain .NET el `/run` responde 200 con el doctor; sin
los módulos del Plan 201 TODO endpoint que los toque responde 200 con
`build_workshop_unavailable`. Nunca un 500 por ImportError.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

import config as _config
from runtime_paths import _active_workspace_root, data_dir

logger = logging.getLogger(__name__)

bp = Blueprint("devops_solution_publisher", __name__, url_prefix="/devops/solution-publisher")

_EMPTY_CATALOG = {"scanned_at": None, "truncated": False, "solutions": []}
_UNAVAILABLE = {
    "error": "build_workshop_unavailable",
    "detail": "Requiere el Taller de Compilación (Plan 201) implementado.",
}


def _guard():
    if not bool(getattr(_config.config, "STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED", False)):
        abort(404)


def _deps_or_none():
    """G7 bis: el Plan 201 podría no estar mergeado. Nunca ImportError al cliente."""
    try:
        from services import build_toolchain, solution_store

        return solution_store, build_toolchain
    except ImportError:
        logger.warning("módulos del Plan 201 ausentes; el publicador degrada", exc_info=True)
        return None, None


def _workspace():
    try:
        ws = _active_workspace_root()
    except Exception:  # noqa: BLE001
        logger.debug("no se pudo resolver el workspace activo", exc_info=True)
        ws = None
    return str(ws) if ws else None


def _enrich(catalog: dict, workspace: str, toolchain: dict) -> dict:
    """Lecturas DIRIGIDAS O(#proyectos) — NO re-walkea el workspace (KPI-2)."""
    from services import publish_config_store, publish_profile_scanner

    out = []
    for sol in catalog.get("solutions") or []:
        sol = dict(sol)
        sln = sol.get("sln_path") or ""
        try:
            sol["missing"] = not os.path.exists(sln)
        except (OSError, ValueError):
            sol["missing"] = True
        sol.setdefault("origin", "scan")
        try:
            cfg = publish_config_store.load_config(workspace, sol.get("slug"))
        except Exception:  # noqa: BLE001
            cfg = publish_config_store.default_config()
        sol["config"] = cfg
        try:
            sol["plan"] = publish_profile_scanner.resolve_publish_plan(sol, cfg, toolchain)
        except Exception:  # noqa: BLE001
            logger.debug("no se pudo resolver el plan de publish", exc_info=True)
            sol["plan"] = {"mode_effective": "build_only", "supported": False,
                           "reason": "plan_no_resoluble", "target": sln, "argv_tail": []}
        profiles = []
        try:
            by_proj = publish_profile_scanner.scan_publish_profiles(sol.get("projects") or [])
            for csproj, entries in by_proj.items():
                for e in entries:
                    profiles.append({**e, "csproj_path": csproj})
        except Exception:  # noqa: BLE001
            logger.debug("no se pudieron leer los perfiles de publish", exc_info=True)
        sol["publish_profiles"] = profiles
        out.append(sol)
    return {**catalog, "solutions": out}


def _catalog_payload(first_scan_ran: bool, workspace, store, toolchain) -> dict:
    catalog = store.load_catalog(workspace) if workspace else dict(_EMPTY_CATALOG)
    payload = {
        "workspace_root": workspace,
        "catalog": _enrich(catalog, workspace or "", toolchain),
        "toolchain": toolchain,
        "first_scan_ran": first_scan_ran,
    }
    if not workspace:
        payload["warning"] = "No hay proyecto activo con workspace_root."
    return payload


@bp.get("/catalog")
def catalog_route():
    _guard()
    store, toolchain_mod = _deps_or_none()
    if store is None:
        return jsonify(_UNAVAILABLE), 200
    ws = _workspace()
    tc = toolchain_mod.detect_toolchain()
    if not ws:
        return jsonify(_catalog_payload(False, None, store, tc))
    first = False
    # Lazy first-scan (KPI-1/2): SOLO si nunca se escaneó este workspace.
    if store.load_catalog(ws).get("scanned_at") is None:
        store.rescan_preserving_manual(ws)
        first = True
    return jsonify(_catalog_payload(first, ws, store, tc))


@bp.post("/rescan")
def rescan_route():
    _guard()
    store, toolchain_mod = _deps_or_none()
    if store is None:
        return jsonify(_UNAVAILABLE), 200
    ws = _workspace()
    tc = toolchain_mod.detect_toolchain()
    if not ws:
        return jsonify(_catalog_payload(False, None, store, tc))
    store.rescan_preserving_manual(ws)
    return jsonify(_catalog_payload(True, ws, store, tc))


@bp.post("/config")
def save_config_route():
    """No toca módulos del 201: sigue operativo aunque falte el Taller."""
    _guard()
    from services import publish_config_store

    body = request.get_json(silent=True) or {}
    slug = (body.get("slug") or "").strip()
    if not slug:
        return jsonify({"error": "slug requerido"}), 400
    ws = _workspace() or ""
    try:
        cfg = publish_config_store.save_config(ws, slug, body.get("config") or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"config": cfg})


@bp.post("/solutions/import")
def import_solutions_route():
    _guard()
    store, toolchain_mod = _deps_or_none()
    if store is None:
        return jsonify(_UNAVAILABLE), 200
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm requerido"}), 400
    ws = _workspace()
    if not ws:
        return jsonify({"error": "sin proyecto activo"}), 400

    added, rejected = [], []
    for raw in body.get("paths") or []:
        path = (raw or "").strip().strip('"')
        if not path:
            continue
        try:
            block = store.add_manual_solution(ws, path)
        except ValueError as exc:
            rejected.append({"path": path, "reason": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 — una ruta mala NUNCA da 500
            rejected.append({"path": path, "reason": str(exc)})
            continue
        match = next(
            (s for s in block.get("solutions", [])
             if os.path.normcase(s.get("sln_path", "")) == os.path.normcase(
                 os.path.normpath(os.path.abspath(path)))),
            None,
        )
        if match:
            added.append(match.get("slug"))

    tc = toolchain_mod.detect_toolchain()
    return jsonify({"added": added, "rejected": rejected,
                    "catalog": _catalog_payload(False, ws, store, tc)["catalog"]})


@bp.post("/deep-scan")
def deep_scan_route():
    """Síncrono con presupuesto de tiempo (hasta 45s) — la UI muestra spinner (C13)."""
    _guard()
    store, _tc = _deps_or_none()
    if store is None:
        return jsonify(_UNAVAILABLE), 200
    from services.solution_deep_scan import deep_scan_sln_paths

    ws = _workspace()
    if not ws:
        return jsonify({"paths": [], "new_paths": [], "timed_out": False,
                        "warning": "No hay proyecto activo con workspace_root."})
    result = deep_scan_sln_paths(ws)
    known = {
        os.path.normcase(s.get("sln_path", ""))
        for s in store.load_catalog(ws).get("solutions", [])
    }
    new_paths = [p for p in result["paths"] if os.path.normcase(p) not in known]
    return jsonify({"paths": result["paths"], "new_paths": new_paths,
                    "timed_out": result["timed_out"]})


@bp.post("/run")
def run_route():
    _guard()
    store, toolchain_mod = _deps_or_none()
    if store is None:
        return jsonify(_UNAVAILABLE), 200
    from services import publish_config_store, publish_profile_scanner, solution_publisher

    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm requerido"}), 400
    slug = (body.get("slug") or "").strip()
    ws = _workspace()
    if not ws:
        return jsonify({"error": "sin proyecto activo"}), 400
    sol = next((s for s in store.load_catalog(ws).get("solutions", [])
                if s.get("slug") == slug), None)
    if sol is None:
        return jsonify({"error": "solución no encontrada en el catálogo"}), 400

    tc = toolchain_mod.detect_toolchain()
    # 200 SIEMPRE para doctor/unsupported: el wrapper api.* del frontend LANZA en
    # non-2xx y estos dos casos la UI los tiene que renderizar.
    if not tc.get("available"):
        return jsonify({"status": "toolchain_missing", "toolchain": tc}), 200
    cfg = publish_config_store.load_config(ws, slug)
    plan = publish_profile_scanner.resolve_publish_plan(sol, cfg, tc)
    if not plan.get("supported"):
        return jsonify({"status": "unsupported", "reason": plan.get("reason"),
                        "plan": plan}), 200

    run_id = solution_publisher.start_publish(slug, ws)
    return jsonify({"run_id": run_id, "status": "running"})


@bp.get("/runs/<run_id>/status")
def run_status_route(run_id: str):
    _guard()
    from services import solution_publisher

    status = solution_publisher.get_status(run_id)
    if status is None:
        # C1 — desconocido (backend reiniciado): 404 para que la UI corte el polling.
        abort(404)
    base_dir = None
    with solution_publisher._LOCK:
        entry = solution_publisher._RUNS.get(run_id)
        if entry:
            base_dir = entry.get("base_dir")
    summary = None
    if base_dir:
        try:
            import json as _json

            with open(os.path.join(base_dir, "publish.summary.json"), encoding="utf-8") as fh:
                summary = _json.load(fh)
        except (OSError, ValueError):
            summary = None
    return jsonify({**status, "summary": summary})


@bp.post("/runs/<run_id>/cancel")
def run_cancel_route(run_id: str):
    _guard()
    from services import solution_publisher

    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm requerido"}), 400
    return jsonify({"cancelled": solution_publisher.cancel(run_id)})


@bp.get("/runs/<run_id>/artifact/download")
def run_download_route(run_id: str):
    _guard()
    from services import solution_publisher

    zip_path = solution_publisher.artifact_zip_path(run_id)
    if not zip_path:
        abort(404)
    root = (data_dir() / "solution_publish_artifacts").resolve()
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


@bp.get("/runs")
def runs_route():
    _guard()
    from services import solution_publisher

    slug = (request.args.get("slug") or "").strip() or None
    ws = _workspace() or ""
    return jsonify({"runs": solution_publisher.list_runs(ws, slug, limit=20)})


@bp.get("/runs/<run_id>/assist-context")
def assist_context_route(run_id: str):
    """Plan 215 F6 — arma el contexto (enmascarado) para el chat DevOps del Plan 90.

    La conversación la crea el FRONTEND contra POST /api/devops/agent/conversations:
    acá solo se COMPONE el mensaje (cero duplicación de lanzamiento/clamp/tickets).
    """
    _guard()
    import project_manager
    from services import publish_config_store, solution_publisher

    status = solution_publisher.get_status(run_id)
    if status is None:
        abort(404)
    project = project_manager.get_active_project()
    if not project:
        return jsonify({"error": "sin proyecto activo"}), 400

    ws = _workspace() or ""
    slug = status.get("slug")
    solution = {}
    toolchain = {}
    store, toolchain_mod = _deps_or_none()
    if store is not None:
        solution = next((s for s in store.load_catalog(ws).get("solutions", [])
                         if s.get("slug") == slug), {}) or {}
        toolchain = toolchain_mod.detect_toolchain()
    cfg = publish_config_store.load_config(ws, slug) if slug else {}

    with solution_publisher._LOCK:
        run = dict(solution_publisher._RUNS.get(run_id) or {})
    if not run:
        run = dict(status)

    message = solution_publisher.build_assist_message(run, cfg, solution, toolchain)
    return jsonify({"project": project, "message": message})


@bp.post("/register-deploy-app")
def register_deploy_app_route():
    """Bridge al Centro de Despliegues (Plan 120), espejo del 201 F8."""
    _guard()
    store, _tc = _deps_or_none()
    if store is None:
        return jsonify(_UNAVAILABLE), 200
    from services import deploy_store, solution_publisher

    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm requerido"}), 400
    run_id = body.get("run_id")
    status = solution_publisher.get_status(run_id) if run_id else None
    if not status or status.get("status") != "success":
        return jsonify({"error": "El publish no está terminado con éxito"}), 400

    slug = status.get("slug")
    staging_dir = None
    with solution_publisher._LOCK:
        entry = solution_publisher._RUNS.get(run_id)
        if entry and entry.get("base_dir"):
            staging_dir = os.path.join(entry["base_dir"], "out")
    if not staging_dir or not os.path.isdir(staging_dir):
        return jsonify({"error": "Artefacto no encontrado"}), 400

    # El Centro de Despliegues EXIGE al menos un destino con `install_path`
    # absoluto (deploy_planner.validate_app): inventarlo sería escribir donde el
    # operador no eligió. Se conservan los destinos existentes si la app ya está.
    existente = deploy_store.get_app(slug) or {}
    targets = body.get("targets")
    if not isinstance(targets, dict) or not targets:
        targets = existente.get("targets") or {}
    if not targets:
        return jsonify({
            "error": ("Falta el destino: indicá al menos un 'targets' con "
                      "'install_path' absoluto para esta app."),
        }), 400

    app_payload = {
        "id": slug,
        "name": existente.get("name") or slug,
        "artifact": {"kind": "folder", "path": os.path.abspath(staging_dir)},
        "targets": targets,
    }
    try:
        app = deploy_store.upsert_app(app_payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"app": app})
