"""Plan 131 — Resolutor de incidencias multimodal."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("incidents", __name__, url_prefix="/incidents")


@bp.get("/status")
def incidents_status():
    from config import config as _cfg
    from services.incident_store import ALLOWED_EXTENSIONS, MAX_FILES, MAX_FILE_BYTES
    return jsonify({
        "enabled": bool(_cfg.STACKY_INCIDENT_RESOLVER_ENABLED),
        "max_files": MAX_FILES,
        "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
    })
