"""Plan 74 F11 bis — Centinela de rutas: /api/migrator/* con un solo prefijo /api.

3 casos (igual que test_plan72_routes_registered.py pero para el migrador).
Garantiza que no hay doble prefijo /api/api/migrator/... (C1).
"""
from __future__ import annotations

import re


def _app_rules():
    from app import create_app
    app = create_app()
    return {r.rule for r in app.url_map.iter_rules()}


def test_migrator_health_route_registrada():
    """/api/migrator/health registrada con un solo /api."""
    rules = _app_rules()
    assert "/api/migrator/health" in rules, (
        f"Ruta /api/migrator/health no registrada. "
        f"Rutas migrator: {sorted(r for r in rules if 'migrator' in r.lower())}"
    )


def test_no_doble_prefijo_migrator():
    """No existe ninguna ruta del migrador con doble prefijo /api/api/migrator/... (gate C1)."""
    rules = _app_rules()
    migrator_double = [r for r in rules if re.match(r"^/api/api/migrator/", r)]
    assert not migrator_double, (
        f"DOBLE PREFIJO detectado en migrador — blueprint mal registrado (C1): {migrator_double}"
    )
    # Verificar que la ruta correcta existe (un solo /api)
    migrator_rules = [r for r in rules if "/migrator/" in r]
    assert any("/api/migrator/" in r for r in migrator_rules), (
        f"Ninguna ruta /api/migrator/* encontrada. Rutas migrator: {migrator_rules}"
    )


def test_migrator_blueprint_registrado():
    """migrator_bp está registrado bajo api_bp (nombre: 'api.migrator' en blueprints)."""
    from app import create_app
    app = create_app()
    blueprint_names = set(app.blueprints.keys())
    assert "api.migrator" in blueprint_names, (
        f"Blueprint 'api.migrator' no registrado. Blueprints: {sorted(blueprint_names)}"
    )
