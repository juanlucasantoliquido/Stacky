"""Tests F2/F4 (plan 48) — inyección de lecciones de rechazo en CLI (context_enrichment)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services import context_enrichment as ce
from services.rejection_lessons import RejectionItem


def _noop(*_a, **_k):
    pass


def _inject(blocks=None, project="Proj", agent_type="functional"):
    return ce._inject_rejection_lessons(
        blocks=blocks or [],
        project_name=project,
        agent_type=agent_type,
        log=_noop,
    )


def test_disabled_does_not_inject(monkeypatch):
    # Default ahora ON (Grupo B); fijamos OFF explícito para el caso deshabilitado.
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "false")
    with patch("services.rejection_lessons.load_for_run") as m_load:
        out = _inject()
    assert not any(b.get("id") == "rejection-lessons" for b in out)
    m_load.assert_not_called()


def test_enabled_injects_block(monkeypatch):
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    items = [RejectionItem("P1", "R1"), RejectionItem("P2", "R2")]
    with patch("services.rejection_lessons.load_for_run", return_value=items), \
         patch("services.anti_patterns.relevant", return_value=[]):
        out = _inject(blocks=[{"id": "brief", "content": "x"}])
    assert out[0]["id"] == "rejection-lessons"
    assert "**Evitá**" in out[0]["content"]


def test_enabled_no_items_no_block(monkeypatch):
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    with patch("services.rejection_lessons.load_for_run", return_value=[]), \
         patch("services.anti_patterns.relevant", return_value=[]):
        out = _inject()
    assert not any(b.get("id") == "rejection-lessons" for b in out)


def test_dedupe_passes_existing_patterns(monkeypatch):
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")

    class _AP:
        pattern = "No inventes Procesos"

    with patch("services.rejection_lessons.load_for_run", return_value=[]) as m_load, \
         patch("services.anti_patterns.relevant", return_value=[_AP()]):
        _inject()
    assert "no inventes procesos" in m_load.call_args.kwargs["existing_patterns"]


def test_exception_is_swallowed(monkeypatch):
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    blocks = [{"id": "brief"}]
    with patch("services.rejection_lessons.load_for_run", side_effect=RuntimeError("boom")), \
         patch("services.anti_patterns.relevant", return_value=[]):
        out = _inject(blocks=blocks)
    assert out == blocks


def test_no_project_no_block(monkeypatch):
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    with patch("services.rejection_lessons.load_for_run") as m_load:
        out = _inject(project=None)
    assert not any(b.get("id") == "rejection-lessons" for b in out)
    m_load.assert_not_called()


def test_block_metadata_has_count(monkeypatch):
    """F4 — el bloque lleva metadata['rejection_lessons_count']."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    items = [RejectionItem("P1", "R1"), RejectionItem("P2", "R2")]
    with patch("services.rejection_lessons.load_for_run", return_value=items), \
         patch("services.anti_patterns.relevant", return_value=[]):
        out = _inject(blocks=[{"id": "brief"}])
    assert out[0]["metadata"]["rejection_lessons_count"] == 2
