"""services/lexical_core.py — Plan 115 · Núcleo léxico compartido (TF-IDF).

Funciones PURAS (sin estado, sin red, sin LLM, sin deps) que concentran la
matemática léxica antes duplicada en `rag_retriever.py`, `docs_rag.py` y
`memory_store.py`. Refactor de higiene: comportamiento observable IDÉNTICO
(mismos scores/rankings). Cada consumidor pasa su `TokenizeOptions` para
REPLICAR su tokenizer actual — no se unifica el comportamiento, solo el código.

Fórmula IDF (idéntica en los 3 motores relevados): log((1+n_docs)/(1+df)) + 1.0.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenizeOptions:
    """Política de tokenización que replica EXACTAMENTE cada motor.

    - `pattern`: regex de tokens (string).
    - `ignorecase`: aplica re.IGNORECASE al findall.
    - `lowercase_text`: baja a minúsculas el TEXTO antes de matchear (rag_retriever).
    - `lowercase_token`: baja a minúsculas cada TOKEN matcheado (docs_rag/memory).
    - `min_len`: descarta tokens más cortos (post-filtro).
    - `stopwords`: set de tokens (ya en minúsculas) a descartar.
    """
    pattern: str = r"[a-záéíóúñ0-9]{3,}"
    ignorecase: bool = False
    lowercase_text: bool = False
    lowercase_token: bool = True
    min_len: int = 1
    stopwords: frozenset = frozenset()


def tokenize(text: str, opts: TokenizeOptions = TokenizeOptions()) -> list[str]:
    t = text or ""
    if opts.lowercase_text:
        t = t.lower()
    flags = re.IGNORECASE if opts.ignorecase else 0
    toks = re.findall(opts.pattern, t, flags)
    out: list[str] = []
    for tok in toks:
        if opts.lowercase_token:
            tok = tok.lower()
        if len(tok) < opts.min_len:
            continue
        if tok in opts.stopwords:
            continue
        out.append(tok)
    return out


def term_frequencies(tokens: list[str]) -> dict[str, int]:
    """Conteos CRUDOS. Los usan docs_rag y memory_store (hoy también crudo)."""
    return dict(Counter(tokens))


def normalized_term_frequencies(tokens: list[str]) -> dict[str, float]:
    """(C1) Frecuencia RELATIVA (count / total). La usa rag_retriever: su `_tf`
    divide por len(tokens). Migrarlo con `term_frequencies` (crudo) cambiaría
    TODOS sus scores y rompería su golden."""
    n = len(tokens)
    if n == 0:
        return {}
    return {term: c / n for term, c in Counter(tokens).items()}


def inverse_doc_frequencies(doc_term_sets) -> dict[str, float]:
    """IDF suavizada, idéntica a los 3 motores: log((1+n_docs)/(1+df)) + 1.0.

    doc_term_sets: iterable de conjuntos de términos (uno por documento).
    n_docs == 0 → {} (mismo que docs_rag/memory con corpus vacío)."""
    docs = list(doc_term_sets)
    n_docs = len(docs)
    if n_docs == 0:
        return {}
    df: Counter = Counter()
    for s in docs:
        for term in s:
            df[term] += 1
    return {t: math.log((1 + n_docs) / (1 + c)) + 1.0 for t, c in df.items()}


def cosine_tfidf(query_tf, doc_tf, idf) -> float:
    """Coseno entre query y doc, ambos ponderados por IDF. Devuelve 0.0 si algún
    vector es vacío/nulo. Replica el coseno de los 3 motores (dot / (|q|·|d|))."""
    if not query_tf or not doc_tf:
        return 0.0
    qv = {t: query_tf[t] * idf.get(t, 1.0) for t in query_tf}
    dv = {t: doc_tf.get(t, 0) * idf.get(t, 1.0) for t in doc_tf}
    dot = sum(qv[t] * dv.get(t, 0.0) for t in qv)
    qn = math.sqrt(sum(v * v for v in qv.values()))
    dn = math.sqrt(sum(v * v for v in dv.values()))
    if qn == 0.0 or dn == 0.0:
        return 0.0
    return dot / (qn * dn)
