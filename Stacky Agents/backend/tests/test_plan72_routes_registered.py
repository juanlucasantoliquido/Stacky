"""Plan 72 [ADICIÓN ARQUITECTO v3] — Centinela de rutas reales.

Bootea create_app() real y afirma que las rutas CI existen en /api/ci/...
(no en /api/api/ci/... — doble prefijo, C1).

Este test hace imposible el falso-verde de la clase C1: tests que pasan sobre
una app armada a mano mientras producción sirve rutas 404.
"""
from __future__ import annotations


def test_ci_routes_registered_under_api_ci():
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    # Rutas esperadas (con url_prefix=/ci sobre api_bp url_prefix=/api)
    assert "/api/ci/<project>/trigger" in rules, (
        f"Ruta /api/ci/<project>/trigger no registrada. Rutas ci: "
        f"{sorted(r for r in rules if 'ci' in r.lower())}"
    )
    assert "/api/ci/<project>/trigger-preview" in rules, (
        f"Ruta /api/ci/<project>/trigger-preview no registrada."
    )
    assert "/api/ci/<project>/pipeline/<pipeline_id>" in rules, (
        f"Ruta /api/ci/<project>/pipeline/<pipeline_id> no registrada."
    )
    # Anti-regresión: verificar que NO hay doble prefijo
    assert "/api/api/ci/<project>/trigger" not in rules, (
        "DOBLE PREFIJO detectado: /api/api/ci — blueprint mal registrado (C1)"
    )
