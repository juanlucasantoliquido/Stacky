"""Plan 112 F5 — DocConsultor fantasma: warning no-silencioso + persona fallback."""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import docs_rag as api_docs_rag


@dataclass
class _FakeAgent:
    system_prompt: str


def _compose(agent_filename: str) -> str:
    """Replica la composición de route_chat (F5): fallback si el prompt es vacío."""
    return (api_docs_rag._read_agent_system_prompt(agent_filename)
            or api_docs_rag._DEFAULT_DOC_CONSULTOR_PROMPT)


def test_missing_agent_logs_warning(monkeypatch, caplog):
    monkeypatch.setattr("services.vscode_agents.get_agent_by_filename",
                        lambda **kw: None)
    with caplog.at_level(logging.WARNING):
        result = api_docs_rag._read_agent_system_prompt("DocConsultor.agent.md")
    assert result == ""
    assert any("se usará persona de fallback" in r.message for r in caplog.records)


def test_chat_uses_fallback_persona_when_agent_missing(monkeypatch):
    monkeypatch.setattr("services.vscode_agents.get_agent_by_filename",
                        lambda **kw: None)
    assert _compose("DocConsultor.agent.md") == api_docs_rag._DEFAULT_DOC_CONSULTOR_PROMPT


def test_present_agent_takes_precedence(monkeypatch):
    monkeypatch.setattr("services.vscode_agents.get_agent_by_filename",
                        lambda **kw: _FakeAgent(system_prompt="PERSONA REAL"))
    assert _compose("DocConsultor.agent.md") == "PERSONA REAL"
