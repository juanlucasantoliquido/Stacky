"""tests/test_plan98_bootstrap_endpoint.py — Plan 98 F3,
GET /api/devops/bootstrap?project=X (hidratación en un round-trip)."""
import json

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    from app import create_app
    import project_manager
    import services.client_profile as cp
    import api.client_profile as api_cp
    import config as _config

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects_dir)
    monkeypatch.setattr(api_cp, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", True)

    pdir = projects_dir / "RSPACIFICO"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "config.json").write_text(json.dumps({
        "name": "RSPACIFICO",
        "display_name": "RSPACIFICO",
        "issue_tracker": {"type": "azure_devops"},
    }, indent=2), encoding="utf-8")

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture()
def client_flag_off(client, monkeypatch):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False)
    return client


def test_bootstrap_404_when_flag_off(client_flag_off):
    resp = client_flag_off.get("/api/devops/bootstrap?project=RSPACIFICO")
    assert resp.status_code == 404


def test_bootstrap_400_without_project(client):
    resp = client.get("/api/devops/bootstrap")
    assert resp.status_code == 400


def test_bootstrap_shape_with_profile(client):
    profile = {
        "devops_pipeline_drafts": [{"name": "d1", "spec": {"steps": []}}],
        "devops_publication_presets": [{"name": "p1", "mode": "todo", "groups": []}],
        "devops_publication_settings": {"step_templates": {"entry": "echo x"}},
        "devops_environment_settings": {"environment_root": "C:/env"},
        "process_catalog": [{"name": "P1", "kind": "entry"}],
    }
    seed = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert seed.status_code == 200

    resp = client.get("/api/devops/bootstrap?project=RSPACIFICO")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["has_profile"] is True
    assert body["profile_keys"]["devops_pipeline_drafts"] == profile["devops_pipeline_drafts"]
    assert body["profile_keys"]["devops_publication_presets"] == profile["devops_publication_presets"]
    assert body["profile_keys"]["devops_publication_settings"] == profile["devops_publication_settings"]
    assert body["profile_keys"]["devops_environment_settings"] == profile["devops_environment_settings"]
    assert body["profile_keys"]["process_catalog"] == profile["process_catalog"]


def test_bootstrap_empty_profile_defaults(client):
    resp = client.get("/api/devops/bootstrap?project=RSPACIFICO")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["has_profile"] is False
    assert body["profile_keys"]["devops_pipeline_drafts"] == []
    assert body["profile_keys"]["devops_publication_presets"] == []
    assert body["profile_keys"]["devops_publication_settings"] == {}
    assert body["profile_keys"]["devops_environment_settings"] is None
    assert body["profile_keys"]["process_catalog"] == []


def test_bootstrap_health_matches_health_endpoint(client):
    bootstrap_resp = client.get("/api/devops/bootstrap?project=RSPACIFICO")
    health_resp = client.get("/api/devops/health")
    assert bootstrap_resp.status_code == health_resp.status_code == 200
    assert bootstrap_resp.get_json()["health"] == health_resp.get_json()


def test_bootstrap_servers_only_when_enabled(client, monkeypatch):
    import config as _config

    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", False)
    resp_off = client.get("/api/devops/bootstrap?project=RSPACIFICO")
    assert resp_off.get_json()["servers"] is None

    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True)
    monkeypatch.setattr(
        "api.devops.server_registry.list_servers",
        lambda: [{"alias": "srv1"}],
    )
    resp_on = client.get("/api/devops/bootstrap?project=RSPACIFICO")
    body = resp_on.get_json()
    assert body["servers"]["servers"] == [{"alias": "srv1"}]
    assert "keyring_available" in body["servers"]


def test_bootstrap_corrupt_keys_normalized(client, monkeypatch):
    monkeypatch.setattr(
        "api.devops.load_client_profile",
        lambda project: {"devops_pipeline_drafts": "basura"},
    )
    resp = client.get("/api/devops/bootstrap?project=RSPACIFICO")
    assert resp.status_code == 200
    assert resp.get_json()["profile_keys"]["devops_pipeline_drafts"] == []
