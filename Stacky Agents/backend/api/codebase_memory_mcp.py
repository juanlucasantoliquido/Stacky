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
    from config import config as cfg
    st = mcp_installation_status()
    guides = {runtime: build_installation_guide(runtime) for runtime in ("claude_code", "codex", "copilot_pro")}
    # Plan 80 F6 — estado real de wiring (aditivo; no rompe las 5 claves del Plan 76).
    binary_path_set = bool(cfg.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH.strip())
    injects_external = st.get("enabled", False) and binary_path_set
    wiring = {"binary_path_set": binary_path_set, "injects_external": injects_external}
    return jsonify({**st, "guides": guides, "wiring": wiring})


@bp.get("/savings")
def savings_route():
    """GET /api/codebase-memory-mcp/savings — métricas agregadas de ahorro estimado.
    Siempre 200. Retorna samples=0 hasta que el operador corra la PoC (Plan 80 F5)."""
    from services.codebase_memory_mcp_wiring import aggregate_savings
    return jsonify(aggregate_savings())
