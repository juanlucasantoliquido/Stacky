"""Plan 76 [C1, ADICIÓN ARQUITECTO v3] — Centinela de rutas reales.

Bootea create_app() real y afirma que la ruta codebase-memory-mcp/status
existe bajo /api/... (no bajo /api/api/...).

Réplica del patrón de test_plan72_routes_registered.py.
"""
from __future__ import annotations


def test_status_route_registered_under_api():
    """La ruta /api/codebase-memory-mcp/status debe estar registrada."""
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/codebase-memory-mcp/status" in rules, (
        f"Ruta /api/codebase-memory-mcp/status no registrada. "
        f"Rutas codebase: {sorted(r for r in rules if 'codebase' in r.lower())}"
    )


def test_no_double_prefix():
    """Anti-regresión doble-prefijo C1: /api/api/... NO debe existir."""
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/api/codebase-memory-mcp/status" not in rules, (
        "DOBLE PREFIJO detectado: /api/api/codebase-memory-mcp — "
        "blueprint mal registrado (C1). Verificar que el registro se hace en "
        "api/__init__.py vía api_bp.register_blueprint, NO en app.py."
    )
