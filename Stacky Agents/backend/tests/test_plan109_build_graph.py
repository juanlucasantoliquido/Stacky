"""tests/test_plan109_build_graph.py — Plan 109 F2.

build_graph: nodos, aristas, backlinks, huérfanas + cache por mtime.
Se monkeypatchea doc_indexer (list_doc_sources / build_project_docs_index /
build_index) para apuntar a un mini-corpus en tmp_path.
"""
import json

import pytest

from services import doc_indexer, doc_graph


def _write(path, text):
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    docs = ws / "docs"
    docs.mkdir(parents=True)
    (ws / "backend" / "services").mkdir(parents=True)
    _write(ws / "backend" / "services" / "foo.py", "print('hi')\n")

    _write(docs / "a.md", "Ver [x](b.md) y [[c]] y backend/services/foo.py:10\n")
    _write(docs / "b.md", "---\ntitle: B\n---\nrota [[no-existe]]\n")
    _write(docs / "c.md", "Nota C sin links\n")
    _write(docs / "huerfana.md", "Sola, sin links ni entrantes\n")

    def fake_list_doc_sources(project_name=None):
        return {
            "ok": True,
            "active_project": "TEST",
            "workspace_root": str(ws),
            "sources": [
                {"id": "project-docs:docs", "kind": "project-docs", "label": "docs",
                 "relative_path": "docs", "absolute_path": str(docs)},
            ],
        }

    def fake_build_project_docs_index(project_name=None, source_id=None):
        children = [
            {"kind": "file", "path": p.name, "source_id": source_id,
             "children": []}
            for p in sorted(docs.glob("*.md"))
        ]
        return {"roots": [{"children": children}]}

    def fake_build_index(vscode_prompts_dir=None):
        return {"roots": []}

    monkeypatch.setattr(doc_indexer, "list_doc_sources", fake_list_doc_sources)
    monkeypatch.setattr(doc_indexer, "build_project_docs_index", fake_build_project_docs_index)
    monkeypatch.setattr(doc_indexer, "build_index", fake_build_index)
    doc_graph.invalidate_graph_cache()
    yield {"ws": ws, "docs": docs}
    doc_graph.invalidate_graph_cache()


def _ids(graph):
    return {n["id"] for n in graph["nodes"]}


def test_nodes_and_edges_shape(corpus):
    g = doc_graph.build_graph()
    assert set(g.keys()) >= {"generated_at", "active_project", "sources", "nodes",
                             "edges", "orphans", "stats", "doc_health"}
    for n in g["nodes"]:
        assert n["id"].split(":", 1)[0] in {"note", "code", "missing"}
    assert any(n["id"].startswith("note:") for n in g["nodes"])


def test_md_link_resolved_same_source(corpus):
    g = doc_graph.build_graph()
    a = "note:project-docs:docs:a.md"
    b = "note:project-docs:docs:b.md"
    assert {"source": a, "target": b, "kind": "md"} in g["edges"]


def test_wikilink_resolved_case_insensitive(corpus):
    g = doc_graph.build_graph()
    a = "note:project-docs:docs:a.md"
    c = "note:project-docs:docs:c.md"
    assert {"source": a, "target": c, "kind": "wikilink"} in g["edges"]


def test_wikilink_unresolved_creates_missing_node(corpus):
    g = doc_graph.build_graph()
    node = next((n for n in g["nodes"] if n["id"] == "missing:no-existe"), None)
    assert node is not None
    assert node["kind"] == "missing"
    assert node["exists"] is False


def test_code_ref_node_and_exists_flag(corpus):
    g = doc_graph.build_graph()
    code = next(n for n in g["nodes"] if n["id"] == "code:backend/services/foo.py")
    assert code["exists"] is True
    # borrar el archivo y forzar rebuild
    (corpus["ws"] / "backend" / "services" / "foo.py").unlink()
    doc_graph.invalidate_graph_cache()
    g2 = doc_graph.build_graph()
    code2 = next(n for n in g2["nodes"] if n["id"] == "code:backend/services/foo.py")
    assert code2["exists"] is False


def test_orphan_detection(corpus):
    g = doc_graph.build_graph()
    assert "note:project-docs:docs:huerfana.md" in g["orphans"]
    assert "note:project-docs:docs:b.md" not in g["orphans"]


def test_md_link_escaping_source_dropped(corpus):
    _write(corpus["docs"] / "a.md", "escape [x](../../fuera.md)\n")
    doc_graph.invalidate_graph_cache()
    g = doc_graph.build_graph()
    for e in g["edges"]:
        assert "fuera" not in e["target"]


def test_cache_hit_within_ttl(corpus, monkeypatch):
    calls = {"n": 0}
    real = doc_graph._read_text

    def counting(path):
        calls["n"] += 1
        return real(path)

    monkeypatch.setattr(doc_graph, "_read_text", counting)
    doc_graph.invalidate_graph_cache()
    doc_graph.build_graph()
    first = calls["n"]
    assert first > 0
    doc_graph.build_graph()  # dentro del TTL → cache, sin leer
    assert calls["n"] == first


def test_ttl_expired_fingerprint_change_rebuilds(corpus, monkeypatch):
    monkeypatch.setattr(doc_graph, "_GRAPH_TTL_SECONDS", 0)
    doc_graph.invalidate_graph_cache()
    g1 = doc_graph.build_graph()
    assert not any(n["id"] == "note:project-docs:docs:nueva.md" for n in g1["nodes"])
    _write(corpus["docs"] / "nueva.md", "nota nueva enorme " * 50 + "\n")
    g2 = doc_graph.build_graph()  # sin invalidate: el fingerprint cambió
    assert any(n["id"] == "note:project-docs:docs:nueva.md" for n in g2["nodes"])


def test_ttl_expired_fingerprint_same_serves_cache(corpus, monkeypatch):
    monkeypatch.setattr(doc_graph, "_GRAPH_TTL_SECONDS", 0)
    doc_graph.invalidate_graph_cache()
    doc_graph.build_graph()
    calls = {"n": 0}
    real = doc_graph._read_text

    def counting(path):
        calls["n"] += 1
        return real(path)

    monkeypatch.setattr(doc_graph, "_read_text", counting)
    doc_graph.build_graph()  # TTL vencido pero fingerprint igual → cache, sin leer
    assert calls["n"] == 0


def test_invalidate_graph_cache_forces_rebuild(corpus, monkeypatch):
    doc_graph.invalidate_graph_cache()
    doc_graph.build_graph()
    calls = {"n": 0}
    real = doc_graph._read_text

    def counting(path):
        calls["n"] += 1
        return real(path)

    monkeypatch.setattr(doc_graph, "_read_text", counting)
    doc_graph.invalidate_graph_cache()
    doc_graph.build_graph()
    assert calls["n"] > 0


def test_determinism_two_runs_equal_json(corpus):
    doc_graph.invalidate_graph_cache()
    g1 = doc_graph.build_graph()
    doc_graph.invalidate_graph_cache()
    g2 = doc_graph.build_graph()
    # generated_at es un timestamp (no determinístico por diseño): se excluye.
    g1 = {k: v for k, v in g1.items() if k != "generated_at"}
    g2 = {k: v for k, v in g2.items() if k != "generated_at"}
    assert json.dumps(g1, sort_keys=True) == json.dumps(g2, sort_keys=True)
