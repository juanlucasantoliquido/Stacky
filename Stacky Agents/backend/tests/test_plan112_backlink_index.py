"""Plan 112 F1 — Índice de backlinks + vecindad (puente grafo↔docs_rag).

Monkeypatch de doc_graph.build_graph con un grafo fake + flag 109 ON.
El fallback por basename (C2) usa la tabla DocChunk real (sqlite in-memory).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
import services.doc_graph as doc_graph_mod
from config import config
from services import docs_rag
from services.docs_rag import DocChunk

db.init_db()


def _note(node_id, path, in_degree=0, source_id="project-docs:main"):
    return {"id": node_id, "kind": "note", "path": path,
            "source_id": source_id, "in_degree": in_degree, "out_degree": 0}


def _fake_graph(nodes, edges):
    def _build(project_name=None, **kw):
        return {"nodes": nodes, "edges": edges}
    return _build


def _clear_chunks(project):
    with db.session_scope() as s:
        s.query(DocChunk).filter_by(project_name=project).delete()


def _add_chunk(project, file_path):
    with db.session_scope() as s:
        s.add(DocChunk(project_name=project, file_path=file_path,
                       section_heading="", chunk_text="x",
                       term_freqs_json="{}", doc_norm=0.0))


def test_backlinks_by_path_from_in_degree(monkeypatch):
    monkeypatch.setattr(config, "STACKY_DOCS_GRAPH_ENABLED", True)
    nodes = [_note("note:project-docs:main:a.md", "a.md", in_degree=3),
             _note("note:project-docs:main:b.md", "b.md", in_degree=1)]
    monkeypatch.setattr(doc_graph_mod, "build_graph", _fake_graph(nodes, []))
    _clear_chunks("P1")
    bl, nb = docs_rag._build_backlink_index("P1")
    assert bl == {"a.md": 3, "b.md": 1}


def test_neighbors_undirected_dedup(monkeypatch):
    monkeypatch.setattr(config, "STACKY_DOCS_GRAPH_ENABLED", True)
    nodes = [_note("id:a", "a.md"), _note("id:b", "b.md")]
    edges = [{"source": "id:a", "target": "id:b", "kind": "md"},
             {"source": "id:a", "target": "id:b", "kind": "wikilink"}]  # duplicado
    monkeypatch.setattr(doc_graph_mod, "build_graph", _fake_graph(nodes, edges))
    _clear_chunks("P1")
    _, nb = docs_rag._build_backlink_index("P1")
    assert nb["a.md"] == ["b.md"]
    assert nb["b.md"] == ["a.md"]


def test_returns_empty_when_graph_flag_off(monkeypatch):
    monkeypatch.setattr(config, "STACKY_DOCS_GRAPH_ENABLED", False)
    called = {"n": 0}
    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("no debe llamarse")
    monkeypatch.setattr(doc_graph_mod, "build_graph", _boom)
    assert docs_rag._build_backlink_index("P1") == ({}, {})
    assert called["n"] == 0


def test_returns_empty_and_logs_when_build_graph_raises(monkeypatch, caplog):
    monkeypatch.setattr(config, "STACKY_DOCS_GRAPH_ENABLED", True)
    def _raise(*a, **k):
        raise RuntimeError("grafo caído")
    monkeypatch.setattr(doc_graph_mod, "build_graph", _raise)
    import logging
    with caplog.at_level(logging.WARNING):
        assert docs_rag._build_backlink_index("P1") == ({}, {})
    assert any("backlink index unavailable" in r.message for r in caplog.records)


def test_ignores_non_project_and_code_nodes(monkeypatch):
    monkeypatch.setattr(config, "STACKY_DOCS_GRAPH_ENABLED", True)
    nodes = [
        _note("id:a", "a.md", in_degree=5),
        _note("id:ext", "ext.md", in_degree=9, source_id="vscode-prompts"),  # no project
        {"id": "code:x", "kind": "code", "path": "x.py", "source_id": "",
         "in_degree": 2, "out_degree": 0},
    ]
    monkeypatch.setattr(doc_graph_mod, "build_graph", _fake_graph(nodes, []))
    _clear_chunks("P1")
    bl, _ = docs_rag._build_backlink_index("P1")
    assert bl == {"a.md": 5}


def test_basename_fallback_mapping(monkeypatch):
    monkeypatch.setattr(config, "STACKY_DOCS_GRAPH_ENABLED", True)
    # Caso 1: chunk "a.md" resuelve por basename contra nodo "sub/a.md".
    nodes = [_note("id:suba", "sub/a.md", in_degree=4)]
    edges = []
    monkeypatch.setattr(doc_graph_mod, "build_graph", _fake_graph(nodes, edges))
    _clear_chunks("PF1")
    _add_chunk("PF1", "a.md")
    bl, nb = docs_rag._build_backlink_index("PF1")
    assert bl["a.md"] == 4  # alias por basename hereda in_degree

    # Caso 2: dos nodos con basename "a.md" ambiguo → se omite del fallback.
    nodes2 = [_note("id:xa", "x/a.md", in_degree=4),
              _note("id:ya", "y/a.md", in_degree=7)]
    monkeypatch.setattr(doc_graph_mod, "build_graph", _fake_graph(nodes2, []))
    _clear_chunks("PF2")
    _add_chunk("PF2", "a.md")
    bl2, _ = docs_rag._build_backlink_index("PF2")
    assert "a.md" not in bl2  # ambiguo → sin alias, sin excepción
