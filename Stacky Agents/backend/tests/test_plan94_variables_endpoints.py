"""tests/test_plan94_variables_endpoints.py — Plan 94 F3.
Tests de los endpoints /api/devops/variables."""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from api.devops_variables import bp
from services.ci_variables import VariablesUnavailableError
from services.tracker_provider import TrackerConfigError, TrackerApiError


@pytest.fixture
def app_on(monkeypatch):
    import config as cfg
    orig_vars = getattr(cfg.config, "STACKY_DEVOPS_VARIABLES_ENABLED", False)
    orig_panel = getattr(cfg.config, "STACKY_DEVOPS_PANEL_ENABLED", False)
    cfg.config.STACKY_DEVOPS_VARIABLES_ENABLED = True
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_VARIABLES_ENABLED = orig_vars
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = orig_panel


@pytest.fixture
def app_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_DEVOPS_VARIABLES_ENABLED", False)
    cfg.config.STACKY_DEVOPS_VARIABLES_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_VARIABLES_ENABLED = orig


def _c(app):
    return app.test_client()


def test_f3_route_registered():
    """El blueprint está registrado en url_map."""
    from app import create_app

    app = create_app()
    rules = [str(rule) for rule in app.url_map.iter_rules()]
    assert any("/api/devops/variables" in rule for rule in rules)


def test_f3_health_has_variables_enabled():
    """Health key variables_enabled existe."""
    with pytest.MonkeyPatch().context() as m:
        m.setenv("STACKY_DEVOPS_VARIABLES_ENABLED", "true")
        from app import create_app

        app = create_app()
        with app.test_client() as client:
            resp = client.get("/api/devops/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "variables_enabled" in data


def test_f3_flag_off_all_routes_404(app_off):
    c = _c(app_off)
    assert c.get("/api/devops/variables").status_code == 404
    assert c.post("/api/devops/variables", json={"project": "p", "key": "K", "value": "v", "confirm": True}).status_code == 404
    assert c.post("/api/devops/variables/delete", json={"project": "p", "key": "K", "confirm": True}).status_code == 404


def test_f3_non_json_post_400(app_on):
    """91 C5: POST sin Content-Type application/json ⇒ 400."""
    c = _c(app_on)
    resp = c.post("/api/devops/variables", data="not json")
    assert resp.status_code == 400


def test_f3_post_without_confirm_400(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        mock_get.return_value = mock.MagicMock(name="gitlab")
        resp = c.post("/api/devops/variables", json={"project": "p", "key": "DEPLOY_PATH", "value": "v", "secret": False})
        assert resp.status_code == 400
        mock_get.return_value.set_variable.assert_not_called()


def test_f3_delete_without_confirm_400(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        mock_get.return_value = mock.MagicMock(name="gitlab")
        resp = c.post("/api/devops/variables/delete", json={"project": "p", "key": "DEPLOY_PATH"})
        assert resp.status_code == 400
        mock_get.return_value.delete_variable.assert_not_called()


def test_f3_post_invalid_key_400(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        mock_get.return_value = mock.MagicMock(name="gitlab")
        resp = c.post("/api/devops/variables", json={"project": "p", "key": "9invalid", "value": "v", "confirm": True})
        assert resp.status_code == 400
        mock_get.return_value.set_variable.assert_not_called()


def test_f3_post_happy_201_no_value_in_response(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        provider = mock.MagicMock()
        provider.set_variable.return_value = {"key": "DB_PASSWORD", "is_secret": True, "masked": True}
        mock_get.return_value = provider
        resp = c.post(
            "/api/devops/variables",
            json={"project": "p", "key": "DB_PASSWORD", "value": "S3cr3t!XYZ", "secret": True, "confirm": True},
        )
        assert resp.status_code == 201
        raw = resp.get_data(as_text=True)
        assert "S3cr3t!XYZ" not in raw
        provider.set_variable.assert_called_once_with("DB_PASSWORD", "S3cr3t!XYZ", True)


def test_f3_get_lists_without_values(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        provider = mock.MagicMock()
        provider.name = "gitlab"
        provider.list_variables.return_value = [
            {"key": "DB_PASSWORD", "is_secret": True, "has_value": True, "masked": True},
        ]
        mock_get.return_value = provider
        resp = c.get("/api/devops/variables?project=p")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "gitlab"
        assert all("value" not in v for v in data["variables"])


def test_f3_ado_unavailable_409_kind(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        mock_get.side_effect = VariablesUnavailableError("ADO sin pipeline definition ... plan 95")
        resp = c.get("/api/devops/variables?project=p")
        assert resp.status_code == 409
        assert resp.get_json()["kind"] == "variables_unavailable"


def test_f3_post_unavailable_409(app_on):
    """C6: la MISMA excepción mapea igual en POST (no solo en GET)."""
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        mock_get.side_effect = VariablesUnavailableError("ADO sin pipeline definition ... plan 95")
        resp = c.post(
            "/api/devops/variables",
            json={"project": "p", "key": "DEPLOY_PATH", "value": "v", "confirm": True},
        )
        assert resp.status_code == 409
        assert resp.get_json()["kind"] == "variables_unavailable"


def test_f3_delete_absent_404(app_on):
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        provider = mock.MagicMock()
        provider.delete_variable.return_value = False
        mock_get.return_value = provider
        resp = c.post("/api/devops/variables/delete", json={"project": "p", "key": "MISSING", "confirm": True})
        assert resp.status_code == 404


def test_f3_tracker_config_400_kind(app_on):
    """C14a: TrackerConfigError de la fábrica ⇒ 400 kind=tracker_config (no 502)."""
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        mock_get.side_effect = TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")
        resp = c.get("/api/devops/variables?project=p")
        assert resp.status_code == 400
        assert resp.get_json()["kind"] == "tracker_config"


def test_f3_unexpected_error_500_generic(app_on):
    """C14b: excepción inesperada ⇒ 500 con mensaje GENÉRICO FIJO, sin str(e)."""
    c = _c(app_on)
    with mock.patch("api.devops_variables.get_variables_provider") as mock_get:
        mock_get.side_effect = RuntimeError("boom S3cr3t!XYZ")
        resp = c.get("/api/devops/variables?project=p")
        assert resp.status_code == 500
        raw = resp.get_data(as_text=True)
        assert "S3cr3t!XYZ" not in raw
        assert "error interno de variables" in raw
