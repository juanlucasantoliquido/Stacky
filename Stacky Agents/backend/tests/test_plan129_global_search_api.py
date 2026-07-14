"""Plan 129 F2 — API GET /api/search/global (gateada por STACKY_PALETTE_DEEP_SEARCH_ENABLED)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_PALETTE_DEEP_SEARCH_ENABLED", False)
    cfg.config.STACKY_PALETTE_DEEP_SEARCH_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PALETTE_DEEP_SEARCH_ENABLED = original


@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_PALETTE_DEEP_SEARCH_ENABLED", False)
    cfg.config.STACKY_PALETTE_DEEP_SEARCH_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PALETTE_DEEP_SEARCH_ENABLED = original


def test_off_404(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.get("/api/search/global?q=x")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "palette_deep_search_disabled"


def test_on_200_shape(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/search/global?q=zzz_no_deberia_matchear_nada")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "groups" in data
    order = [g["kind"] for g in data["groups"]]
    expected_order = ["ticket", "execution", "doc", "server", "flag"]
    assert order == [k for k in expected_order if k in order]
    for group in data["groups"]:
        for hit in group["hits"]:
            assert "score" not in hit


def test_q_larga_400(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/search/global?q=" + ("a" * 201))
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "query_too_long"


def test_limit_clamp(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/search/global?q=plan&limit=999")
    assert resp.status_code == 200
    for group in resp.get_json()["groups"]:
        assert len(group["hits"]) <= 20

    resp2 = client.get("/api/search/global?q=plan&limit=abc")
    assert resp2.status_code == 200


def test_health_reporta_on(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/search/health")
    assert resp.status_code == 200
    assert resp.get_json()["flag_enabled"] is True
