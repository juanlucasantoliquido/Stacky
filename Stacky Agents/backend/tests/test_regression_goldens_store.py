"""Plan 56 F1 — Persistencia de goldens (JSON versionado en repo).

Tests PRIMERO (TDD). Usa tmp_path para aislar el disco de cada test.
"""
from __future__ import annotations

import json
import pytest


# ── fixture: redirigir _GOLDENS_DIR a tmp_path ───────────────────────────────

@pytest.fixture(autouse=True)
def _isolated_goldens_dir(tmp_path, monkeypatch):
    """Redirige el directorio de goldens a un tmpdir para cada test."""
    import harness.regression_goldens as mod
    monkeypatch.setattr(mod, "_GOLDENS_DIR", tmp_path)
    yield


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_negative_golden(value: str = "el rf-01 no tiene criterios"):
    from harness.regression_goldens import Golden
    return Golden(
        kind="negative",
        check="absent_substring",
        value=value,
        project="p1",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )


# ── Tests F1 ─────────────────────────────────────────────────────────────────

def test_save_then_load_roundtrip():
    """save_golden seguido de load_goldens devuelve el mismo golden."""
    from harness.regression_goldens import save_golden, load_goldens

    g = _make_negative_golden()
    save_golden(g)

    loaded = load_goldens(project="p1", agent_type="BusinessAgent", work_item_type="Epic")
    assert len(loaded) == 1
    assert loaded[0] == g


def test_save_idempotent_no_duplication():
    """Guardar el mismo golden dos veces → sigue siendo 1 entrada."""
    from harness.regression_goldens import save_golden, load_goldens

    g = _make_negative_golden()
    save_golden(g)
    save_golden(g)  # segunda vez: debe ser no-op

    loaded = load_goldens(project="p1", agent_type="BusinessAgent", work_item_type="Epic")
    assert len(loaded) == 1


def test_load_missing_returns_empty():
    """Archivo inexistente → load_goldens devuelve []."""
    from harness.regression_goldens import load_goldens

    result = load_goldens(project="nonexistent", agent_type="X", work_item_type="Epic")
    assert result == []


def test_corrupt_json_returns_empty_no_raise(tmp_path, monkeypatch):
    """JSON corrupto → load_goldens devuelve [], sin lanzar excepción."""
    import harness.regression_goldens as mod
    monkeypatch.setattr(mod, "_GOLDENS_DIR", tmp_path)

    # Escribir JSON roto directamente
    path = mod._store_path(project="p1", agent_type="BusinessAgent", work_item_type="Epic")
    path.write_text("{ invalid json !!!}", encoding="utf-8")

    result = mod.load_goldens(project="p1", agent_type="BusinessAgent", work_item_type="Epic")
    assert result == []
