"""tests/test_plan131_incident_flag.py — Plan 131 F0.

Alta de la flag STACKY_INCIDENT_RESOLVER_ENABLED (editable por UI, default OFF)
y del endpoint GET /api/incidents/status (siempre 200, gate ausente).
Patrón de fixture app/client: tests/test_plan109_flag.py.
"""
import pytest


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("STACKY_INCIDENT_RESOLVER_ENABLED", raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_INCIDENT_RESOLVER_ENABLED is False
    importlib.reload(config)  # restaurar estado de import normal para el resto de la suite


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_INCIDENT_RESOLVER_ENABLED", False)
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = original


@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_INCIDENT_RESOLVER_ENABLED", False)
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = original


def test_status_responds_200_with_enabled_false_when_off(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.get("/api/incidents/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is False
    assert data["max_files"] == 10
    assert data["max_file_mb"] == 10
    assert ".png" in data["allowed_extensions"]


def test_status_responds_enabled_true_when_on(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/incidents/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is True


def test_flagspec_registered():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    spec = next((s for s in FLAG_REGISTRY if s.key == "STACKY_INCIDENT_RESOLVER_ENABLED"), None)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.env_only is False
    # Guardarraíl §3.7: sin default= declarado (curación via _CURATED_DEFAULTS_ON
    # es solo para flags default ON; esta flag es default OFF, no curada).
    assert spec.default is None
    # Centinela test_every_registry_flag_is_categorized exige bijección completa.
    assert "STACKY_INCIDENT_RESOLVER_ENABLED" in _CATEGORY_KEYS["capacidades_optin"]


def test_plain_help_entry():
    from services.harness_flags_help import PLAIN_HELP
    entry = PLAIN_HELP.get("STACKY_INCIDENT_RESOLVER_ENABLED")
    assert entry is not None
    assert entry.what.strip()
    assert entry.on_effect.strip()
    assert entry.off_effect.strip()
    assert entry.example.strip()
