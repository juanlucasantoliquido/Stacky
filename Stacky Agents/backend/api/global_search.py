"""Plan 129 — Paleta global: búsqueda profunda multi-fuente.

GET /api/search/health  — siempre 200, reporta si la flag está ON.
GET /api/search/global  — 404 si la flag está OFF; búsqueda determinista sobre
                           tickets, ejecuciones, documentos, servidores DevOps y
                           flags del arnés.
"""
from flask import Blueprint, jsonify, request

from config import config

bp = Blueprint("global_search", __name__, url_prefix="/search")


def _enabled() -> bool:
    return bool(getattr(config, "STACKY_PALETTE_DEEP_SEARCH_ENABLED", False))


@bp.get("/health")
def search_health():
    return jsonify({"ok": True, "flag_enabled": _enabled()})


@bp.get("/global")
def search_global():
    if not _enabled():
        return jsonify({"ok": False, "error": "palette_deep_search_disabled"}), 404
    from services import global_search as gs

    q = (request.args.get("q") or "").strip()
    if len(q) > gs.MAX_QUERY_LEN:
        return jsonify({"ok": False, "error": "query_too_long"}), 400
    try:
        limit = int(request.args.get("limit", gs.DEFAULT_LIMIT))
    except ValueError:
        limit = gs.DEFAULT_LIMIT
    return jsonify(gs.search_all(q, limit_per_source=limit))
