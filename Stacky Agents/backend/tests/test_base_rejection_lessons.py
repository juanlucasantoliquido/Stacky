"""Tests F3 (plan 48) — paridad github_copilot en agents/base.py."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agents.base import BaseAgent, RunContext
from services.rejection_lessons import RejectionItem


class _MiniAgent(BaseAgent):
    type = "functional"
    name = "Mini"
    description = "test agent"

    def system_prompt(self) -> str:
        return "BASE PROMPT"


def _ctx(**kw):
    # Apagar few-shot/decisions/style para aislar el bloque de anti-patrones.
    return RunContext(
        project="Proj",
        use_few_shot=False,
        use_decisions=False,
        use_anti_patterns=kw.pop("use_anti_patterns", True),
        started_by="",
        **kw,
    )


def test_copilot_disabled_only_manual_antipatterns(monkeypatch):
    monkeypatch.delenv("STACKY_PUSH_REJECTIONS_ENABLED", raising=False)
    with patch("services.anti_patterns.relevant", return_value=[]), \
         patch("services.rejection_lessons.load_for_run") as m_load:
        _prompt, meta = _MiniAgent().compose_system_prompt(_ctx())
    assert "rejection_lessons_count" not in meta
    m_load.assert_not_called()


def test_copilot_enabled_appends_rejections(monkeypatch):
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    items = [RejectionItem("P1", "R1"), RejectionItem("P2", "R2")]
    with patch("services.anti_patterns.relevant", return_value=[]), \
         patch("services.rejection_lessons.load_for_run", return_value=items):
        prompt, meta = _MiniAgent().compose_system_prompt(_ctx())
    assert meta["rejection_lessons_count"] == 2
    assert "Lecciones de rechazos previos" in prompt


def test_copilot_dedupe_against_manual(monkeypatch):
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")

    class _AP:
        pattern = "No inventes Procesos"
        reason = "r"
        example = None

    with patch("services.anti_patterns.relevant", return_value=[_AP()]), \
         patch("services.rejection_lessons.load_for_run", return_value=[]) as m_load:
        _MiniAgent().compose_system_prompt(_ctx())
    assert "no inventes procesos" in m_load.call_args.kwargs["existing_patterns"]


def test_copilot_use_anti_patterns_false_skips_all(monkeypatch):
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")
    with patch("services.anti_patterns.relevant") as m_ap, \
         patch("services.rejection_lessons.load_for_run") as m_load:
        _prompt, meta = _MiniAgent().compose_system_prompt(_ctx(use_anti_patterns=False))
    assert "anti_patterns_count" not in meta
    assert "rejection_lessons_count" not in meta
    m_ap.assert_not_called()
    m_load.assert_not_called()
