"""Plan 289 F2 — el contador de enriquecimiento se persiste igual en los 3 runtimes.

NO importa db: la sesion se inyecta por session_factory (P6).
"""
from __future__ import annotations

import contextlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _FilaFalsa:
    def __init__(self, md=None):
        self.metadata_dict = md if md is not None else {}


class _SesionFalsa:
    def __init__(self, fila):
        self._fila = fila
        self.gets = []

    def get(self, modelo, pk):
        self.gets.append((modelo, pk))
        return self._fila


def _factory(fila):
    @contextlib.contextmanager
    def _f():
        yield _SesionFalsa(fila)
    return _f


def test_escribe_la_clave_ado_context_sin_pisar_lo_que_ya_habia():
    from services.context_enrichment import persistir_stats_de_contexto

    fila = _FilaFalsa({"runtime": "codex_cli", "vscode_agent_filename": "X.agent.md"})
    ok = persistir_stats_de_contexto(
        execution_id=42, stats={"comments_count": 3, "errors": []},
        session_factory=_factory(fila),
    )
    assert ok is True
    assert fila.metadata_dict["ado_context"] == {"comments_count": 3, "errors": []}
    assert fila.metadata_dict["runtime"] == "codex_cli"          # no piso lo previo
    assert fila.metadata_dict["vscode_agent_filename"] == "X.agent.md"


def test_stats_none_no_escribe_nada():
    """ado_id ausente -> enrich_blocks devuelve None; no se inventa una clave vacia."""
    from services.context_enrichment import persistir_stats_de_contexto

    fila = _FilaFalsa({"runtime": "claude_code_cli"})
    assert persistir_stats_de_contexto(
        execution_id=1, stats=None, session_factory=_factory(fila)) is False
    assert "ado_context" not in fila.metadata_dict


def test_execution_id_none_no_explota():
    from services.context_enrichment import persistir_stats_de_contexto

    fila = _FilaFalsa()
    assert persistir_stats_de_contexto(
        execution_id=None, stats={"comments_count": 1}, session_factory=_factory(fila)) is False


def test_fila_inexistente_no_explota():
    from services.context_enrichment import persistir_stats_de_contexto

    @contextlib.contextmanager
    def _sin_fila():
        yield types.SimpleNamespace(get=lambda *a, **k: None)

    assert persistir_stats_de_contexto(
        execution_id=999, stats={"comments_count": 1}, session_factory=_sin_fila) is False


def test_metadata_dict_none_se_trata_como_dict_vacio():
    from services.context_enrichment import persistir_stats_de_contexto

    fila = _FilaFalsa(None)
    fila.metadata_dict = None
    assert persistir_stats_de_contexto(
        execution_id=7, stats={"comments_count": 0}, session_factory=_factory(fila)) is True
    assert fila.metadata_dict["ado_context"] == {"comments_count": 0}


def test_una_excepcion_de_la_sesion_no_tumba_el_run():
    """Persistir un contador NUNCA puede romper una ejecucion del agente."""
    from services.context_enrichment import persistir_stats_de_contexto

    @contextlib.contextmanager
    def _rompe():
        raise RuntimeError("database is locked")
        yield  # pragma: no cover

    assert persistir_stats_de_contexto(
        execution_id=5, stats={"comments_count": 2}, session_factory=_rompe) is False
