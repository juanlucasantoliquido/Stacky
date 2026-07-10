"""tests/test_plan109_doc_health.py — Plan 109 F3.

Clasificador determinístico classify_doc_health con nodos/aristas a mano.
Solo la Regla 3 (INCOMPLETA) usa filesystem (tmp_path como workspace).
"""
from services.doc_graph import classify_doc_health


def _note(nid, source_id, has_fm=False):
    return {"id": nid, "kind": "note", "source_id": source_id,
            "has_frontmatter": has_fm}


def _code_edge(ref):
    return {"source": "note:project-docs:docs:a.md",
            "target": f"code:{ref}", "kind": "code_ref"}


def _wiki_edge():
    return {"source": "note:project-docs:docs:a.md",
            "target": "note:project-docs:docs:b.md", "kind": "wikilink"}


def test_sin_docs_when_no_project_notes():
    nodes = [_note("note:stacky:x.md", "stacky", has_fm=True)]
    r = classify_doc_health(nodes, [], None)
    assert r["status"] == "SIN_DOCS"


def test_formato_no_obsidian():
    nodes = [_note("note:project-docs:docs:a.md", "project-docs:docs"),
             _note("note:project-docs:docs:b.md", "project-docs:docs")]
    r = classify_doc_health(nodes, [], None)
    assert r["status"] == "FORMATO_NO_OBSIDIAN"


def test_formato_ok_with_only_wikilinks():
    nodes = [_note("note:project-docs:docs:a.md", "project-docs:docs")]
    r = classify_doc_health(nodes, [_wiki_edge()], None)
    assert r["status"] != "FORMATO_NO_OBSIDIAN"


def test_incompleta_uncovered_module(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "foo.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "app.tsx").write_text("export {}\n", encoding="utf-8")
    nodes = [_note("note:project-docs:docs:a.md", "project-docs:docs", has_fm=True)]
    r = classify_doc_health(nodes, [_code_edge("backend/foo.py")], str(tmp_path))
    assert r["status"] == "INCOMPLETA"
    assert r["uncovered_modules"] == ["frontend"]


def test_sana_all_modules_covered(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "foo.py").write_text("x=1\n", encoding="utf-8")
    nodes = [_note("note:project-docs:docs:a.md", "project-docs:docs", has_fm=True)]
    r = classify_doc_health(nodes, [_code_edge("backend/foo.py")], str(tmp_path))
    assert r["status"] == "SANA"


def test_excluded_dirs_not_modules(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("x\n", encoding="utf-8")
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    (tmp_path / ".git" / "hooks" / "x.py").write_text("x\n", encoding="utf-8")
    nodes = [_note("note:project-docs:docs:a.md", "project-docs:docs", has_fm=True)]
    r = classify_doc_health(nodes, [], str(tmp_path))
    assert r["status"] == "SANA"
    assert r["uncovered_modules"] == []


def test_no_workspace_root_skips_rule3():
    nodes = [_note("note:project-docs:docs:a.md", "project-docs:docs", has_fm=True)]
    r = classify_doc_health(nodes, [], None)
    assert r["status"] == "SANA"


def test_never_raises_on_garbage():
    nodes = [{"kind": "note"}, {"source_id": None}, {}]
    edges = [{}, {"kind": "wikilink"}, {"target": None}]
    r = classify_doc_health(nodes, edges, None)
    assert r["status"] in {"SIN_DOCS", "FORMATO_NO_OBSIDIAN", "INCOMPLETA", "SANA"}
