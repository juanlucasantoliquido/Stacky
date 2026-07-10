"""Plan 112 F4 — Telemetría A/B del híbrido en GET /api/docs-rag/stats."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import db
from services import docs_rag
from services.docs_rag import DocChunk

db.init_db()


@pytest.fixture(autouse=True)
def _reset():
    docs_rag._reset_hybrid_telemetry()
    yield
    docs_rag._reset_hybrid_telemetry()


def test_record_increments_counters():
    docs_rag.record_hybrid_query(lexical=3, added=2, new_from_expansion=True)
    t = docs_rag.get_hybrid_telemetry()
    assert t == {"queries": 1, "queries_with_new": 1, "hits_lexical": 3, "hits_added": 2}


def test_queries_with_new_only_when_added():
    docs_rag.record_hybrid_query(lexical=5, added=0, new_from_expansion=False)
    docs_rag.record_hybrid_query(lexical=4, added=1, new_from_expansion=True)
    t = docs_rag.get_hybrid_telemetry()
    assert t["queries"] == 2
    assert t["queries_with_new"] == 1
    assert t["hits_lexical"] == 9
    assert t["hits_added"] == 1


def test_stats_includes_hybrid_block(monkeypatch):
    import config as cfg
    cfg.config.STACKY_DOCS_RAG_HYBRID_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    monkeypatch.setattr("api.docs_rag._resolve_project", lambda n: ("TEST", {}))
    resp = app.test_client().get("/api/docs-rag/stats")
    data = resp.get_json()
    assert "hybrid" in data
    assert set(data["hybrid"].keys()) == {
        "queries", "queries_with_new", "hits_lexical", "hits_added"}


def test_existing_stats_keys_unchanged():
    with db.session_scope() as s:
        s.query(DocChunk).filter_by(project_name="ST1").delete()
        s.add(DocChunk(project_name="ST1", file_path="a.md", section_heading="",
                       chunk_text="x", term_freqs_json="{}", doc_norm=0.0))
    stats = docs_rag.get_stats("ST1")
    for key in ("chunks", "files", "last_indexed"):
        assert key in stats
    assert stats["chunks"] == 1
    assert "hybrid" in stats  # aditivo
