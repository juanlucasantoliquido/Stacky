"""tests/test_plan159_model_catalog_endpoint.py — Plan 159 v2 F1.

Endpoint GET /api/agents/model-catalog: siempre 200, introspección copilot
cacheada (C3), nunca deja el selector vacío. Fixture autouse resetea los
cachés módulo-level (sin ella el caché copilot contamina entre casos).
"""
import pytest

from services import model_catalog


@pytest.fixture(autouse=True)
def _reset_catalog_caches():
    model_catalog._cache.update(data=None, loaded_at=0.0, mtime=None)
    model_catalog._copilot_cache.update(models=None, loaded_at=0.0, error=None)
    yield


@pytest.fixture(scope="module")
def app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_endpoint_returns_200_and_claude_models(client):
    resp = client.get("/api/agents/model-catalog")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    ids = {m["id"] for m in data["runtimes"]["claude_code_cli"]["models"]}
    assert "claude-sonnet-5" in ids


def test_endpoint_includes_codex_note(client):
    resp = client.get("/api/agents/model-catalog")
    data = resp.get_json()
    codex = data["runtimes"]["codex_cli"]
    assert codex["efforts"] == []
    assert codex.get("note", "").strip()


def test_endpoint_copilot_models_from_live_introspection(client, monkeypatch):
    import copilot_bridge
    monkeypatch.setattr(
        copilot_bridge, "list_copilot_models",
        lambda timeout_sec=5: [{"id": "gpt-a", "name": "GPT A"}, {"id": "gpt-b", "name": "GPT B"}],
    )
    resp = client.get("/api/agents/model-catalog")
    data = resp.get_json()
    ids = {m["id"] for m in data["runtimes"]["github_copilot"]["models"]}
    assert {"gpt-a", "gpt-b"} <= ids


def test_endpoint_copilot_failure_degrades_not_500(client, monkeypatch):
    import copilot_bridge

    def boom(timeout_sec=5):
        raise RuntimeError("red caída")

    monkeypatch.setattr(copilot_bridge, "list_copilot_models", boom)
    resp = client.get("/api/agents/model-catalog")
    assert resp.status_code == 200  # nunca 500
    data = resp.get_json()
    assert data["runtimes"]["github_copilot"]["error"] is not None
    assert data["runtimes"]["github_copilot"]["models"] == []


def test_endpoint_disabled_flag_returns_ok_false(client, monkeypatch):
    # C9: monkeypatch SOBRE LA INSTANCIA, nunca el módulo.
    from config import config as config_instance
    monkeypatch.setattr(config_instance, "STACKY_MODEL_CATALOG_ENABLED", False, raising=False)
    resp = client.get("/api/agents/model-catalog")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert data["reason"] == "catalog_disabled"
