"""api/pipeline_inventory.py — Blueprint del inventario vivo de pipelines. Plan 246 F4.

url_prefix="/pipeline-inventory" -> ruta final /api/pipeline-inventory/...
NO poner url_prefix="/api/..." (daria /api/api/...) y NO registrar en app.py:
se registra sobre api_bp en api/__init__.py.
Guard de la flag PER-REQUEST (abort(404)), nunca gateado en el registro.

READ-ONLY: este blueprint no define ningun POST/PUT/PATCH/DELETE. A proposito.
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, abort, jsonify, request

from services.pipeline_inventory import build_inventory

bp = Blueprint("pipeline_inventory", __name__, url_prefix="/pipeline-inventory")


@bp.get("/list")
def list_inventory_route():
    """Inventario completo. SIEMPRE 200 con la flag ON (nunca 500).

    Query params:
      project  (opcional) nombre del proyecto; None => proyecto activo
      refresh  "1"/"true" => saltea el cache TTL (accion explicita del operador)
    """
    # GOTCHA: leer la INSTANCIA (_config.config), no el modulo. getattr del modulo
    # devuelve el default y mata el branch OFF (el test flag-off pasaria en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_INVENTORY_ENABLED", False):
        abort(404)
    project = request.args.get("project") or None
    refresh = (request.args.get("refresh") or "").strip().lower() in ("1", "true", "yes")
    return jsonify(build_inventory(project, refresh=refresh))
