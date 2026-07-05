"""tests/test_plan89_env_settings_validation.py — F3 tests (validación aditiva
de devops_environment_settings en put_client_profile). Mismo fixture que
test_plan88_presets_validation.py / test_plan87_drafts_validation.py."""
import json

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fixture que redirige PROJECTS_DIR / projects_dir a `tmp_path`."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    from app import create_app
    import project_manager
    import services.client_profile as cp
    import api.client_profile as api_cp

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects_dir)
    monkeypatch.setattr(api_cp, "PROJECTS_DIR", projects_dir)

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


def _put(client, profile):
    return client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})


def test_f3_absent_key_noop(client):
    resp = _put(client, {"schema_version": 1, "language": {"primary": "csharp"}})
    assert resp.status_code == 200


def test_f3_root_relative_400(client):
    resp = _put(client, {"devops_environment_settings": {"environment_root": "relativo/x"}})
    assert resp.status_code == 400


def test_f3_root_drive_root_400(client):
    resp = _put(client, {"devops_environment_settings": {"environment_root": "C:\\"}})
    assert resp.status_code == 400


def test_f3_layout_bad_key_400(client):
    resp = _put(client, {"devops_environment_settings": {"folder_layout": {"badkey": ["x"]}}})
    assert resp.status_code == 400


def test_f3_layout_traversal_segment_400(client):
    resp = _put(client, {"devops_environment_settings": {"folder_layout": {"entry": ["../x"]}}})
    assert resp.status_code == 400


def test_f3_pps_not_bool_400(client):
    resp = _put(client, {"devops_environment_settings": {"per_process_subfolder": "si"}})
    assert resp.status_code == 400


def test_f3_layout_windows_invalid_char_400(client):
    resp = _put(client, {"devops_environment_settings": {"folder_layout": {"entry": ["IN|X"]}}})
    assert resp.status_code == 400


def test_f3_layout_reserved_name_400(client):
    resp = _put(client, {"devops_environment_settings": {"folder_layout": {"entry": ["CON"]}}})
    assert resp.status_code == 400


def test_f3_valid_roundtrip(client, tmp_path):
    root = str(tmp_path / "ambiente")
    settings = {
        "environment_root": root,
        "folder_layout": {"entry": ["IN_"], "processing": ["productivas"], "output": ["salida"], "default": []},
        "per_process_subfolder": False,
    }
    resp = _put(client, {"devops_environment_settings": settings})
    assert resp.status_code == 200
    get_resp = client.get("/api/projects/RSPACIFICO/client-profile")
    assert get_resp.status_code == 200
    saved = get_resp.get_json()["profile"]["devops_environment_settings"]
    assert saved == settings
