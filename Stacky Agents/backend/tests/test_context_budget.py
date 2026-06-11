"""Tests de F2.4 — presupuesto de contexto con ranking en enrich_blocks."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _log(*_a, **_k):
    pass


def _blocks():
    # ~1000 chars c/u ≈ 250 tok cada uno
    return [
        {"id": "ado-epic-structured", "content": "E" * 1000},
        {"id": "ado-comments", "content": "C" * 4000},      # menor prioridad, grande
        {"id": "ado-similar-tickets", "content": "S" * 4000},
    ]


def test_budget_off_passthrough_same_object():
    from services import context_enrichment as ce

    blocks = _blocks()
    out = ce._apply_context_budget(blocks, project_name="P", log=_log)
    assert out is blocks  # OFF default → no copia ni recorta


def test_budget_keeps_high_priority_drops_low(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_PROJECTS", "", raising=False)
    # Budget chico: solo entra el epic (250 tok) + parte de uno más.
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_TOKENS", 300, raising=False)

    out = ce._apply_context_budget(_blocks(), project_name="P", log=_log)
    ids = [b["id"] for b in out]
    # El epic (prioridad 100) SIEMPRE sobrevive.
    assert "ado-epic-structured" in ids
    # Algo de menor prioridad se descartó.
    assert len(out) < 3


def test_budget_truncation_marker(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_PROJECTS", "", raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_TOKENS", 350, raising=False)

    out = ce._apply_context_budget(_blocks(), project_name="P", log=_log)
    joined = "\n".join(b.get("content", "") for b in out)
    # Hubo recorte: o bien hay marcador de truncado, o bloques descartados.
    assert "recortado por presupuesto" in joined or len(out) < 3
