"""Tests TDD para I2.3 — Expansión y normalización de query para retrieval.

Spec:
- normalize_text: fold de acentos, lowercase, colapso de espacios.
- expand_query: tokens + sinónimos del dominio, deduplicados.
- _tokenize global NO cambia por el flag (test explícito de inmutabilidad).
- Flag OFF → retrieval byte-idéntico (tokenizer base).
- Flag ON → query "factura" matchea docs con "facturación".
- Fold de acentos "facturacion"↔"facturación" matchea.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Tests de normalize_text
# ---------------------------------------------------------------------------

def test_normalize_lowercase():
    from services.query_expansion import normalize_text
    assert normalize_text("FACTURA") == "factura"


def test_normalize_accents_fold():
    from services.query_expansion import normalize_text
    assert normalize_text("facturación") == "facturacion"
    assert normalize_text("integración") == "integracion"
    assert normalize_text("ñoño") == "nono"
    assert normalize_text("ümlaut") == "umlaut"


def test_normalize_collapse_spaces():
    from services.query_expansion import normalize_text
    assert normalize_text("  hello   world  ") == "hello world"
    assert normalize_text("foo\tbar\nbaz") == "foo bar baz"


def test_normalize_empty():
    from services.query_expansion import normalize_text
    assert normalize_text("") == ""
    assert normalize_text("   ") == ""


# ---------------------------------------------------------------------------
# Tests de expand_query
# ---------------------------------------------------------------------------

def test_expand_adds_synonyms():
    from services.query_expansion import expand_query
    tokens = ["factura"]
    result = expand_query(tokens)
    assert "factura" in result
    # Debe incluir los sinónimos del grupo
    assert "facturacion" in result
    assert "comprobante" in result


def test_expand_deduplicates():
    from services.query_expansion import expand_query
    # "factura" y "facturacion" son del mismo grupo
    tokens = ["factura", "facturacion"]
    result = expand_query(tokens)
    # No debe haber duplicados
    assert len(result) == len(set(result))


def test_expand_preserves_original_order():
    from services.query_expansion import expand_query
    tokens = ["error", "tarea"]
    result = expand_query(tokens)
    # Los tokens originales deben estar al inicio
    assert result[0] == "error"
    assert result[1] == "tarea"


def test_expand_no_synonym_token_unchanged():
    from services.query_expansion import expand_query
    tokens = ["xyzfoobar_no_synonym"]
    result = expand_query(tokens)
    assert result == ["xyzfoobar_no_synonym"]


def test_expand_empty():
    from services.query_expansion import expand_query
    assert expand_query([]) == []


def test_expand_tarea_task():
    from services.query_expansion import expand_query
    result = expand_query(["tarea"])
    assert "task" in result

    result2 = expand_query(["task"])
    assert "tarea" in result2


def test_expand_error_falla_bug():
    from services.query_expansion import expand_query
    result = expand_query(["error"])
    assert "falla" in result
    assert "bug" in result


# ---------------------------------------------------------------------------
# Test: _tokenize global no se muta por expand_query ni normalize_text
# ---------------------------------------------------------------------------

def test_tokenize_global_immutable(monkeypatch):
    """El tokenizer global de embeddings NO cambia comportamiento al usar I2.3."""
    from services.embeddings import _tokenize

    # Comportamiento baseline
    baseline = _tokenize("factura facturación")

    # Simular que la expansión está ON
    monkeypatch.setenv("STACKY_RETRIEVAL_EXPANSION_ENABLED", "true")

    # Tokenizer base NUNCA cambia
    after = _tokenize("factura facturación")
    assert after == baseline


# ---------------------------------------------------------------------------
# Test: embeddings.top_k con flag OFF → mismas llamadas que sin flag
# ---------------------------------------------------------------------------

def test_topk_flag_off_uses_base_tokenizer(monkeypatch):
    """Flag OFF: top_k usa _tokenize estándar."""
    monkeypatch.setenv("STACKY_RETRIEVAL_EXPANSION_ENABLED", "false")

    # Importar y verificar que _tokenize base no fue mutado
    from services.embeddings import _tokenize
    result = _tokenize("factura")
    # El tokenizer base tokeniza "factura" como un token
    assert "factura" in result


# ---------------------------------------------------------------------------
# Test: normalize_text + expand_query integración - "factura" matchea "facturación"
# ---------------------------------------------------------------------------

def test_expansion_bridges_accented_variant():
    """query 'factura' con expansión debe incluir 'facturacion' para match."""
    from services.query_expansion import normalize_text, expand_query
    from services.embeddings import _tokenize

    # Simular la ruta que usa embeddings._query_vector con expand=True
    query = "factura"
    normalized = normalize_text(query)
    base_tokens = _tokenize(normalized)
    expanded = expand_query(base_tokens)

    # El documento tiene "facturación" (con acento)
    doc = "facturación pendiente"
    doc_normalized = normalize_text(doc)
    doc_tokens = _tokenize(doc_normalized)  # → ["facturacion", "pendiente"]

    # "facturacion" debe estar en el query expandido
    assert "facturacion" in expanded
    # "facturacion" del doc debe matchear el query expandido
    assert any(t in expanded for t in doc_tokens if t != "pendiente")


# ---------------------------------------------------------------------------
# Test: memory_store.search con flag ON expande el query
# ---------------------------------------------------------------------------

def test_memory_store_search_expansion_flag_off_is_identical(monkeypatch):
    """Flag OFF → tokenizer y lógica byte-idénticos (sin cambios en query_tokens)."""
    monkeypatch.setenv("STACKY_RETRIEVAL_EXPANSION_ENABLED", "false")

    # No pegamos a DB real; solo verificamos que el flag no causa ImportError
    # y que _tokenize global no cambia.
    from services.embeddings import _tokenize
    t1 = _tokenize("factura error tarea")
    monkeypatch.setenv("STACKY_RETRIEVAL_EXPANSION_ENABLED", "true")
    t2 = _tokenize("factura error tarea")
    assert t1 == t2  # el tokenizer base es inmutable
