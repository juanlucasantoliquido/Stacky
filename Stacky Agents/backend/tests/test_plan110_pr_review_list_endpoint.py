"""Plan 110 F2 — GET /api/pr-review/list. Gate por flag, shape normalizado, nunca 500."""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from services.tracker_provider import TrackerConfigError, TrackerApiError


@pytest.fixture
def app_on():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_PR_REVIEWER_ENABLED", False)
    cfg.config.STACKY_PR_REVIEWER_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PR_REVIEWER_ENABLED = orig


@pytest.fixture
def app_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_PR_REVIEWER_ENABLED", False)
    cfg.config.STACKY_PR_REVIEWER_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PR_REVIEWER_ENABLED = orig


def _fake_provider(mrs):
    provider = mock.MagicMock()
    provider.name = "gitlab"
    provider.list_merge_requests.return_value = mrs
    return provider


def test_list_404_when_flag_off(app_off):
    c = app_off.test_client()
    assert c.get("/api/pr-review/list?project=p").status_code == 404


def test_list_ok_with_flag_on(app_on):
    c = app_on.test_client()
    mrs = [{"id": "7", "title": "t", "state": "open", "source_branch": "a",
            "target_branch": "main", "author": "Ana", "web_url": "u", "pipeline_status": "success"}]
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_fake_provider(mrs)):
        resp = c.get("/api/pr-review/list?project=p")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "gitlab"
        assert data["merge_requests"] == mrs


def test_list_tracker_error_is_not_500(app_on):
    c = app_on.test_client()
    provider = mock.MagicMock()
    provider.name = "gitlab"
    provider.list_merge_requests.side_effect = TrackerApiError(502, "tracker caído", kind="upstream")
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=provider):
        resp = c.get("/api/pr-review/list?project=p")
        assert resp.status_code == 502
        assert resp.get_json()["error"]


def test_list_config_error_400(app_on):
    c = app_on.test_client()
    with mock.patch("api.pr_review.get_merge_request_provider", side_effect=TrackerConfigError("sin credenciales")):
        resp = c.get("/api/pr-review/list?project=p")
        assert resp.status_code == 400
        assert resp.get_json()["kind"] == "tracker_config"


def test_list_ado_config_error_400_not_500(app_on):
    """AdoConfigError (PAT no encontrado) debe mapear a 400 con mensaje, no al 500 mudo."""
    from services.ado_client import AdoConfigError
    c = app_on.test_client()
    with mock.patch("api.pr_review.get_merge_request_provider",
                    side_effect=AdoConfigError("ADO PAT no encontrado")):
        resp = c.get("/api/pr-review/list?project=p")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["kind"] == "tracker_config"
        assert "PAT" in data["error"]


def test_list_ado_api_error_maps_status(app_on):
    """AdoApiError conserva su status_code (p.ej. 401 PAT inválido) en vez de 500."""
    from services.ado_client import AdoApiError
    c = app_on.test_client()
    provider = mock.MagicMock()
    provider.name = "azure_devops"
    provider.list_merge_requests.side_effect = AdoApiError("PAT inválido", status_code=401)
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=provider):
        resp = c.get("/api/pr-review/list?project=p")
        assert resp.status_code == 401
        assert resp.get_json()["kind"] == "tracker_api"
