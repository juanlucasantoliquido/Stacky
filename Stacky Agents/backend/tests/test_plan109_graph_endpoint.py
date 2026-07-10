"""tests/test_plan109_graph_endpoint.py — Plan 109 F4.

GET /api/docs/graph gateado por flag + golden de no-regresión de /api/docs/*.
Patrón de fixture app/client: test_plan89_environments_endpoints.py.
"""
from unittest.mock import MagicMock

import pytest


def _make_app(flag_on: bool):
    import config as cfg
    cfg.config.STACKY_DOCS_GRAPH_ENABLED = flag_on
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def app_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DOCS_GRAPH_ENABLED", False)
    app = _make_app(True)
    yield app
    cfg.config.STACKY_DOCS_GRAPH_ENABLED = original


@pytest.fixture
def app_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DOCS_GRAPH_ENABLED", False)
    app = _make_app(False)
    yield app
    cfg.config.STACKY_DOCS_GRAPH_ENABLED = original


_FAKE_GRAPH = {
    "generated_at": "2026-07-09T00:00:00+00:00",
    "active_project": "TEST",
    "sources": [],
    "nodes": [],
    "edges": [],
    "orphans": [],
    "stats": {"notes": 0},
    "doc_health": {"status": "SIN_DOCS"},
}


def test_graph_404_when_flag_off(app_off):
    resp = app_off.test_client().get("/api/docs/graph")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "docs_graph_disabled"


def test_graph_ok_when_flag_on(app_on, monkeypatch):
    monkeypatch.setattr("services.doc_graph.build_graph", lambda **kw: dict(_FAKE_GRAPH))
    resp = app_on.test_client().get("/api/docs/graph")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    for key in ("nodes", "edges", "orphans", "stats", "doc_health", "sources", "generated_at"):
        assert key in data


def test_graph_500_wrapped_on_exception(app_on, monkeypatch):
    def boom(**kw):
        raise RuntimeError("secreto interno")

    monkeypatch.setattr("services.doc_graph.build_graph", boom)
    resp = app_on.test_client().get("/api/docs/graph")
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["error"] == "docs_graph_failed"
    assert "secreto interno" not in (data.get("message") or "")  # (C7) sin fuga


def test_docs_endpoints_unchanged_when_flag_off(app_off):
    client = app_off.test_client()
    resp = client.get("/api/docs/sources")
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == {
        "ok", "active_project", "project_display_name", "workspace_root",
        "default_source_id", "sources", "note", "graph_enabled",
    }
    assert data["graph_enabled"] is False
    # /index sin cambios (no lo tocamos): 200 con 'roots'.
    idx = client.get("/api/docs/index")
    assert idx.status_code == 200
    assert "roots" in idx.get_json()


def test_graph_refresh_param_forces_rebuild(app_on, monkeypatch):
    monkeypatch.setattr("services.doc_graph.build_graph", lambda **kw: dict(_FAKE_GRAPH))
    invalidate = MagicMock()
    monkeypatch.setattr("services.doc_graph.invalidate_graph_cache", invalidate)
    client = app_on.test_client()
    client.get("/api/docs/graph?refresh=1")
    assert invalidate.called
    invalidate.reset_mock()
    client.get("/api/docs/graph")
    assert not invalidate.called
