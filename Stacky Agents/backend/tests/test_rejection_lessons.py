"""Tests F0/F1 (plan 48) — rejection_lessons: rechazos → anti-patrones."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services import rejection_lessons as rl


def _mem(content, tags):
    return {"content": content, "tags": tags, "title": "t"}


# ── F0 build_items / build_prefix ───────────────────────────────────────────────

def test_no_memories_returns_empty():
    assert rl.build_items([]) == []
    assert rl.build_prefix([]) == ""


def test_ignores_non_rejection_tags():
    m = _mem("Veredicto: rejected\n\nalgo", ["agent", "session"])
    assert rl.build_items([m]) == []


def test_extracts_pattern_from_rejected_note():
    m = _mem(
        "Veredicto: rejected\n\nNo inventes procesos batch\nUsar solo el catálogo",
        ["functional", "operator_note", "rejected", "rejected_reason"],
    )
    items = rl.build_items([m])
    assert len(items) == 1
    assert items[0].pattern == "No inventes procesos batch"
    assert "Usar solo el catálogo" in items[0].reason


def test_dedupes_against_existing():
    m = _mem(
        "Veredicto: rejected\n\nNo inventes procesos batch",
        ["rejected_reason"],
    )
    items = rl.build_items(
        [m], existing_patterns={"no inventes procesos batch"}
    )
    assert items == []


def test_dedupes_internal():
    m1 = _mem("Veredicto: rejected\n\nMismo error\ncontexto a", ["rejected_reason"])
    m2 = _mem("Veredicto: rejected\n\nMismo error\ncontexto b", ["rejected_reason"])
    items = rl.build_items([m1, m2])
    assert len(items) == 1


def test_respects_max_items():
    mems = [
        _mem(f"Veredicto: rejected\n\nError {i}", ["rejected_reason"])
        for i in range(10)
    ]
    items = rl.build_items(mems, max_items=6)
    assert len(items) == 6


def test_truncates_long_pattern():
    m = _mem("Veredicto: rejected\n\n" + "x" * 500, ["rejected_reason"])
    items = rl.build_items([m])
    assert len(items[0].pattern) == 280


def test_build_prefix_imperative_format():
    items = [
        rl.RejectionItem(pattern="P1", reason="R1"),
        rl.RejectionItem(pattern="P2", reason="R2"),
    ]
    out = rl.build_prefix(items)
    assert "Lecciones de rechazos previos" in out
    assert "**Evitá**" in out
    assert "P1" in out and "P2" in out


def test_approval_condition_tag_also_included():
    m = _mem(
        "Veredicto: approved_with_notes\n\nSiempre citar la fuente",
        ["operator_note", "approval_condition"],
    )
    items = rl.build_items([m])
    assert len(items) == 1
    assert items[0].pattern == "Siempre citar la fuente"


# ── F1 load_for_run ─────────────────────────────────────────────────────────────

def test_load_none_project_returns_empty():
    assert rl.load_for_run(project=None, agent_type="functional") == []


def test_load_filters_and_builds():
    rows = [
        _mem("Veredicto: rejected\n\nNo X", ["operator_note", "rejected_reason"]),
        _mem("Veredicto: ok\n\nresumen", ["operator_note", "session"]),
    ]
    with patch("services.memory_store.list_observations", return_value=rows) as m_list:
        items = rl.load_for_run(project="Proj", agent_type="functional")
    assert len(items) == 1
    assert items[0].pattern == "No X"
    assert m_list.call_args.kwargs["type"] == "operator_note"
    assert m_list.call_args.kwargs["project"] == "Proj"


def test_load_db_error_returns_empty():
    with patch("services.memory_store.list_observations", side_effect=RuntimeError("boom")):
        assert rl.load_for_run(project="Proj", agent_type="functional") == []
