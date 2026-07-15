"""Plan 139 F0 — flag del shell v2 + lectura por /api/diag/health."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import importlib

import pytest


def test_flag_registered_and_categorized():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS, categorize
    keys = {s.key for s in FLAG_REGISTRY}
    assert "STACKY_UI_SHELL_V2_ENABLED" in keys
    assert "STACKY_UI_SHELL_V2_ENABLED" in _CATEGORY_KEYS["interfaz_ui"]
    assert categorize("STACKY_UI_SHELL_V2_ENABLED") == "interfaz_ui"


def test_flag_default_off_and_not_curated():
    from services.harness_flags import FLAG_REGISTRY, declared_default, default_is_known
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_UI_SHELL_V2_ENABLED")
    assert declared_default(spec) is False          # type-zero (sin default explícito)
    assert default_is_known(spec) is False           # NO curada


def test_plain_help_present():
    from services.harness_flags_help import PLAIN_HELP
    assert "STACKY_UI_SHELL_V2_ENABLED" in PLAIN_HELP


def test_config_default_off():
    import config
    importlib.reload(config)
    assert config.config.STACKY_UI_SHELL_V2_ENABLED is False


@pytest.fixture
def client():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_diag_health_exposes_shell_flag_default_off(client):
    r = client.get("/api/diag/health")
    assert r.status_code == 200
    assert r.get_json()["shell_v2_enabled"] is False


def test_diag_health_reflects_flag_on(client, monkeypatch):
    import config
    monkeypatch.setattr(config.config, "STACKY_UI_SHELL_V2_ENABLED", True, raising=False)
    r = client.get("/api/diag/health")
    assert r.get_json()["shell_v2_enabled"] is True
