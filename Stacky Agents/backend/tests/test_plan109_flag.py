"""tests/test_plan109_flag.py — Plan 109 F0.

Alta de la flag STACKY_DOCS_GRAPH_ENABLED (editable por UI, default OFF) y su
exposición como key aditiva `graph_enabled` en GET /api/docs/sources.
Patrón de fixture app/client: test_plan89_environments_endpoints.py.
"""
import pytest


def test_flag_registered_in_contexto_memoria():
    from services.harness_flags import _CATEGORY_KEYS
    assert "STACKY_DOCS_GRAPH_ENABLED" in _CATEGORY_KEYS["contexto_memoria"]


def test_flag_default_off():
    from config import config
    assert config.STACKY_DOCS_GRAPH_ENABLED is False


def test_flag_spec_no_declared_default_and_no_requires():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_DOCS_GRAPH_ENABLED")
    assert spec.default is None
    assert spec.requires is None
    assert spec.env_only is False


def test_flag_has_plain_help():
    from services.harness_flags_help import PLAIN_HELP
    assert "STACKY_DOCS_GRAPH_ENABLED" in PLAIN_HELP


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DOCS_GRAPH_ENABLED", False)
    cfg.config.STACKY_DOCS_GRAPH_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DOCS_GRAPH_ENABLED = original


def test_sources_endpoint_exposes_graph_enabled(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.get("/api/docs/sources")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "graph_enabled" in data
    assert isinstance(data["graph_enabled"], bool)
    assert data["graph_enabled"] is False
