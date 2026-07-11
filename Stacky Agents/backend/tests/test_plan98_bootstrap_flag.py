"""tests/test_plan98_bootstrap_flag.py — Plan 98 F0, flag STACKY_DEVOPS_BOOTSTRAP_ENABLED
(5 patas) + key aditiva bootstrap_enabled en /api/devops/health."""
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

_KEY = "STACKY_DEVOPS_BOOTSTRAP_ENABLED"


def _spec():
    return next((s for s in FLAG_REGISTRY if s.key == _KEY), None)


def test_flag_registered_bool():
    spec = _spec()
    assert spec is not None
    assert spec.type == "bool"
    assert spec.env_only is False


def test_flag_categorized_devops():
    assert _KEY in _CATEGORY_KEYS["devops"]


def test_flag_requires_panel():
    spec = _spec()
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_default_on_effective(monkeypatch):
    """Default ON desde 2026-07-09 (activación explícita del operador)."""
    monkeypatch.delenv(_KEY, raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_DEVOPS_BOOTSTRAP_ENABLED is True


def test_health_exposes_bootstrap_enabled_false_by_default():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False)
    cfg.config.STACKY_DEVOPS_BOOTSTRAP_ENABLED = False
    try:
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        resp = client.get("/api/devops/health")
        assert resp.status_code == 200
        assert resp.get_json()["bootstrap_enabled"] is False
    finally:
        cfg.config.STACKY_DEVOPS_BOOTSTRAP_ENABLED = original
