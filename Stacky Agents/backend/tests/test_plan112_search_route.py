"""Plan 112 F3 — POST /api/docs-rag/search: selección por flag + golden + debug.

Patrón app/client: test_plan109_graph_endpoint.py. Flag OFF = byte-idéntico a hoy.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from services.docs_rag import DocHit


def _make_app(flag_on: bool):
    import config as cfg
    cfg.config.STACKY_DOCS_RAG_HYBRID_ENABLED = flag_on
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def app_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DOCS_RAG_HYBRID_ENABLED", False)
    app = _make_app(False)
    yield app
    cfg.config.STACKY_DOCS_RAG_HYBRID_ENABLED = original


@pytest.fixture
def app_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DOCS_RAG_HYBRID_ENABLED", False)
    app = _make_app(True)
    yield app
    cfg.config.STACKY_DOCS_RAG_HYBRID_ENABLED = original


@pytest.fixture(autouse=True)
def _stub_project(monkeypatch):
    monkeypatch.setattr("api.docs_rag._resolve_project", lambda n: ("TEST", {}))


def test_search_uses_plain_when_flag_off(app_off, monkeypatch):
    calls = {"plain": 0, "hybrid": 0}

    def _plain(name, query, top_k=5):
        calls["plain"] += 1
        return [DocHit("a.md", "", "x", 0.5)]

    def _hybrid(*a, **k):
        calls["hybrid"] += 1
        return []

    monkeypatch.setattr("api.docs_rag.search", _plain)
    monkeypatch.setattr("services.docs_rag.search_hybrid", _hybrid)
    resp = app_off.test_client().post("/api/docs-rag/search", json={"query": "q"})
    assert resp.status_code == 200
    assert calls == {"plain": 1, "hybrid": 0}


def test_search_uses_hybrid_when_flag_on(app_on, monkeypatch):
    calls = {"plain": 0, "hybrid": 0}

    def _plain(*a, **k):
        calls["plain"] += 1
        return []

    def _hybrid(name, query, top_k=5, **k):
        calls["hybrid"] += 1
        return [DocHit("a.md", "", "x", 0.5)]

    monkeypatch.setattr("api.docs_rag.search", _plain)
    monkeypatch.setattr("services.docs_rag.search_hybrid", _hybrid)
    resp = app_on.test_client().post("/api/docs-rag/search", json={"query": "q"})
    assert resp.status_code == 200
    assert calls == {"plain": 0, "hybrid": 1}


def test_search_response_shape_unchanged(app_off, monkeypatch):
    monkeypatch.setattr("api.docs_rag.search",
                        lambda name, query, top_k=5: [DocHit("a.md", "## H", "cuerpo", 0.42)])
    # incluso mandando debug_hybrid=true, con flag OFF el shape no cambia
    resp = app_off.test_client().post(
        "/api/docs-rag/search", json={"query": "q", "debug_hybrid": True})
    data = resp.get_json()
    assert set(data.keys()) == {"ok", "project_name", "query", "hits"}
    assert data["hits"][0] == {"file_path": "a.md", "section_heading": "## H",
                               "chunk_text": "cuerpo", "score": 0.42}


def test_debug_block_only_when_flag_on_and_requested(app_on, monkeypatch):
    def _hybrid(name, query, top_k=5, *, collect_debug=False):
        hits = [DocHit("a.md", "", "x", 0.5)]
        if collect_debug:
            return hits, {"lexical_files": ["a.md"], "expanded_files": ["b.md"],
                          "weights": {"alpha": 1.0, "beta": 0.15, "max_neighbors": 8}}
        return hits

    monkeypatch.setattr("services.docs_rag.search_hybrid", _hybrid)
    client = app_on.test_client()

    # con debug_hybrid=true → bloque presente con 3 keys
    r1 = client.post("/api/docs-rag/search", json={"query": "q", "debug_hybrid": True})
    d1 = r1.get_json()
    assert "hybrid_debug" in d1
    assert set(d1["hybrid_debug"].keys()) == {"lexical_files", "expanded_files", "weights"}

    # sin debug_hybrid → NO aparece el bloque
    r2 = client.post("/api/docs-rag/search", json={"query": "q"})
    assert "hybrid_debug" not in r2.get_json()
