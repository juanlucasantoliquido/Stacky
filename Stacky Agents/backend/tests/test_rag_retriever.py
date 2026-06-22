"""Tests TDD de services/rag_retriever.py (F0 — Plan 64)."""
import pytest
from services.rag_retriever import (
    RagChunk, build_index, retrieve, chunks_from_process_catalog, _tokenize,
)

CATALOG = [
    {"name": "Mul2Bane", "kind": "batch", "purpose": "Carga multigestion de bancos y entidades financieras"},
    {"name": "IncHost", "kind": "batch", "purpose": "Procesa incrementos de host para cuentas activas productivas"},
    {"name": "RSCore", "kind": "batch", "purpose": "Aplica reglas de negocio centrales sobre saldos y movimientos"},
    {"name": "RsExtrae", "kind": "batch", "purpose": "Extrae datos de salida y genera reportes de cierre"},
    {"name": "GenReporte", "kind": "batch", "purpose": "Generacion de reportes de conciliacion y auditoria"},
]


def test_chunks_from_catalog_length():
    chunks = chunks_from_process_catalog(CATALOG)
    assert len(chunks) == len(CATALOG)


def test_chunks_from_catalog_ids_unique():
    chunks = chunks_from_process_catalog(CATALOG)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunks_from_catalog_skips_empty():
    partial = [{"name": "", "kind": "batch", "purpose": "algo"}, CATALOG[0]]
    chunks = chunks_from_process_catalog(partial)
    assert len(chunks) == 1


def test_build_index_empty():
    idx = build_index([])
    assert idx.chunks == []
    assert idx.tf_vecs == []


def test_build_index_non_empty():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    assert len(idx.chunks) == len(CATALOG)
    assert len(idx.tf_vecs) == len(CATALOG)
    assert len(idx.idf) > 0


def test_retrieve_returns_top_k():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "reportes de conciliacion y auditoria", top_k=2)
    assert len(results) == 2
    # El chunk de GenReporte debe estar primero (mayor similitud)
    top_id = results[0][0].id
    assert top_id == "genreporte"


def test_retrieve_scores_descending():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "bancos entidades financieras", top_k=5)
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_empty_query_returns_empty():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    assert retrieve(idx, "", top_k=3) == []
    assert retrieve(idx, "   ", top_k=3) == []


def test_retrieve_top_k_zero_returns_empty():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    assert retrieve(idx, "algo", top_k=0) == []


def test_retrieve_top_k_greater_than_corpus():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "proceso batch", top_k=100)
    assert len(results) == len(CATALOG)  # nunca más que el corpus


def test_retrieve_payload_intact():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "host cuentas activas", top_k=1)
    assert results[0][0].payload["name"] == "IncHost"


def test_tokenize_basic():
    tokens = _tokenize("Mul2Bane carga multigestion")
    assert "multigestion" in tokens


def test_retrieve_no_crash_on_single_chunk():
    chunks = [RagChunk(id="x", text="proceso unico especial", payload={})]
    idx = build_index(chunks)
    results = retrieve(idx, "proceso especial", top_k=3)
    assert len(results) == 1
    assert results[0][1] > 0.0


def test_content_hash_stored():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks, content_hash="abc123")
    assert idx.content_hash == "abc123"


# [ADICIÓN ARQUITECTO v2] — Discriminación de vocabulario real RSPACIFICO
def test_domain_discrimination_mul2bane():
    """'multigestion bancos entidades' debe recuperar Mul2Bane como top-1."""
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "multigestion bancos entidades", top_k=3)
    assert len(results) > 0
    assert results[0][0].payload["name"] == "Mul2Bane", (
        f"Esperaba Mul2Bane como top-1, obtuve {results[0][0].payload['name']}"
    )


def test_domain_discrimination_reporte():
    """'conciliacion auditoria reportes' debe recuperar GenReporte como top-1."""
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "conciliacion auditoria reportes", top_k=3)
    assert len(results) > 0
    assert results[0][0].payload["name"] == "GenReporte", (
        f"Esperaba GenReporte como top-1, obtuve {results[0][0].payload['name']}"
    )
