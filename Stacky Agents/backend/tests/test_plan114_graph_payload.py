"""Plan 114 F2 — No-regresión del payload /api/docs/graph con flag OFF/ON + anti-polución de cache (C1).

NOTA: se monta el blueprint `docs` en AISLAMIENTO (importlib) para no gatillar
`api/__init__.py`, que a la fecha está roto por WIP ajeno (SyntaxError preexistente
en api/devops_servers.py, commiteado en HEAD — no es de este plan).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from flask import Flask

import config as cfg
from services import doc_graph, doc_indexer, doc_staleness

_BACKEND = Path(__file__).resolve().parents[1]


def _load_docs_module():
    spec = importlib.util.spec_from_file_location("docs_iso_p114", str(_BACKEND / "api" / "docs.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _client():
    m = _load_docs_module()
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(m.bp, url_prefix="/api/docs")
    return app.test_client()


def _fake_graph():
    note_id = "note:src1:note.md"
    return {
        "sources": [{"id": "src1", "relative_path": "docs"}],
        "nodes": [
            {"id": note_id, "kind": "note", "path": "note.md", "source_id": "src1"},
            {"id": "code:src/mod.py", "kind": "code", "path": "src/mod.py", "source_id": ""},
        ],
        "edges": [{"source": note_id, "target": "code:src/mod.py", "kind": "code_ref"}],
        "doc_health": {"status": "SANA"},
    }


@pytest.fixture
def wiring(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DOCS_GRAPH_ENABLED", True, raising=False)
    shared = _fake_graph()
    monkeypatch.setattr(doc_graph, "build_graph", lambda **kw: shared)
    monkeypatch.setattr(doc_indexer, "list_doc_sources",
                        lambda project_name=None: {"workspace_root": "/repo", "sources": []})
    doc_staleness._epoch_cache.clear()
    return shared


def test_graph_payload_identical_when_staleness_off(wiring, monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DOCS_STALENESS_ENABLED", False, raising=False)
    data = _client().get("/api/docs/graph").get_json()
    assert data["ok"] is True
    assert "stale_stats" not in data
    for e in data["edges"]:
        assert "stale" not in e
    for n in data["nodes"]:
        assert "has_stale" not in n


def test_graph_payload_has_stale_fields_when_on(wiring, monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DOCS_STALENESS_ENABLED", True, raising=False)
    # código (src/mod.py) más nuevo que la nota (docs/note.md) → stale
    epochs = {"src/mod.py": 2000, "docs/note.md": 1000}
    monkeypatch.setattr(doc_staleness, "git_last_commit_epoch",
                        lambda repo_root, rel: epochs.get(rel))
    data = _client().get("/api/docs/graph").get_json()
    assert data["stale_stats"] == {"stale_edges": 1, "stale_notes": 1}
    code_edge = next(e for e in data["edges"] if e["kind"] == "code_ref")
    assert code_edge["stale"] is True
    note = next(n for n in data["nodes"] if n["kind"] == "note")
    assert note["has_stale"] is True


def test_cache_not_polluted_after_annotation(wiring, monkeypatch):
    """C1 — request ON (anota) seguida de request OFF → la 2da NO trae campos stale."""
    epochs = {"src/mod.py": 2000, "docs/note.md": 1000}
    monkeypatch.setattr(doc_staleness, "git_last_commit_epoch",
                        lambda repo_root, rel: epochs.get(rel))
    monkeypatch.setattr(cfg.config, "STACKY_DOCS_STALENESS_ENABLED", True, raising=False)
    on = _client().get("/api/docs/graph").get_json()
    assert on["stale_stats"]["stale_edges"] == 1  # sí anotó

    monkeypatch.setattr(cfg.config, "STACKY_DOCS_STALENESS_ENABLED", False, raising=False)
    off = _client().get("/api/docs/graph").get_json()
    assert "stale_stats" not in off
    for e in off["edges"]:
        assert "stale" not in e  # la cache del 109 (objeto compartido) quedó limpia
    for n in off["nodes"]:
        assert "has_stale" not in n
