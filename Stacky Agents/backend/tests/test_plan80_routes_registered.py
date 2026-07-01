"""Plan 80 F7 — Centinela de rutas reales para /savings.

Réplica del patrón de test_plan76_routes_registered.py.

Casos:
  1. /api/codebase-memory-mcp/savings está registrada.
  2. /api/api/codebase-memory-mcp/savings (doble prefijo) NO existe.
  3. /api/codebase-memory-mcp/status (del 76) sigue viva (co-existencia).
"""
from __future__ import annotations


def test_savings_route_registered_under_api():
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/codebase-memory-mcp/savings" in rules, (
        f"Ruta /api/codebase-memory-mcp/savings no registrada. "
        f"Rutas codebase: {sorted(r for r in rules if 'codebase' in r.lower())}"
    )


def test_no_double_prefix_savings():
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/api/codebase-memory-mcp/savings" not in rules, (
        "DOBLE PREFIJO detectado: /api/api/codebase-memory-mcp/savings — "
        "blueprint mal registrado. Verificar que la ruta se agregó al bp existente "
        "en api/codebase_memory_mcp.py, NO un blueprint nuevo ni app.py."
    )


def test_status_route_still_alive():
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/codebase-memory-mcp/status" in rules
