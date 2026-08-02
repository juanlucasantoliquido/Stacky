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
      project   (opcional) nombre del proyecto; None => proyecto activo
      refresh   "1"/"true" => saltea el cache TTL (accion explicita del operador)
      describe  "1"/"true" => suma la ficha en castellano a cada entrada
                (Plan 294 F10). SIN el parametro la respuesta es byte-identica
                a la de siempre: las 12 claves de make_entry y nada mas.
    """
    # GOTCHA: leer la INSTANCIA (_config.config), no el modulo. getattr del modulo
    # devuelve el default y mata el branch OFF (el test flag-off pasaria en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_INVENTORY_ENABLED", False):
        abort(404)
    project = request.args.get("project") or None
    refresh = (request.args.get("refresh") or "").strip().lower() in ("1", "true", "yes")
    describe = (request.args.get("describe") or "").strip().lower() in ("1", "true", "yes")
    # R10 — sin `?describe`, la LLAMADA es byte-identica a la de siempre: no se
    # manda el kwarg. No es cosmetica: hay dobles vivos cuya firma sigue siendo
    # (project, refresh=False), y mandarles un kwarg desconocido los rompe con
    # 500 (medido: rompia 3 casos de test_plan246_inventory_endpoint.py).
    if not describe:
        return jsonify(build_inventory(project, refresh=refresh))
    return jsonify(build_inventory(project, refresh=refresh, describe=True))
