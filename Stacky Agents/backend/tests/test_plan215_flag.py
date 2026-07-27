"""Plan 215 F0 — alta de la flag del Publicador de Soluciones + health key.

Flag por INSTANCIA (`config.config`): getattr sobre el MODULO devolveria el
default y mataria el branch OFF.
"""
from __future__ import annotations

_KEY = "STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED"


def test_flag_registered_and_curated():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    spec = next((s for s in FLAG_REGISTRY if s.key == _KEY), None)
    assert spec is not None, "la FlagSpec no esta en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True
    assert _KEY in _CATEGORY_KEYS["devops"]
    assert _KEY in _CURATED_DEFAULTS_ON


def test_plain_help_entry_exists():
    from services.harness_flags_help import PLAIN_HELP

    assert _KEY in PLAIN_HELP, "falta la ayuda llana (6ta pata del cableado)"


def test_config_default_is_on():
    import config as cfg

    assert getattr(cfg.config, _KEY, None) is True


def test_health_exposes_solution_publisher_enabled():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    r = app.test_client().get("/api/devops/health")
    assert r.status_code == 200
    assert "solution_publisher_enabled" in r.get_json()
