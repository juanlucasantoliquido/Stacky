"""tests/test_plan87_drafts_validation.py — F2 tests (validación de devops_pipeline_drafts)."""
import pytest
import json


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

    # Crear proyectos demo (RSPACIFICO ADO, B2IMPACT Jira)
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


class TestF2DraftsValidation:
    """Validación aditiva de devops_pipeline_drafts en put_client_profile."""

    def test_f2_absent_key_noop(self, client):
        """PUT sin la key → mismo resultado que hoy (200/ok:true)."""
        # Usar RSPACIFICO que está creado por el fixture
        # Profile mínimo válido (sin devops_pipeline_drafts)
        profile = {
            "schema_version": 1,
            "language": {"primary": "csharp"},
        }
        resp = client.put("/api/projects/RSPACIFICO/client-profile",
                         json={"profile": profile})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("ok") is True

    def test_f2_drafts_not_list_400(self, client):
        """drafts no es lista → 400."""
        resp = client.put("/api/projects/RSPACIFICO/client-profile",
                         json={"profile": {"devops_pipeline_drafts": {}}})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "debe ser una lista" in data.get("error", "")

    def test_f2_draft_without_name_400(self, client):
        """Draft sin name → 400."""
        resp = client.put("/api/projects/RSPACIFICO/client-profile",
                         json={"profile": {"devops_pipeline_drafts": [{"spec": {}}]}})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "name" in data.get("error", "").lower()

    def test_f2_draft_without_spec_400(self, client):
        """Draft sin spec → 400."""
        resp = client.put("/api/projects/RSPACIFICO/client-profile",
                         json={"profile": {"devops_pipeline_drafts": [{"name": "x"}]}})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "spec" in data.get("error", "").lower()

    def test_f2_over_50_drafts_400(self, client):
        """Más de 50 drafts → 400."""
        drafts = [{"name": f"d{i}", "spec": {}} for i in range(51)]
        resp = client.put("/api/projects/RSPACIFICO/client-profile",
                         json={"profile": {"devops_pipeline_drafts": drafts}})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "50" in data.get("error", "")

    def test_f2_duplicate_name_400(self, client):
        """Name duplicado → 400."""
        drafts = [
            {"name": "duplicate", "spec": {}},
            {"name": "duplicate", "spec": {}}
        ]
        resp = client.put("/api/projects/RSPACIFICO/client-profile",
                         json={"profile": {"devops_pipeline_drafts": drafts}})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "duplicado" in data.get("error", "").lower()

    def test_f2_name_over_120_chars_400(self, client):
        """Name > 120 chars → 400."""
        name = "a" * 121
        resp = client.put("/api/projects/RSPACIFICO/client-profile",
                         json={"profile": {"devops_pipeline_drafts": [{"name": name, "spec": {}}]}})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "120" in data.get("error", "")

    def test_f2_valid_drafts_persist(self, client):
        """Drafts válidos → 200 y persisten en GET."""
        drafts = [
            {"name": "test-draft", "spec": {"name": "p", "stages": []}},
        ]
        resp = client.put("/api/projects/RSPACIFICO/client-profile",
                         json={"profile": {"devops_pipeline_drafts": drafts}})
        assert resp.status_code == 200
        # GET para verificar persistencia
        resp = client.get("/api/projects/RSPACIFICO/client-profile")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "profile" in data
        assert data["profile"]["devops_pipeline_drafts"][0]["name"] == "test-draft"

    def test_f2_incomplete_spec_tolerated(self, client):
        """Draft con spec incompleto (inválido para publicar) → 200 (borrador en edición se tolera)."""
        drafts = [
            {"name": "incomplete", "spec": {"name": "", "stages": []}},
        ]
        resp = client.put("/api/projects/RSPACIFICO/client-profile",
                         json={"profile": {"devops_pipeline_drafts": drafts}})
        assert resp.status_code == 200
