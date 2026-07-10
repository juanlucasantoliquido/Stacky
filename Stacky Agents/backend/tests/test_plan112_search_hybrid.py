"""Plan 112 F2 — search_hybrid + _rerank_with_backlinks (expansión 1-hop + prior).

Corpus fake en DB de test + monkeypatch de _build_backlink_index para inyectar
backlinks/neighbors deterministas. Incluye el KPI central (recall estructural).
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from services import docs_rag
from services.docs_rag import DocChunk, DocHit

db.init_db()


def _seed(project, file_path, text, heading=""):
    tf, norm = docs_rag._compute_tf(text)
    with db.session_scope() as s:
        s.add(DocChunk(project_name=project, file_path=file_path,
                       section_heading=heading, chunk_text=text,
                       term_freqs_json=docs_rag.json.dumps(dict(tf)),
                       doc_norm=norm))


def _clear(project):
    with db.session_scope() as s:
        s.query(DocChunk).filter_by(project_name=project).delete()
    docs_rag._invalidate_idf(project)


def test_degrades_to_search_when_no_graph(monkeypatch):
    _clear("D1")
    _seed("D1", "a.md", "manzana pera banana")
    _seed("D1", "b.md", "auto camion moto")
    monkeypatch.setattr(docs_rag, "_build_backlink_index", lambda p: ({}, {}))
    plain = docs_rag.search("D1", "manzana", top_k=5)
    hyb = docs_rag.search_hybrid("D1", "manzana", top_k=5)
    assert [h.to_dict() for h in hyb] == [h.to_dict() for h in plain]


def test_pulls_neighbor_note_chunk(monkeypatch):
    # KPI CENTRAL: término solo en a.md; respuesta en b.md (vecina, sin el término).
    _clear("K1")
    _seed("K1", "a.md", "instalacion configuracion requisitos previos")
    _seed("K1", "b.md", "detalle procedimiento pasos finales verificacion")
    monkeypatch.setattr(docs_rag, "_build_backlink_index",
                        lambda p: ({"a.md": 0, "b.md": 0}, {"a.md": ["b.md"], "b.md": ["a.md"]}))
    plain_files = {h.file_path for h in docs_rag.search("K1", "instalacion", top_k=5)}
    hyb_files = {h.file_path for h in docs_rag.search_hybrid("K1", "instalacion", top_k=5)}
    assert "b.md" not in plain_files      # léxico puro NO trae la vecina
    assert "b.md" in hyb_files            # híbrido SÍ la trae


def test_backlink_prior_reorders_hubs():
    # (C5) valores exactos: A score 0.50 bl=0 vs B score 0.48 bl=10, alpha=1 beta=0.15.
    a = DocHit("a.md", "", "A", 0.50)
    b = DocHit("b.md", "", "B", 0.48)
    ranked = docs_rag._rerank_with_backlinks([a, b], {"a.md": 0, "b.md": 10}, 1.0, 0.15)
    key_b = 0.48 + 0.15 * math.log1p(10)
    assert key_b > 0.50           # sanity del cálculo esperado (~0.8397)
    assert ranked[0].file_path == "b.md"


def test_max_neighbors_zero_still_reranks(monkeypatch):
    _clear("M1")
    _seed("M1", "a.md", "alpha beta gamma")
    _seed("M1", "b.md", "delta epsilon zeta")
    monkeypatch.setattr(docs_rag, "_read_hybrid_weights", lambda: (1.0, 0.15, 0))
    monkeypatch.setattr(docs_rag, "_build_backlink_index",
                        lambda p: ({"a.md": 0}, {"a.md": ["b.md"]}))
    files = {h.file_path for h in docs_rag.search_hybrid("M1", "alpha", top_k=5)}
    assert "b.md" not in files    # maxn=0 → sin expansión
    assert "a.md" in files        # pero el rerank corrió (a.md sigue presente)


def test_does_not_mutate_base_hits(monkeypatch):
    _clear("N1")
    _seed("N1", "a.md", "unico termino especifico")
    monkeypatch.setattr(docs_rag, "_build_backlink_index",
                        lambda p: ({"a.md": 5}, {"a.md": []}))
    base = docs_rag.search("N1", "especifico", top_k=5)
    scores_before = [h.score for h in base]
    docs_rag.search_hybrid("N1", "especifico", top_k=5)
    assert [h.score for h in base] == scores_before  # search hits intactos


def test_stable_on_ties():
    hits = [DocHit(f"f{i}.md", "", "x", 0.5) for i in range(5)]
    ranked = docs_rag._rerank_with_backlinks(hits, {}, 1.0, 0.15)
    assert [h.file_path for h in ranked] == [f"f{i}.md" for i in range(5)]


def test_result_count_capped(monkeypatch):
    _clear("C1")
    _seed("C1", "a.md", "raiz comun palabra")
    neigh = [f"n{i}.md" for i in range(20)]
    for f in neigh:
        _seed("C1", f, "relleno contenido vecino adicional")
        _seed("C1", f, "segundo chunk del vecino")  # 2 chunks c/u
    monkeypatch.setattr(docs_rag, "_build_backlink_index",
                        lambda p: ({}, {"a.md": neigh}))
    res = docs_rag.search_hybrid("C1", "raiz", top_k=5)
    assert len(res) <= 15
