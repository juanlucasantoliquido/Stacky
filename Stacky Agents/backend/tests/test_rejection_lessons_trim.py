"""Tests F4b — Plan 54: poda determinística del corpus rejection_lessons.

trim_rejection_corpus mantiene los últimos max_count por (project, agent_type).
Usa mocks de memory_store para evitar dependencia de DB/Flask.
"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import patch, call, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_row(i: int, tag="rejected_reason") -> dict:
    """Fila de memory_store simulada."""
    return {
        "memory_id": f"mem-{i:04d}",
        "content": f"Veredicto: rejected\n\nError número {i}",
        "tags": ["operator_note", tag],
        "title": f"Nota {i}",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_trim_keeps_last_n():
    """Con 150 lecciones y max_count=100 → se eliminan 50 (las más antiguas)."""
    from services import rejection_lessons as rl

    # list_observations devuelve 150 filas (ya en orden DESC, i=0 es la más reciente)
    all_rows = [_fake_row(i) for i in range(150)]

    deleted_ids = []

    def fake_set_status(mem_id, status):
        deleted_ids.append(mem_id)
        return True

    with patch("services.memory_store.list_observations", return_value=all_rows), \
         patch("services.memory_store.set_status", side_effect=fake_set_status):
        count = rl.trim_rejection_corpus(project="ONP", agent_type="business", max_count=100)

    assert count == 50
    # Las filas eliminadas son las últimas 50 del ordenamiento DESC (índices 100..149)
    expected_deleted = [f"mem-{i:04d}" for i in range(100, 150)]
    assert deleted_ids == expected_deleted


def test_trim_is_deterministic():
    """Mismo input → mismo resultado (determinista)."""
    from services import rejection_lessons as rl

    all_rows = [_fake_row(i) for i in range(20)]

    counts = []
    for _ in range(3):
        deleted_ids = []

        def fake_set_status(mem_id, status):
            deleted_ids.append(mem_id)
            return True

        with patch("services.memory_store.list_observations", return_value=all_rows), \
             patch("services.memory_store.set_status", side_effect=fake_set_status):
            c = rl.trim_rejection_corpus(project="ONP", agent_type="business", max_count=10)
        counts.append(c)

    assert counts[0] == counts[1] == counts[2] == 10, "Resultado debe ser determinista"


def test_trim_no_op_when_under_limit():
    """Si hay ≤ max_count filas, no se elimina nada."""
    from services import rejection_lessons as rl

    all_rows = [_fake_row(i) for i in range(5)]

    with patch("services.memory_store.list_observations", return_value=all_rows), \
         patch("services.memory_store.set_status") as mock_del:
        count = rl.trim_rejection_corpus(project="ONP", agent_type="business", max_count=100)

    assert count == 0
    mock_del.assert_not_called()


def test_trim_skips_non_rejection_tags():
    """Filas sin tag de rechazo no cuentan para el límite ni se eliminan."""
    from services import rejection_lessons as rl

    # 5 con tag de rechazo + 5 sin tag de rechazo
    rows = [_fake_row(i, tag="rejected_reason") for i in range(5)]
    rows += [_fake_row(i + 100, tag="session_note") for i in range(5)]  # no rejection

    with patch("services.memory_store.list_observations", return_value=rows), \
         patch("services.memory_store.set_status") as mock_del:
        count = rl.trim_rejection_corpus(project="ONP", agent_type="business", max_count=10)

    # Solo 5 filas con rejection tags < max_count=10 → 0 eliminadas
    assert count == 0
    mock_del.assert_not_called()


def test_trim_handles_exception_gracefully():
    """Si memory_store falla → devuelve 0, no lanza."""
    from services import rejection_lessons as rl

    with patch("services.memory_store.list_observations", side_effect=RuntimeError("DB error")):
        count = rl.trim_rejection_corpus(project="ONP", agent_type="business")

    assert count == 0
