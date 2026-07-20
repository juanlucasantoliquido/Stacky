"""api/db_compare_masking.py — Plan 181 F4: prefs de masking por columna del
data-diff (blueprint propio para no engordar api/db_compare.py, patrón 178/180).

url_prefix="/db-compare" → rutas finales /api/db-compare/masking/...

Gate doble: STACKY_DB_COMPARE_ENABLED (master 122) + STACKY_DB_COMPARE_MASKING_ENABLED
(181). Solo prefs (GET estado + POST override); las respuestas del run se
enmascaran en api/db_compare.py:get_run_route (F3), no acá.
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, jsonify, request

from services import dbcompare_masking

bp = Blueprint("db_compare_masking", __name__, url_prefix="/db-compare")


def _require_masking_enabled():
    # Idioma api/db_compare.py:27-29 — instancia de flags = config.config.
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    if not getattr(_config.config, "STACKY_DB_COMPARE_MASKING_ENABLED", False):
        return jsonify({"ok": False, "error": "Masking deshabilitado (STACKY_DB_COMPARE_MASKING_ENABLED)."}), 403
    return None


@bp.get("/masking/prefs")
def get_masking_prefs_route():
    gate = _require_masking_enabled()
    if gate:
        return gate
    return jsonify({"ok": True, "prefs": dbcompare_masking.load_prefs()})


@bp.post("/masking/prefs")
def post_masking_override_route():
    gate = _require_masking_enabled()
    if gate:
        return gate
    data = request.get_json(silent=True) or {}
    schema = (data.get("schema") or "").strip()
    table = (data.get("table") or "").strip()
    column = (data.get("column") or "").strip()
    state = (data.get("state") or "").strip()
    if not schema or not table or not column or not state:
        return jsonify({"ok": False, "error": "faltan campos: schema, table, column, state."}), 400
    try:
        prefs = dbcompare_masking.set_override(schema, table, column, state)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "prefs": prefs})
