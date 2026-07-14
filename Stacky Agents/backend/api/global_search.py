"""Plan 129 — Paleta global: búsqueda profunda multi-fuente.

GET /api/search/health  — siempre 200, reporta si la flag está ON.
GET /api/search/global  — 404 si la flag está OFF; búsqueda determinista sobre
                           tickets, ejecuciones, documentos, servidores DevOps y
                           flags del arnés. (Agregado en F2.)
"""
from flask import Blueprint, jsonify

from config import config

bp = Blueprint("global_search", __name__, url_prefix="/search")


def _enabled() -> bool:
    return bool(getattr(config, "STACKY_PALETTE_DEEP_SEARCH_ENABLED", False))


@bp.get("/health")
def search_health():
    return jsonify({"ok": True, "flag_enabled": _enabled()})
