"""Plan 76 — Blueprint para estado de integración codebase-memory-mcp.

Ruta final: GET /api/codebase-memory-mcp/status
  (api_bp monta /api; este blueprint url_prefix="/codebase-memory-mcp")

NUNCA registrar en app.py ni usar url_prefix="/api/..." — causa doble prefijo (C1).
"""
from __future__ import annotations

from flask import Blueprint, jsonify

bp = Blueprint("codebase_memory_mcp", __name__, url_prefix="/codebase-memory-mcp")


@bp.get("/status")
def status_route():
    """GET /api/codebase-memory-mcp/status

    Retorna el estado de la integración opcional + guías de instalación por runtime.
    La respuesta es siempre 200 (el flag puede estar OFF).

    Response JSON:
        enabled (bool): si el flag está ON
        installed_hint (str): guía de next-step para el operador
        flag (str): nombre de la env var
        external_repo (str): URL del repo
        guides (dict): markdown de instalación por runtime
    """
    from services.codebase_memory_mcp_status import mcp_installation_status, build_installation_guide
    st = mcp_installation_status()
    guides = {runtime: build_installation_guide(runtime) for runtime in ("claude_code", "codex", "copilot_pro")}
    return jsonify({**st, "guides": guides})
