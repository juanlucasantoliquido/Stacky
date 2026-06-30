"""Tests F4 — Plan 54: sink determinístico rechazo → corpus rejection_lessons.

F4a: función pura pure_rejection_to_lesson (determinista, sin red/DB).
F4b: integración load_for_run lee lo que capture_operator_note escribe
     (simulado via mock de memory_store para evitar dependencia de Flask/DB).
"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# F4a — función pura pure_rejection_to_lesson
# ---------------------------------------------------------------------------

def test_pure_rejection_to_lesson_deterministic():
    """Misma nota → mismo resultado siempre; determinista y sin efectos."""
    from services.rejection_lessons import pure_rejection_to_lesson

    nota = "No inventes procesos batch que no existen en el catálogo"
    result1 = pure_rejection_to_lesson(nota)
    result2 = pure_rejection_to_lesson(nota)

    assert result1 == result2, "Debe ser determinista"
    assert "NO REPITAS" in result1
    assert nota in result1


def test_pure_rejection_to_lesson_empty_returns_empty():
    """Nota vacía → string vacío."""
    from services.rejection_lessons import pure_rejection_to_lesson

    assert pure_rejection_to_lesson("") == ""
    assert pure_rejection_to_lesson("   ") == ""
    assert pure_rejection_to_lesson(None) == ""  # type: ignore[arg-type]


def test_pure_rejection_to_lesson_strips_whitespace():
    """Nota con espacios → se normaliza la nota, prefijo fijo."""
    from services.rejection_lessons import pure_rejection_to_lesson

    result = pure_rejection_to_lesson("  Error en la narración  ")
    assert result == "NO REPITAS: Error en la narración"


# ---------------------------------------------------------------------------
# F4b — integración: lo que se escribe se puede leer (mock memory_store)
# ---------------------------------------------------------------------------

def test_reject_persists_and_loads():
    """capture_operator_note guarda en memory_store → load_for_run lo recupera.

    Usa mocks para evitar depender de Flask/DB. Verifica el contrato:
    la memoria con tag 'rejected_reason' es procesada por build_items.
    """
    from services import rejection_lessons as rl

    # Simular lo que capture_operator_note escribe en memory_store
    _fake_memory = {
        "content": "Veredicto: rejected\n\nNo uses procesos no-catalogados",
        "tags": ["business", "operator_note", "rejected", "rejected_reason"],
        "title": "Nota del operador — business",
    }

    with patch("services.memory_store.list_observations", return_value=[_fake_memory]):
        items = rl.load_for_run(project="ONP", agent_type="business")

    assert len(items) == 1
    assert "No uses procesos no-catalogados" in items[0].pattern
    prefix = rl.build_prefix(items)
    assert "Evitá" in prefix or "Evit" in prefix
    assert "No uses procesos no-catalogados" in prefix
