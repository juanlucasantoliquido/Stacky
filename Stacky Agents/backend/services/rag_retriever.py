"""RAG local: TF-IDF puro sin dependencias externas.

Funciones puras: sin estado global, sin red, sin LLM.
Compatible con Python 3.10+ stdlib (math, re, collections).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from services import lexical_core  # Plan 115 — núcleo léxico TF-IDF compartido


@dataclass(frozen=True)
class RagChunk:
    id: str          # identificador estable del chunk (ej. process name slug)
    text: str        # texto plano del chunk (para scoring)
    payload: dict    # datos originales (se devuelve intacto al llamador)


@dataclass
class RagIndex:
    chunks: list[RagChunk]
    idf: dict[str, float]           # term -> idf score
    tf_vecs: list[dict[str, float]] # un dict tf por chunk, alineado con chunks[]
    # Cache key: hash del contenido original para invalidar automáticamente.
    content_hash: str = ""


# Plan 115 — política de tokenización que REPLICA el tokenizer original de
# rag_retriever (lowercase del texto, pattern con \w, min 2 chars, sin stopwords).
_TOKENIZE_OPTS = lexical_core.TokenizeOptions(
    pattern=r"[a-záéíóúüñ\w]{2,}", lowercase_text=True,
    lowercase_token=False, min_len=2,
)


def _tokenize(text: str) -> list[str]:
    """Tokenización simple: lower, solo alfanum + guión/subguión, min 2 chars."""
    return lexical_core.tokenize(text, _TOKENIZE_OPTS)


def _tf(tokens: list[str]) -> dict[str, float]:
    # (C1) rag_retriever usa frecuencia RELATIVA (count/n), NO conteos crudos.
    return lexical_core.normalized_term_frequencies(tokens)


def _build_idf(token_sets: list[set[str]], n_docs: int) -> dict[str, float]:
    # Fórmula idéntica: log((1+n_docs)/(1+df)) + 1.0. n_docs == len(token_sets).
    return lexical_core.inverse_doc_frequencies(token_sets)


def _tfidf_vec(tf: dict[str, float], idf: dict[str, float]) -> dict[str, float]:
    return {term: tf_val * idf.get(term, 1.0) for term, tf_val in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    # Vectores YA ponderados por IDF → coseno crudo (idf neutro {} ⇒ pesos 1.0).
    return lexical_core.cosine_tfidf(a, b, {})


def build_index(chunks: Sequence[RagChunk], content_hash: str = "") -> RagIndex:
    """Construye el índice TF-IDF a partir de una lista de chunks. O(N*V)."""
    chunk_list = list(chunks)
    if not chunk_list:
        return RagIndex(chunks=[], idf={}, tf_vecs=[], content_hash=content_hash)
    tokenized = [_tokenize(c.text) for c in chunk_list]
    token_sets = [set(t) for t in tokenized]
    idf = _build_idf(token_sets, len(chunk_list))
    tf_vecs = [_tfidf_vec(_tf(tokens), idf) for tokens in tokenized]
    return RagIndex(chunks=chunk_list, idf=idf, tf_vecs=tf_vecs, content_hash=content_hash)


def retrieve(index: RagIndex, query: str, top_k: int = 8) -> list[tuple[RagChunk, float]]:
    """Devuelve los top_k chunks más similares al query, ordenados por score desc.

    Retorna lista de (chunk, score). Si el índice está vacío o top_k<=0, devuelve [].
    Nunca lanza; score mínimo = 0.0.
    """
    if not index.chunks or top_k <= 0 or not query.strip():
        return []
    q_tokens = _tokenize(query)
    q_tf = _tf(q_tokens)
    q_vec = _tfidf_vec(q_tf, index.idf)
    scored = [
        (chunk, _cosine(q_vec, tv))
        for chunk, tv in zip(index.chunks, index.tf_vecs)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def chunks_from_process_catalog(catalog: list[dict]) -> list[RagChunk]:
    """Convierte el process_catalog de client_profile en chunks indexables.

    Cada proceso = un chunk. El texto es: name + kind + purpose (concatenados).
    El payload es el dict original del proceso para reconstruir el bloque.
    El id es el slug del name (lowercase, spaces->guión).
    """
    result: list[RagChunk] = []
    for p in (catalog or []):
        name = (p.get("name") or "").strip()
        purpose = (p.get("purpose") or "").strip()
        kind = (p.get("kind") or "otro").strip()
        if not name or not purpose:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        text = f"{name} {kind} {purpose}"
        result.append(RagChunk(id=slug, text=text, payload=p))
    return result
