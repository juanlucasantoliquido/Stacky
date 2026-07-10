"""Plan 110 F4bis — GET /api/pr-review/models (catálogo Copilot para elegir el id Haiku, C3)."""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def app_on():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_PR_REVIEWER_ENABLED", False)
    orig_model = getattr(cfg.config, "STACKY_PR_REVIEW_HAIKU_MODEL", "")
    cfg.config.STACKY_PR_REVIEWER_ENABLED = True
    cfg.config.STACKY_PR_REVIEW_HAIKU_MODEL = "claude-3.5-haiku"
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PR_REVIEWER_ENABLED = orig
    cfg.config.STACKY_PR_REVIEW_HAIKU_MODEL = orig_model


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


def test_models_404_when_flag_off(app_off):
    c = app_off.test_client()
    assert c.get("/api/pr-review/models").status_code == 404


def test_models_lists_and_flags_haiku(app_on):
    c = app_on.test_client()
    catalog = [
        {"id": "claude-3.5-haiku", "name": "Claude 3.5 Haiku"},
        {"id": "gpt-4o", "name": "GPT-4o"},
    ]
    with mock.patch("copilot_bridge.list_copilot_models", return_value=catalog):
        resp = c.get("/api/pr-review/models")
        assert resp.status_code == 200
        data = resp.get_json()
        by_id = {m["id"]: m["is_haiku"] for m in data["models"]}
        assert by_id["claude-3.5-haiku"] is True
        assert by_id["gpt-4o"] is False
        assert data["configured"] == "claude-3.5-haiku"


def test_models_502_when_copilot_unavailable(app_on):
    c = app_on.test_client()
    with mock.patch("copilot_bridge.list_copilot_models", side_effect=RuntimeError("sin token")):
        resp = c.get("/api/pr-review/models")
        assert resp.status_code == 502
        assert resp.get_json()["error"] == "copilot_models_unavailable"
