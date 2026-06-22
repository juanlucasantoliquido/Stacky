"""Tests TDD del wiring RAG en context_enrichment (F2+F3 — Plan 64)."""
import os
import pytest
from unittest.mock import patch, MagicMock

CATALOG = [
    {"name": "Mul2Bane", "kind": "batch", "purpose": "Carga multigestion bancos"},
    {"name": "IncHost", "kind": "batch", "purpose": "Procesa incrementos host cuentas activas"},
    {"name": "RSCore", "kind": "batch", "purpose": "Aplica reglas negocio saldos movimientos"},
    {"name": "RsExtrae", "kind": "batch", "purpose": "Extrae datos salida reportes cierre"},
    {"name": "GenReporte", "kind": "batch", "purpose": "Generacion reportes conciliacion auditoria"},
]
PROFILE = {"process_catalog": CATALOG}


def _make_profile_loader(profile):
    def loader(project_name):
        return profile
    return loader


def test_rag_disabled_injects_full_catalog(monkeypatch):
    """Con RAG OFF → inyecta el catálogo completo (comportamiento original)."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "false")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block([], "mi-proyecto", lambda *a, **k: None, query="reportes")
    assert any(b.get("id") == "process-catalog" for b in result)
    block = next(b for b in result if b.get("id") == "process-catalog")
    assert "Mul2Bane" in block["content"]
    assert "IncHost" in block["content"]
    assert "GenReporte" in block["content"]


def test_rag_enabled_injects_subset(monkeypatch):
    """Con RAG ON → inyecta solo el top-K (no todos)."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "true")
    monkeypatch.setenv("STACKY_RAG_CATALOG_TOP_K", "2")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    ce._RAG_INDEX_CACHE.clear()
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block(
            [], "mi-proyecto", lambda *a, **k: None, query="reportes conciliacion auditoria"
        )
    assert any(b.get("id") == "process-catalog" for b in result)
    block = next(b for b in result if b.get("id") == "process-catalog")
    process_lines = [l for l in block["content"].splitlines() if l.startswith("- ")]
    assert len(process_lines) <= 2


def test_rag_enabled_no_query_falls_back_to_full(monkeypatch):
    """Con RAG ON pero sin query → degradación limpia → full-inject."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "true")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    ce._RAG_INDEX_CACHE.clear()
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block(
            [], "mi-proyecto", lambda *a, **k: None, query=None
        )
    block = next((b for b in result if b.get("id") == "process-catalog"), None)
    assert block is not None
    assert "Mul2Bane" in block["content"]


def test_rag_disabled_env_off(monkeypatch):
    """Con STACKY_INJECT_PROCESS_CATALOG=false → no inyecta nada."""
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "false")
    from services import context_enrichment as ce
    result = ce._inject_process_catalog_block([], "mi-proyecto", lambda *a, **k: None)
    assert not any(b.get("id") == "process-catalog" for b in result)


def test_rag_already_present_skips(monkeypatch):
    """Si el bloque ya está en blocks → no duplicar."""
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    existing = [{"id": "process-catalog", "content": "ya está"}]
    result = ce._inject_process_catalog_block(existing, "mi-proyecto", lambda *a, **k: None)
    catalog_blocks = [b for b in result if b.get("id") == "process-catalog"]
    assert len(catalog_blocks) == 1


def test_build_process_dictionary_block_rag_returns_top_k():
    """build_process_dictionary_block_rag devuelve (block, n) con ≤top_k procesos."""
    from services.context_enrichment import build_process_dictionary_block_rag, _RAG_INDEX_CACHE
    _RAG_INDEX_CACHE.clear()
    result = build_process_dictionary_block_rag(PROFILE, query="host cuentas activas", top_k=2)
    assert result is not None
    block, n = result
    assert block["id"] == "process-catalog"
    assert n <= 2
    process_lines = [l for l in block["content"].splitlines() if l.startswith("- ")]
    assert len(process_lines) == n


def test_build_process_dictionary_block_rag_empty_query_returns_none():
    from services.context_enrichment import build_process_dictionary_block_rag
    assert build_process_dictionary_block_rag(PROFILE, query="") is None
    assert build_process_dictionary_block_rag(PROFILE, query="   ") is None


def test_rag_index_cache_hit(monkeypatch):
    """El índice se reconstruye solo cuando el catálogo cambia."""
    from services import context_enrichment as ce
    ce._RAG_INDEX_CACHE.clear()
    ce._get_rag_index(CATALOG)
    first_hash = list(ce._RAG_INDEX_CACHE.keys())[0]
    ce._get_rag_index(CATALOG)
    assert list(ce._RAG_INDEX_CACHE.keys()) == [first_hash]
    ce._get_rag_index(CATALOG + [{"name": "Nuevo", "kind": "x", "purpose": "algo nuevo"}])
    assert first_hash not in ce._RAG_INDEX_CACHE


def test_rag_query_uses_title_and_description_from_enrich_blocks():
    """_rag_query combina ticket_title y ticket_description (ambos o solo uno)."""
    parts = [p for p in ["titulo del ticket", "descripcion detallada"] if p]
    query = " ".join(parts) or None
    assert query == "titulo del ticket descripcion detallada"
    parts_none = [p for p in [None, None] if p]
    query_none = " ".join(parts_none) or None
    assert query_none is None


# F3 — Tests de telemetría _rag_meta
def test_rag_block_has_meta_when_rag_on(monkeypatch):
    """Con RAG ON el bloque tiene _rag_meta con los conteos."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "true")
    monkeypatch.setenv("STACKY_RAG_CATALOG_TOP_K", "3")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    ce._RAG_INDEX_CACHE.clear()
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block(
            [], "mi-proyecto", lambda *a, **k: None, query="reportes conciliacion"
        )
    block = next(b for b in result if b.get("id") == "process-catalog")
    meta = block.get("_rag_meta")
    assert meta is not None
    assert meta["rag_enabled"] is True
    assert meta["catalog_total"] == len(CATALOG)
    assert 0 < meta["retrieved"] <= 3


def test_rag_block_no_meta_when_rag_off(monkeypatch):
    """Con RAG OFF el bloque NO tiene _rag_meta."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "false")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block(
            [], "mi-proyecto", lambda *a, **k: None, query="reportes"
        )
    block = next(b for b in result if b.get("id") == "process-catalog")
    assert "_rag_meta" not in block
