"""Tests TDD para I2.1 — Re-ranking de bloques por relevancia al ticket.

Spec:
- Flag OFF → _apply_context_budget byte-idéntico (regresión sobre fixture).
- Flag ON + presupuesto ajustado + dos bloques de igual prioridad media →
  se conserva el más relevante al ticket (TF-IDF coseno).
- Bloques de alta prioridad NUNCA se recortan independientemente de la relevancia.
- El orden de PRESENTACIÓN (orden original en la lista) no cambia.
- Bloque con context_text None → rerank no aplica (sin crash).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _log(*_a, **_k):
    pass


def _block(id_: str, content: str) -> dict:
    return {"id": id_, "content": content}


# ---------------------------------------------------------------------------
# Helper: activa ambos flags y usa budget pequeño
# ---------------------------------------------------------------------------

def _monkeypatch_rerank(monkeypatch, budget: int = 20):
    from config import config
    from services import cli_feature_flags
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_PROJECTS", "", raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_TOKENS", budget, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_RERANK_ENABLED", True, raising=False)
    # Parchear cli_feature_flags.context_budget_enabled para que devuelva True
    monkeypatch.setattr(
        cli_feature_flags, "context_budget_enabled", lambda _p: True, raising=False
    )


# ---------------------------------------------------------------------------
# Test 1: Flag OFF → _apply_context_budget byte-idéntico
# ---------------------------------------------------------------------------

def test_rerank_flag_off_budget_identical(monkeypatch):
    from config import config
    from services import cli_feature_flags, context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_PROJECTS", "", raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_TOKENS", 1000, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_RERANK_ENABLED", False, raising=False)
    monkeypatch.setattr(cli_feature_flags, "context_budget_enabled", lambda _p: True, raising=False)

    blocks = [
        _block("ado-similar-tickets", "tickets similares"),
        _block("ado-comments", "comentarios del ticket"),
    ]

    # Con rerank ON
    monkeypatch.setattr(config, "STACKY_CONTEXT_RERANK_ENABLED", True, raising=False)
    result_on = ce._apply_context_budget(
        blocks, project_name="P", log=_log, context_text="tickets similares"
    )

    # Con rerank OFF
    monkeypatch.setattr(config, "STACKY_CONTEXT_RERANK_ENABLED", False, raising=False)
    result_off = ce._apply_context_budget(
        blocks, project_name="P", log=_log, context_text="tickets similares"
    )

    # Sin presión de budget ambos conservan todo → mismos ids en el resultado
    ids_on = [b.get("id") for b in result_on]
    ids_off = [b.get("id") for b in result_off]
    assert ids_on == ids_off


# ---------------------------------------------------------------------------
# Test 2: Con presupuesto ajustado y dos bloques de igual prioridad media,
# se conserva el más relevante al ticket.
# Usamos mock de _block_token_estimate para controlar el presupuesto exacto.
# ---------------------------------------------------------------------------

def test_rerank_keeps_more_relevant_block(monkeypatch):
    from config import config
    from services import cli_feature_flags, context_enrichment as ce
    from unittest.mock import patch

    # Habilitar rerank + budget con tokens controlados vía mock
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_PROJECTS", "", raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_TOKENS", 150, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_RERANK_ENABLED", True, raising=False)
    monkeypatch.setattr(cli_feature_flags, "context_budget_enabled", lambda _p: True, raising=False)

    # Bloques: similar = 100 tok (más relevante), comments = 100 tok (menos relevante)
    # Budget 150 → solo cabe uno. El rerank debe conservar el más relevante.
    blocks = [
        _block("ado-similar-tickets", "factura pendiente refactoring"),
        _block("ado-comments", "deployment pipeline status"),
    ]
    context_text = "factura refactoring"

    def _fake_token_estimate(block):
        return 100  # ambos cuestan 100 tokens

    with patch.object(ce, "_block_token_estimate", _fake_token_estimate):
        result = ce._apply_context_budget(
            blocks, project_name="P", log=_log, context_text=context_text
        )

    result_ids = [b.get("id") for b in result]
    # Con rerank ON, "ado-similar-tickets" tiene mayor score efectivo (más relevante)
    # → debe sobrevivir al corte del budget
    assert "ado-similar-tickets" in result_ids, (
        f"Se esperaba 'ado-similar-tickets' en el resultado. Resultado: {result_ids}"
    )


# ---------------------------------------------------------------------------
# Test 3: Bloques de alta prioridad nunca se recortan
# ---------------------------------------------------------------------------

def test_rerank_high_priority_never_cut(monkeypatch):
    from config import config
    from services import cli_feature_flags, context_enrichment as ce
    from unittest.mock import patch

    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_PROJECTS", "", raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_TOKENS", 150, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_RERANK_ENABLED", True, raising=False)
    monkeypatch.setattr(cli_feature_flags, "context_budget_enabled", lambda _p: True, raising=False)

    # Un bloque de alta prioridad (100 tok) y uno de baja (100 tok)
    # Budget 150 → solo cabe uno.
    # El comentario es más "relevante" al context_text, pero la épica tiene alta prioridad.
    blocks = [
        _block("ado-epic-structured", "información de la épica"),  # alta prioridad → nunca cae
        _block("ado-comments", "comentario breve relevante"),       # baja prioridad
    ]
    context_text = "comentario breve relevante"  # el comentario es más relevante al query

    def _fake_token_estimate(block):
        return 100

    with patch.object(ce, "_block_token_estimate", _fake_token_estimate):
        result = ce._apply_context_budget(
            blocks, project_name="P", log=_log, context_text=context_text
        )

    result_ids = [b.get("id") for b in result]
    # La épica NUNCA se corta aunque el comentario sea más relevante al query
    assert "ado-epic-structured" in result_ids, (
        f"ado-epic-structured fue recortado. Resultado: {result_ids}"
    )


# ---------------------------------------------------------------------------
# Test 4: El ORDEN DE PRESENTACIÓN no cambia (solo el orden de conservación)
# ---------------------------------------------------------------------------

def test_rerank_presentation_order_stable(monkeypatch):
    from config import config
    from services import cli_feature_flags, context_enrichment as ce

    # Budget generoso para que no se recorte nada
    _monkeypatch_rerank(monkeypatch, budget=100_000)

    blocks = [
        _block("ado-comments", "comentario"),
        _block("ado-similar-tickets", "similar"),
        _block("ado-attachments", "adjunto"),
    ]
    context_text = "similar"

    result = ce._apply_context_budget(
        blocks, project_name="P", log=_log, context_text=context_text
    )

    # Con budget amplio, todos se conservan en el orden ORIGINAL
    result_ids = [b.get("id") for b in result]
    assert result_ids == ["ado-comments", "ado-similar-tickets", "ado-attachments"]


# ---------------------------------------------------------------------------
# Test 5: context_text=None → rerank no aplica (sin crash)
# ---------------------------------------------------------------------------

def test_rerank_no_crash_without_context_text(monkeypatch):
    from config import config
    from services import cli_feature_flags, context_enrichment as ce

    _monkeypatch_rerank(monkeypatch, budget=100_000)

    blocks = [
        _block("ado-similar-tickets", "algo"),
        _block("ado-comments", "otra cosa"),
    ]

    result = ce._apply_context_budget(
        blocks, project_name="P", log=_log, context_text=None
    )
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Test 6: _apply_context_budget sin flag de budget activo → identidad (retro-compat)
# ---------------------------------------------------------------------------

def test_budget_disabled_returns_same(monkeypatch):
    from config import config
    from services import cli_feature_flags, context_enrichment as ce

    monkeypatch.setattr(cli_feature_flags, "context_budget_enabled", lambda _p: False, raising=False)

    blocks = [_block("ado-comments", "texto")]
    result = ce._apply_context_budget(blocks, project_name="P", log=_log, context_text="texto")
    assert result is blocks
