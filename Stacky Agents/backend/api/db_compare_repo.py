"""Plan 180 — API del puente diff->repo. Blueprint SEPARADO de api/db_compare.py
(que toca el plan 176) para colision de merge cero. Mismo url_prefix, nombre
distinto: Flask lo admite; las rutas no se pisan (tabla verificada
api/db_compare.py — /repo-scripts y /runs/<run_id>/repo-coverage libres).

Gate doble: master 122 (STACKY_DB_COMPARE_ENABLED) + puente 180
(STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED). OFF (cualquiera) => 403 en TODO.
HITL absoluto: estas rutas SOLO informan (indice read-only + cobertura); nunca
excluyen items del diff, nunca editan/ejecutan scripts, nunca escriben bajo el
workspace (unica escritura: data_dir()/db_compare/repo_scripts/index.json).
"""
from flask import Blueprint, jsonify

import config as _config
import runtime_paths
from services import dbcompare_repo_scripts, dbcompare_runs

bp = Blueprint("db_compare_repo", __name__, url_prefix="/db-compare")


def _require_bridge_enabled():
    # Idioma de api/db_compare.py — la instancia de flags es config.config,
    # NO el modulo (gotcha: getattr(config, FLAG) da el default y mata el OFF).
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    if not getattr(_config.config, "STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED", False):
        return jsonify({"ok": False, "error": "Puente al repo deshabilitado (STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED)."}), 403
    return None


@bp.get("/repo-scripts")
def get_repo_scripts_route():
    gate = _require_bridge_enabled()
    if gate is not None:
        return gate
    workspace = runtime_paths._active_workspace_root()
    if workspace is None:
        return jsonify({"ok": True, "index": None, "workspace": None})
    index = dbcompare_repo_scripts.load_index_for(workspace)  # fix C4: solo el indice del workspace activo
    if index is None:
        index = dbcompare_repo_scripts.build_index()  # auto-escaneo primera vez o proyecto recien cambiado
    return jsonify({"ok": True, "index": index, "workspace": str(workspace)})


@bp.post("/repo-scripts/refresh")
def refresh_repo_scripts_route():
    gate = _require_bridge_enabled()
    if gate is not None:
        return gate
    index = dbcompare_repo_scripts.build_index()  # escaneo forzado
    if index is None:
        return jsonify({"ok": True, "index": None, "workspace": None})
    return jsonify({"ok": True, "index": index})


@bp.get("/runs/<run_id>/repo-coverage")
def run_repo_coverage_route(run_id):
    gate = _require_bridge_enabled()
    if gate is not None:
        return gate
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": "run desconocido"}), 404
    if run.get("diff") is None:
        return jsonify({"ok": False, "error": "la corrida no tiene diff (status != done)"}), 409
    workspace = runtime_paths._active_workspace_root()
    if workspace is None:
        return jsonify({"ok": True, "coverage": None, "workspace": None})
    index = dbcompare_repo_scripts.load_index_for(workspace)  # fix C4
    if index is None:
        index = dbcompare_repo_scripts.build_index()  # auto-escaneo como en GET
    if index is None:
        return jsonify({"ok": True, "coverage": None, "workspace": str(workspace)})
    coverage = dbcompare_repo_scripts.match_diff_items(run["diff"], index)
    return jsonify({"ok": True, "coverage": coverage, "workspace": str(workspace)})
