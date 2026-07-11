"""tests/test_plan98_profile_key_patch.py — Plan 98 F2, endpoint
PATCH /api/projects/<name>/client-profile/keys/<key> (merge server-side bajo lock).
Mismo fixture que test_plan88_presets_validation.py."""
import json

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fixture que redirige PROJECTS_DIR / projects_dir a `tmp_path` y activa la flag."""
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

    for name, tracker_type in [("RSPACIFICO", "azure_devops")]:
        pdir = projects_dir / name
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "config.json").write_text(json.dumps({
            "name": name,
            "display_name": name,
            "issue_tracker": {"type": tracker_type},
        }, indent=2), encoding="utf-8")

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture()
def client_flag_off(client, monkeypatch):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False)
    return client


def _patch(client, project, key, value):
    return client.patch(
        f"/api/projects/{project}/client-profile/keys/{key}",
        json={"value": value},
    )


def _valid_draft(**overrides):
    d = {"name": "d1", "spec": {"steps": []}}
    d.update(overrides)
    return d


def _valid_preset(**overrides):
    p = {"name": "p1", "mode": "todo", "groups": []}
    p.update(overrides)
    return p


def test_patch_404_when_flag_off(client_flag_off):
    resp = _patch(client_flag_off, "RSPACIFICO", "devops_pipeline_drafts", [])
    assert resp.status_code == 404


def test_patch_404_unknown_project(client):
    resp = _patch(client, "NOEXISTE", "devops_pipeline_drafts", [])
    assert resp.status_code == 404


def test_patch_400_key_not_in_allowlist(client):
    resp = _patch(client, "RSPACIFICO", "language", "csharp")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "key_not_patchable"
    assert body["allowed"] == sorted([
        "devops_pipeline_drafts",
        "devops_publication_presets",
        "devops_publication_settings",
        "devops_environment_settings",
    ])


def test_patch_400_missing_value(client):
    resp = client.patch(
        "/api/projects/RSPACIFICO/client-profile/keys/devops_pipeline_drafts",
        json={},
    )
    assert resp.status_code == 400


def test_patch_400_invalid_value_same_error_as_put(client):
    patch_resp = _patch(client, "RSPACIFICO", "devops_pipeline_drafts", "no-lista")
    put_resp = client.put(
        "/api/projects/RSPACIFICO/client-profile",
        json={"profile": {"devops_pipeline_drafts": "no-lista"}},
    )
    assert patch_resp.status_code == put_resp.status_code == 400
    assert patch_resp.get_json()["error"] == put_resp.get_json()["error"]


def test_patch_preserves_other_keys(client):
    seed = client.put(
        "/api/projects/RSPACIFICO/client-profile",
        json={"profile": {
            "devops_publication_presets": [_valid_preset(name="keepme")],
            "devops_pipeline_drafts": [_valid_draft(name="old")],
        }},
    )
    assert seed.status_code == 200

    resp = _patch(client, "RSPACIFICO", "devops_pipeline_drafts", [_valid_draft(name="new")])
    assert resp.status_code == 200

    get_resp = client.get("/api/projects/RSPACIFICO/client-profile")
    profile = get_resp.get_json()["profile"]
    assert profile["devops_publication_presets"] == [_valid_preset(name="keepme")]
    assert profile["devops_pipeline_drafts"] == [_valid_draft(name="new")]


def test_patch_creates_profile_when_absent(client):
    resp = _patch(client, "RSPACIFICO", "devops_pipeline_drafts", [_valid_draft()])
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["value"] == [_valid_draft()]

    get_resp = client.get("/api/projects/RSPACIFICO/client-profile")
    assert get_resp.get_json()["profile"]["devops_pipeline_drafts"] == [_valid_draft()]


def test_patch_null_deletes_key(client):
    seed = client.put(
        "/api/projects/RSPACIFICO/client-profile",
        json={"profile": {"devops_pipeline_drafts": [_valid_draft()]}},
    )
    assert seed.status_code == 200

    resp = _patch(client, "RSPACIFICO", "devops_pipeline_drafts", None)
    assert resp.status_code == 200
    assert resp.get_json()["value"] is None

    get_resp = client.get("/api/projects/RSPACIFICO/client-profile")
    profile = get_resp.get_json()["profile"]
    assert "devops_pipeline_drafts" not in profile


def test_patch_records_event(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.client_profile.record_event",
        lambda **kwargs: calls.append(kwargs),
    )
    resp = _patch(client, "RSPACIFICO", "devops_pipeline_drafts", [_valid_draft()])
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0]["action"] == "client_profile_key_patch"
    assert calls[0]["detail"]["key"] == "devops_pipeline_drafts"
