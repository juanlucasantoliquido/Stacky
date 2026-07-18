"""tests/test_plan159_model_catalog_flag.py — Plan 159 v2 F2.

Alta de la flag STACKY_MODEL_CATALOG_ENABLED (default ON, categoría
runtimes_cli, editable por UI). Patrón: tests/test_plan131_incident_flag.py.
Fixture autouse resetea cachés módulo-level del catálogo (C11b).
"""
import pytest

from services import model_catalog


@pytest.fixture(autouse=True)
def _reset_catalog_caches():
    model_catalog._cache.update(data=None, loaded_at=0.0, mtime=None)
    model_catalog._copilot_cache.update(models=None, loaded_at=0.0, error=None)
    yield


def test_flag_default_on(monkeypatch):
    monkeypatch.delenv("STACKY_MODEL_CATALOG_ENABLED", raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_MODEL_CATALOG_ENABLED is True
    importlib.reload(config)  # restaurar import normal para el resto de la suite


def test_flagspec_registered():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    spec = next((s for s in FLAG_REGISTRY if s.key == "STACKY_MODEL_CATALOG_ENABLED"), None)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.env_only is False
    assert spec.default is True
    assert "STACKY_MODEL_CATALOG_ENABLED" in _CATEGORY_KEYS["runtimes_cli"]


def test_plain_help_entry():
    from services.harness_flags_help import PLAIN_HELP
    entry = PLAIN_HELP.get("STACKY_MODEL_CATALOG_ENABLED")
    assert entry is not None
    assert entry.what.strip()
    assert entry.on_effect.strip()
    assert entry.off_effect.strip()
    assert entry.example.strip()


def test_endpoint_returns_ok_false_when_flag_off(monkeypatch):
    # C9: monkeypatch sobre la INSTANCIA config.config, raising=False.
    from app import create_app
    from config import config as config_instance
    monkeypatch.setattr(config_instance, "STACKY_MODEL_CATALOG_ENABLED", False, raising=False)
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get("/api/agents/model-catalog")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert data["reason"] == "catalog_disabled"
