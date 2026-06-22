"""Test de performance del RAG (F4 — Plan 64). No debe superar 100 ms para N=500."""
import time
import pytest
from services.rag_retriever import build_index, retrieve, chunks_from_process_catalog


def _synthetic_catalog(n: int) -> list[dict]:
    return [
        {
            "name": f"Proceso{i:04d}",
            "kind": "batch",
            "purpose": f"Procesamiento de datos financieros tipo {i % 20} con validacion de saldos y movimientos",
        }
        for i in range(n)
    ]


def test_retriever_perf_500_chunks():
    """build_index + retrieve sobre 500 chunks debe completar en <100 ms."""
    catalog = _synthetic_catalog(500)
    chunks = chunks_from_process_catalog(catalog)
    t0 = time.perf_counter()
    index = build_index(chunks)
    results = retrieve(index, "validacion saldos movimientos financieros", top_k=8)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 100, f"RAG tardó {elapsed_ms:.1f} ms para N=500 (límite: 100 ms)"
    assert len(results) == 8


def test_retriever_perf_cache_hit_negligible():
    """Segunda llamada a _get_rag_index con mismo catálogo no reconstruye el índice (< 5 ms)."""
    from services.context_enrichment import _get_rag_index, _RAG_INDEX_CACHE
    _RAG_INDEX_CACHE.clear()
    catalog = _synthetic_catalog(200)
    _get_rag_index(catalog)  # build
    t0 = time.perf_counter()
    _get_rag_index(catalog)  # cache hit
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 5, f"Cache hit tardó {elapsed_ms:.1f} ms (límite: 5 ms)"
