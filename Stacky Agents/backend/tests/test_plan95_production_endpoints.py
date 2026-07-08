"""tests/test_plan95_production_endpoints.py — Plan 95 F3.
Tests de los endpoints /api/devops/production."""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from api.devops_production import bp
from services.tracker_provider import TrackerConfigError, TrackerApiError


@pytest.fixture
def app_on(monkeypatch):
    import config as cfg
    orig_prod = getattr(cfg.config, "STACKY_DEVOPS_PRODUCTION_ENABLED", False)
    orig_panel = getattr(cfg.config, "STACKY_DEVOPS_PANEL_ENABLED", False)
    cfg.config.STACKY_DEVOPS_PRODUCTION_ENABLED = True
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PRODUCTION_ENABLED = orig_prod
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = orig_panel


@pytest.fixture
def app_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_DEVOPS_PRODUCTION_ENABLED", False)
    cfg.config.STACKY_DEVOPS_PRODUCTION_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PRODUCTION_ENABLED = orig


def _c(app):
    return app.test_client()


def test_f3_route_registered():
    from app import create_app

    app = create_app()
    rules = [str(rule) for rule in app.url_map.iter_rules()]
    assert any("/api/devops/production/mr" in rule for rule in rules)


def test_f3_health_has_production_enabled():
    with pytest.MonkeyPatch().context() as m:
        m.setenv("STACKY_DEVOPS_PRODUCTION_ENABLED", "true")
        from app import create_app

        app = create_app()
        with app.test_client() as client:
            resp = client.get("/api/devops/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "production_enabled" in data
            # C2: ado_commit_supported es capability independiente (siempre True en este build)
            assert data["ado_commit_supported"] is True


def test_f3_flag_off_all_routes_404(app_off):
    c = _c(app_off)
    assert c.post("/api/devops/production/mr", json={"project": "p", "source_branch": "b", "confirm": True}).status_code == 404
    assert c.get("/api/devops/production/mr/1?project=p").status_code == 404
    assert c.post("/api/devops/production/mr/1/merge", json={"project": "p", "confirm": True}).status_code == 404
    assert c.post("/api/devops/production/ado/ensure-definition", json={"project": "p", "confirm": True}).status_code == 404


def test_f3_non_json_post_400(app_on):
    c = _c(app_on)
    resp = c.post("/api/devops/production/mr", data="not json")
    assert resp.status_code == 400


def test_f3_create_mr_without_confirm_400(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_production.get_merge_request_provider") as mock_get:
        mock_get.return_value = mock.MagicMock(name="gitlab")
        resp = c.post("/api/devops/production/mr", json={"project": "p", "source_branch": "feature/x"})
        assert resp.status_code == 400
        mock_get.return_value.create_merge_request.assert_not_called()


def test_f3_merge_without_confirm_400(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_production.get_merge_request_provider") as mock_get:
        mock_get.return_value = mock.MagicMock(name="gitlab")
        resp = c.post("/api/devops/production/mr/1/merge", json={"project": "p"})
        assert resp.status_code == 400
        mock_get.return_value.merge_merge_request.assert_not_called()


def test_f3_create_mr_happy_201_default_target(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_production.get_merge_request_provider") as mock_get:
        with mock.patch("api.devops_production._default_branch", return_value="main") as mock_default:
            provider = mock.MagicMock()
            provider.name = "gitlab"
            provider.create_merge_request.return_value = {"id": "42", "web_url": "http://x", "state": "open"}
            mock_get.return_value = provider

            resp = c.post(
                "/api/devops/production/mr",
                json={"project": "p", "source_branch": "feature/x", "confirm": True},
            )
            assert resp.status_code == 201
            mock_default.assert_called_once()
            provider.create_merge_request.assert_called_once_with(
                "feature/x", "main", "pipeline: feature/x", "",
            )


def test_f3_get_mr_polls_provider(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_production.get_merge_request_provider") as mock_get:
        provider = mock.MagicMock()
        provider.get_merge_request.return_value = {
            "id": "42", "state": "open", "pipeline_status": "running", "mergeable": False, "web_url": "http://x",
        }
        mock_get.return_value = provider
        resp = c.get("/api/devops/production/mr/42?project=p")
        assert resp.status_code == 200
        assert resp.get_json()["pipeline_status"] == "running"
        provider.get_merge_request.assert_called_once_with("42")


def test_f3_merge_happy(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_production.get_merge_request_provider") as mock_get:
        provider = mock.MagicMock()
        provider.merge_merge_request.return_value = {"id": "42", "state": "merged"}
        mock_get.return_value = provider
        resp = c.post("/api/devops/production/mr/42/merge", json={"project": "p", "confirm": True})
        assert resp.status_code == 200
        assert resp.get_json()["state"] == "merged"


def test_f3_merge_conflict_status_propagated(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_production.get_merge_request_provider") as mock_get:
        provider = mock.MagicMock()
        provider.merge_merge_request.side_effect = TrackerApiError(409, "No se puede mergear: conflictos", kind="merge_conflict")
        mock_get.return_value = provider
        resp = c.post("/api/devops/production/mr/42/merge", json={"project": "p", "confirm": True})
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["kind"] == "merge_conflict"
        assert "conflictos" in data["error"]


def test_f3_ensure_definition_ado_only(app_on):
    c = _c(app_on)
    with mock.patch("services.project_context.resolve_project_context") as mock_ctx:
        mock_ctx.return_value.tracker_type = "gitlab"
        resp = c.post("/api/devops/production/ado/ensure-definition", json={"project": "p", "confirm": True})
        assert resp.status_code == 400
        assert "solo aplica a proyectos ADO" in resp.get_json()["error"]

    with mock.patch("services.project_context.resolve_project_context") as mock_ctx:
        mock_ctx.return_value.tracker_type = "azure_devops"
        with mock.patch("services.ado_pipeline_definitions.ensure_yaml_definition") as mock_ensure:
            mock_ensure.return_value = {"id": 7, "name": "stacky-x", "created": True}
            resp = c.post("/api/devops/production/ado/ensure-definition", json={"project": "p", "confirm": True})
            assert resp.status_code == 200
            assert resp.get_json()["created"] is True
