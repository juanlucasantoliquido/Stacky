"""Tests F0 — Plan 54: helper build_memory_prefix (función pura)."""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rej_item(pattern="NO hagas X", reason="Operador lo rechazó"):
    """Crea un RejectionItem real importando la dataclass."""
    from services.rejection_lessons import RejectionItem
    return RejectionItem(pattern=pattern, reason=reason)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_flag_off_returns_empty(monkeypatch):
    """Flag OFF → prefix vacío, count=0, nunca llama a rejection_lessons.

    El default ahora es ON (Grupo B) y build_memory_prefix con push_rejections_enabled=None
    lee config; pasamos el flag explícito=False para probar el caso OFF de forma determinista.
    """
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "false")
    with patch("services.rejection_lessons.load_for_run") as mock_load:
        from services.memory_prefix import build_memory_prefix
        prefix, meta = build_memory_prefix(
            project="proj", agent_type="BusinessAgent", push_rejections_enabled=False
        )
    assert prefix == ""
    assert meta["rejection_lessons_count"] == 0
    mock_load.assert_not_called()


def test_flag_on_includes_rejections(monkeypatch):
    """Flag ON, load_for_run retorna un ítem → prefix contiene "REGLA", count=1."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    item = _make_rej_item(pattern="NO hagas X")
    with patch("services.rejection_lessons.load_for_run", return_value=[item]), \
         patch("services.rejection_lessons.build_prefix", return_value="REGLA"):
        import importlib, services.memory_prefix as mp
        importlib.reload(mp)  # asegurar reload tras monkeypatch de env
        from services.memory_prefix import build_memory_prefix
        prefix, meta = build_memory_prefix(
            project="proj",
            agent_type="BusinessAgent",
            push_rejections_enabled=True,  # pasado explícito
        )
    assert "REGLA" in prefix
    assert meta["rejection_lessons_count"] == 1


def test_service_exception_is_swallowed(monkeypatch):
    """Si load_for_run lanza → prefix vacío, meta contiene 'memory_prefix_error'."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    with patch("services.rejection_lessons.load_for_run", side_effect=RuntimeError("boom")):
        from services.memory_prefix import build_memory_prefix
        prefix, meta = build_memory_prefix(
            project="proj",
            agent_type="BusinessAgent",
            push_rejections_enabled=True,
        )
    assert prefix == ""
    assert "memory_prefix_error" in meta
    assert "boom" in meta["memory_prefix_error"]


def test_empty_pattern_returns_empty(monkeypatch):
    """load_for_run devuelve lista vacía → prefix vacío, sin error."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    with patch("services.rejection_lessons.load_for_run", return_value=[]), \
         patch("services.rejection_lessons.build_prefix", return_value=""):
        from services.memory_prefix import build_memory_prefix
        prefix, meta = build_memory_prefix(
            project="proj",
            agent_type="BusinessAgent",
            push_rejections_enabled=True,
        )
    assert prefix == ""
    assert meta["rejection_lessons_count"] == 0
    assert "memory_prefix_error" not in meta
