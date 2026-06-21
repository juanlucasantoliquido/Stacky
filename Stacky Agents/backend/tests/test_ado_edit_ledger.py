"""Plan 60 F3 — Tests del ledger de idempotencia (services/ado_edit_ledger.py).

Usa DB temporal en memoria + tmpdir para el JSONL fallback.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def ledger(monkeypatch, tmp_path):
    """Ledger con DB en memoria + JSONL en tmpdir."""
    import services.ado_edit_ledger as m
    monkeypatch.setattr(m, "_get_db_path", lambda: "file::memory:?cache=shared&uri=true")
    monkeypatch.setattr(m, "_get_jsonl_path", lambda: tmp_path / "ado_edit_learned.jsonl")
    m._create_table_if_needed()
    return m


def test_not_learned_before_mark(ledger):
    """already_learned antes de marcar → False."""
    assert ledger.already_learned(10, 2) is False


def test_learned_after_mark(ledger):
    """after mark_learned → already_learned → True."""
    ledger.mark_learned(10, 2, "run-x")
    assert ledger.already_learned(10, 2) is True


def test_processed_revs_for(ledger):
    """processed_revs_for devuelve set de revs marcadas."""
    ledger.mark_learned(10, 2, "run-a")
    ledger.mark_learned(10, 3, "run-b")
    revs = ledger.processed_revs_for(10)
    assert revs == {2, 3}


def test_mark_twice_same_pk_does_not_raise(ledger):
    """mark_learned dos veces misma PK → no rompe (INSERT OR IGNORE)."""
    ledger.mark_learned(10, 2, "run-x")
    ledger.mark_learned(10, 2, "run-y")  # should not raise
    assert ledger.already_learned(10, 2) is True


def test_jsonl_fallback(monkeypatch, tmp_path):
    """Con SQLite fallando → mark_learned escribe en JSONL; already_learned lee del JSONL."""
    import services.ado_edit_ledger as m

    # Forzar fallo de SQLite en _get_db_path y _create_table_if_needed
    monkeypatch.setattr(m, "_get_db_path", lambda: "/nonexistent/path/stacky.db")
    jsonl_path = tmp_path / "ado_edit_learned.jsonl"
    monkeypatch.setattr(m, "_get_jsonl_path", lambda: jsonl_path)

    # Con DB que no existe, mark_learned no lanza pero sí escribe JSONL
    m.mark_learned(99, 5, "run-z")

    # JSONL debe existir y contener la entrada
    assert jsonl_path.exists()
    with jsonl_path.open() as f:
        entries = [json.loads(line) for line in f if line.strip()]
    assert any(e["ado_id"] == 99 and e["rev"] == 5 for e in entries)

    # already_learned debe leer del JSONL cuando SQLite no funciona
    result = m.already_learned(99, 5)
    assert result is True

    # El JSONL no debe contener autor ni contenido (solo ado_id, rev, ts)
    for entry in entries:
        assert "author" not in entry
        assert "content" not in entry
        assert "html" not in entry
