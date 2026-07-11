"""Plan 112 F0 — Flags del retrieval híbrido docs-rag (1 bool + 2 float + 1 int).

Rieles: default OFF, bounds declarativos (patrón plan 83), requires contra la
master (patrón plan 82/104), ayuda llana 100% (plan 86).
"""
from __future__ import annotations

from config import config
from services.harness_flags import FLAG_REGISTRY, categorize

_MASTER = "STACKY_DOCS_RAG_HYBRID_ENABLED"
_ALPHA = "STACKY_DOCS_RAG_HYBRID_ALPHA"
_BETA = "STACKY_DOCS_RAG_HYBRID_BETA"
_MAXN = "STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS"
_ALL = (_MASTER, _ALPHA, _BETA, _MAXN)


def _spec(key: str):
    return next(s for s in FLAG_REGISTRY if s.key == key)


def test_flags_registered_in_categories():
    # Activación operador 2026-07-10: el master es una capacidad opt-in;
    # los knobs de tuning quedan en contexto_memoria (requires al master).
    assert categorize(_MASTER) == "capacidades_optin"
    for key in (_ALPHA, _BETA, _MAXN):
        assert categorize(key) == "contexto_memoria", key


def test_hybrid_default_on():
    # Promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON).
    assert config.STACKY_DOCS_RAG_HYBRID_ENABLED is True


def test_numeric_defaults():
    assert config.STACKY_DOCS_RAG_HYBRID_ALPHA == 1.0
    assert config.STACKY_DOCS_RAG_HYBRID_BETA == 0.15
    assert config.STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS == 8


def test_numeric_bounds_declared():
    assert _spec(_ALPHA).min_value == 0.0 and _spec(_ALPHA).max_value == 10.0
    assert _spec(_BETA).min_value == 0.0 and _spec(_BETA).max_value == 10.0
    assert _spec(_MAXN).min_value == 0 and _spec(_MAXN).max_value == 100


def test_numeric_flags_require_master():
    for key in (_ALPHA, _BETA, _MAXN):
        assert _spec(key).requires == _MASTER, key
    # la master NO declara requires (no encadenar — gotcha R4 profundidad-1)
    assert _spec(_MASTER).requires is None


def test_flags_have_plain_help():
    from services.harness_flags_help import PLAIN_HELP
    for key in _ALL:
        assert key in PLAIN_HELP, key
