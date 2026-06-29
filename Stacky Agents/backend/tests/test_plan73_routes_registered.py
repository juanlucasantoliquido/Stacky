"""Test centinela de rutas reales Plan 73 (ADICIÓN ARQUITECTO v2, C2).
Verifica que las rutas /api/pipeline-generator/... están registradas en create_app()
bajo el prefijo CORRECTO — hace imposible el falso-verde de doble prefijo /api/api/....
"""


def test_pipeline_generator_routes_registered_under_api():
    """Rutas /api/pipeline-generator/... presentes en el url_map de create_app()."""
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/pipeline-generator/preview" in rules, (
        f"Ruta /api/pipeline-generator/preview no registrada. "
        f"Rutas de pipeline-generator: {[r for r in rules if 'pipeline' in r.lower()]}"
    )
    assert "/api/pipeline-generator/commit" in rules, (
        f"Ruta /api/pipeline-generator/commit no registrada. "
        f"Rutas de pipeline-generator: {[r for r in rules if 'pipeline' in r.lower()]}"
    )
