"""tests/test_plan131_incident_docs.py — Plan 131 F6.

Doc del incidente + aristas en el grafo documental. tmp_path + monkeypatch de
`doc_indexer.STACKY_AGENTS_ROOT` (patrón real de tests/test_doc_indexer.py).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services import doc_indexer, doc_graph, incident_docs

SAMPLE_HTML = """
<h1>[INC] La pantalla de login se rompe</h1>
<h2>ARCHIVOS Y MODULOS PROBABLES</h2>
<ul><li>backend/services/foo.py — hipótesis de causa raíz</li></ul>
"""

SAMPLE_INCIDENT = {
    "id": "inc_20260714_120000_abcdef",
    "created_at": "2026-07-14T12:00:00+00:00",
    "tracker_id": "341",
    "tracker_url": "https://fake.tracker/341",
    "epic_id": 267,
    "status": "publicada",
    "execution_id": 555,
    "work_item_type": "Issue",
}

SAMPLE_RELATED = {"epic_id": 267, "confidence": 85, "reason": "afecta el alta"}


@pytest.fixture(autouse=True)
def _tmp_agents_root(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_indexer, "STACKY_AGENTS_ROOT", tmp_path)
    doc_graph.invalidate_graph_cache()
    yield tmp_path
    doc_graph.invalidate_graph_cache()


def test_write_happy_path_frontmatter_and_wikilink(tmp_path):
    (tmp_path / "docs").mkdir()
    doc_path_str = incident_docs.write_incident_doc(
        SAMPLE_INCIDENT, "[INC] La pantalla de login se rompe", SAMPLE_HTML, SAMPLE_RELATED,
    )
    assert doc_path_str is not None
    doc_path = Path(doc_path_str)
    assert doc_path.exists()
    assert doc_path.name == "INC-341_inc-la-pantalla-de-login-se-rompe.md"
    content = doc_path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "incident_id: inc_20260714_120000_abcdef" in content
    assert "tracker_id: 341" in content
    assert "epica: 267" in content
    assert "execution_id: 555" in content
    assert "[[INDICE_INCIDENCIAS]]" in content


def test_index_created_if_missing_and_no_duplicate_on_rewrite(tmp_path):
    (tmp_path / "docs").mkdir()
    incident_docs.write_incident_doc(
        SAMPLE_INCIDENT, "[INC] La pantalla de login se rompe", SAMPLE_HTML, SAMPLE_RELATED,
    )
    index_path = tmp_path / "docs" / "incidencias" / "INDICE_INCIDENCIAS.md"
    assert index_path.exists()
    first_content = index_path.read_text(encoding="utf-8")
    assert first_content.count("[[INC-341_inc-la-pantalla-de-login-se-rompe]]") == 1

    # Segunda escritura del MISMO incidente → NO duplica la línea del índice.
    incident_docs.write_incident_doc(
        SAMPLE_INCIDENT, "[INC] La pantalla de login se rompe", SAMPLE_HTML, SAMPLE_RELATED,
    )
    second_content = index_path.read_text(encoding="utf-8")
    assert second_content.count("[[INC-341_inc-la-pantalla-de-login-se-rompe]]") == 1


def test_slugify_accents_symbols_cap_60():
    slug = incident_docs._slugify("¡Título con Ácentos y Símbolos raros!! " + "x" * 80)
    assert slug == slug.lower()
    assert all(c.isalnum() or c == "-" for c in slug)
    assert len(slug) <= 60


def test_write_without_docs_root_uses_fallback(tmp_path, monkeypatch):
    # tmp_path/docs NO existe → fallback a data_dir()/incident_docs.
    fallback_dir = tmp_path / "fallback_data"
    monkeypatch.setattr("runtime_paths.data_dir", lambda: fallback_dir)

    doc_path_str = incident_docs.write_incident_doc(
        SAMPLE_INCIDENT, "[INC] La pantalla de login se rompe", SAMPLE_HTML, SAMPLE_RELATED,
    )
    assert doc_path_str is not None
    doc_path = Path(doc_path_str)
    assert doc_path.exists()
    assert str(fallback_dir.resolve()) in str(doc_path)


def test_invalidate_graph_cache_invoked(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    calls = {"count": 0}

    def _spy():
        calls["count"] += 1

    monkeypatch.setattr("services.doc_graph.invalidate_graph_cache", _spy)

    incident_docs.write_incident_doc(
        SAMPLE_INCIDENT, "[INC] La pantalla de login se rompe", SAMPLE_HTML, SAMPLE_RELATED,
    )
    assert calls["count"] == 1


def test_integration_graph_node_with_wikilink_and_code_edges(tmp_path, monkeypatch):
    """KPI-3: el .md del incidente aparece como nodo con >=1 arista doc->doc
    (wikilink al índice) y >=1 arista doc->código (backend/services/foo.py)."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "dummy.md").write_text("Nota dummy sin links\n", encoding="utf-8")
    (tmp_path / "backend" / "services").mkdir(parents=True)
    (tmp_path / "backend" / "services" / "foo.py").write_text("print('hi')\n", encoding="utf-8")

    doc_path_str = incident_docs.write_incident_doc(
        SAMPLE_INCIDENT, "[INC] La pantalla de login se rompe", SAMPLE_HTML, SAMPLE_RELATED,
    )
    assert doc_path_str is not None

    def _walk_md_files(root: Path) -> list[dict]:
        out = []
        for p in sorted(root.rglob("*.md")):
            rel = p.relative_to(root).as_posix()
            out.append({"kind": "file", "path": rel, "source_id": "project-docs:docs", "children": []})
        return out

    def fake_list_doc_sources(project_name=None):
        return {
            "ok": True,
            "active_project": "TEST",
            "workspace_root": str(tmp_path),
            "sources": [
                {"id": "project-docs:docs", "kind": "project-docs", "label": "docs",
                 "relative_path": "docs", "absolute_path": str(docs)},
            ],
        }

    def fake_build_project_docs_index(project_name=None, source_id=None):
        return {"roots": [{"children": _walk_md_files(docs)}]}

    def fake_build_index(vscode_prompts_dir=None):
        return {"roots": []}

    monkeypatch.setattr(doc_indexer, "list_doc_sources", fake_list_doc_sources)
    monkeypatch.setattr(doc_indexer, "build_project_docs_index", fake_build_project_docs_index)
    monkeypatch.setattr(doc_indexer, "build_index", fake_build_index)
    doc_graph.invalidate_graph_cache()

    graph = doc_graph.build_graph()
    doc_node_id = "note:project-docs:docs:incidencias/INC-341_inc-la-pantalla-de-login-se-rompe.md"
    node_ids = {n["id"] for n in graph["nodes"]}
    assert doc_node_id in node_ids, sorted(node_ids)

    outgoing = [e for e in graph["edges"] if e["source"] == doc_node_id]
    assert len(outgoing) >= 1
    wikilink_targets = {
        e["target"] for e in outgoing
        if "indice_incidencias" in e["target"].lower() or "indice-incidencias" in e["target"].lower()
    }
    assert wikilink_targets, [e for e in outgoing]

    code_edges = [e for e in outgoing if e["target"].startswith("code:")]
    assert any("foo.py" in e["target"] for e in code_edges), outgoing
