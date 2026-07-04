"""tests/test_plan88_presets_validation.py — F2 tests (validación aditiva de
devops_publication_presets, devops_publication_settings y publish_group en
put_client_profile). Mismo fixture que test_plan87_drafts_validation.py."""
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

    for name, tracker_type in [("RSPACIFICO", "azure_devops"), ("B2IMPACT", "jira")]:
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


def _valid_preset(**overrides):
    preset = {"name": "a", "mode": "todo", "groups": []}
    preset.update(overrides)
    return preset


class TestF2PresetsValidation:
    def test_f2_absent_keys_noop(self, client):
        resp = _put(client, {"schema_version": 1, "language": {"primary": "csharp"}})
        assert resp.status_code == 200
        assert resp.get_json().get("ok") is True

    def test_f2_preset_bad_mode_400(self, client):
        resp = _put(client, {"devops_publication_presets": [_valid_preset(mode="invalido")]})
        assert resp.status_code == 400
        assert "mode" in resp.get_json().get("error", "")

    def test_f2_preset_no_name_400(self, client):
        preset = _valid_preset()
        del preset["name"]
        resp = _put(client, {"devops_publication_presets": [preset]})
        assert resp.status_code == 400
        assert "name" in resp.get_json().get("error", "")

    def test_f2_selection_without_names_400(self, client):
        resp = _put(client, {"devops_publication_presets": [_valid_preset(mode="selection")]})
        assert resp.status_code == 400
        assert "process_names" in resp.get_json().get("error", "")

    def test_f2_bad_group_400(self, client):
        resp = _put(client, {"devops_publication_presets": [_valid_preset(groups=["mensual"])]})
        assert resp.status_code == 400
        assert "groups" in resp.get_json().get("error", "")

    def test_f2_bad_target_400(self, client):
        resp = _put(client, {"devops_publication_presets": [_valid_preset(target="jenkins")]})
        assert resp.status_code == 400
        assert "target" in resp.get_json().get("error", "")

    def test_f2_duplicate_preset_name_400(self, client):
        resp = _put(client, {"devops_publication_presets": [_valid_preset(name="a"), _valid_preset(name="a")]})
        assert resp.status_code == 400
        assert "duplicado" in resp.get_json().get("error", "")

    def test_f2_over_50_presets_400(self, client):
        presets = [_valid_preset(name=f"p{i}") for i in range(51)]
        resp = _put(client, {"devops_publication_presets": presets})
        assert resp.status_code == 400
        assert "50" in resp.get_json().get("error", "")

    def test_f2_preset_name_over_120_400(self, client):
        resp = _put(client, {"devops_publication_presets": [_valid_preset(name="x" * 121)]})
        assert resp.status_code == 400
        assert "120" in resp.get_json().get("error", "")

    def test_f2_publish_group_invalid_400(self, client):
        resp = _put(client, {"process_catalog": [{"name": "P1", "kind": "entry", "publish_group": "mensual"}]})
        assert resp.status_code == 400
        assert resp.get_json().get("error") == "invalid_publish_group"

    def test_f2_publish_group_absent_tolerated(self, client):
        resp = _put(client, {"process_catalog": [{"name": "P1", "kind": "entry"}]})
        assert resp.status_code == 200

    def test_f2_valid_roundtrip(self, client):
        profile = {
            "devops_publication_presets": [_valid_preset(name="preset1")],
            "devops_publication_settings": {"step_templates": {"entry": "echo {process_name}"}},
            "process_catalog": [{"name": "P1", "kind": "entry", "publish_group": "batch"}],
        }
        resp = _put(client, profile)
        assert resp.status_code == 200

        get_resp = client.get("/api/projects/RSPACIFICO/client-profile")
        assert get_resp.status_code == 200
        saved = get_resp.get_json()["profile"]
        assert saved["devops_publication_presets"] == profile["devops_publication_presets"]
        assert saved["devops_publication_settings"] == profile["devops_publication_settings"]
        assert saved["process_catalog"] == profile["process_catalog"]

    def test_f2_bad_template_key_400(self, client):
        resp = _put(client, {"devops_publication_settings": {"step_templates": {"deploy": "x"}}})
        assert resp.status_code == 400
        assert "step_templates" in resp.get_json().get("error", "")
