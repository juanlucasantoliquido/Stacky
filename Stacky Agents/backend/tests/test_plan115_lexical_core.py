"""Plan 115 F1 — unit tests puros del núcleo léxico compartido."""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import lexical_core as lc


def test_tokenize_docs_policy_min3_stopwords():
    opts = lc.TokenizeOptions(
        pattern=r"[a-záéíóúñ0-9]{3,}", ignorecase=True,
        lowercase_token=True, stopwords=frozenset({"los"}),
    )
    assert lc.tokenize("Los Datos ABC de x", opts) == ["datos", "abc"]


def test_tokenize_rag_policy_min2_lowercase_text():
    opts = lc.TokenizeOptions(
        pattern=r"[a-záéíóúüñ\w]{2,}", lowercase_text=True,
        lowercase_token=False, min_len=2,
    )
    assert lc.tokenize("Hola Mundo AB", opts) == ["hola", "mundo", "ab"]


def test_normalized_term_frequencies_divides_by_length():
    assert lc.normalized_term_frequencies(["a", "a", "b"]) == {"a": 2 / 3, "b": 1 / 3}
    assert lc.normalized_term_frequencies([]) == {}


def test_term_frequencies_stays_raw_counts():
    assert lc.term_frequencies(["a", "a", "b"]) == {"a": 2, "b": 1}


def test_inverse_doc_frequencies_formula():
    sets = [{"a", "b"}, {"a"}]  # n=2, df(a)=2, df(b)=1
    idf = lc.inverse_doc_frequencies(sets)
    assert idf["a"] == math.log((1 + 2) / (1 + 2)) + 1.0  # log(1)+1 = 1.0
    assert idf["b"] == math.log((1 + 2) / (1 + 1)) + 1.0
    assert lc.inverse_doc_frequencies([]) == {}


def test_cosine_tfidf_known_values():
    idf = {"a": 1.0, "b": 1.0}
    assert lc.cosine_tfidf({"a": 1}, {"a": 1}, idf) == 1.0  # vectores idénticos
    assert lc.cosine_tfidf({"a": 1}, {"b": 1}, idf) == 0.0  # ortogonales
    assert lc.cosine_tfidf({}, {"a": 1}, idf) == 0.0
    assert lc.cosine_tfidf({"a": 1}, {}, idf) == 0.0
