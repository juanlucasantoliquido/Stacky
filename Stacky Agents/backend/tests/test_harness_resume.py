"""H7.1 — Tests de harness.resume.resolve().

Casos:
  1. Sin sesión previa → (None, None)
  2. Con sesión + flag CODEX_CLI_RESUME_ENABLED ON → (session_ref, delta_prefix o None)
  3. Flag OFF → (None, None)
  4. Runtime claude_code_cli con flag ON → (session_ref, delta_prefix o None)
  5. Runtime desconocido → ValueError
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_resolve_no_session_returns_none():
    """Sin sesión previa registrada en la DB → (None, None) para cualquier runtime."""
    from harness.resume import resolve

    result = resolve(
        runtime="codex_cli",
        ticket_id=9999,
        agent_type="dev",
        project="TestProject",
    )
    assert result == (None, None)


def test_resolve_flag_off_returns_none(monkeypatch):
    """Flag CODEX_CLI_RESUME_ENABLED OFF → (None, None) sin tocar la DB."""
    from config import config
    from harness.resume import resolve

    monkeypatch.setattr(config, "CODEX_CLI_RESUME_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "CODEX_CLI_RESUME_PROJECTS", "", raising=False)

    result = resolve(
        runtime="codex_cli",
        ticket_id=1,
        agent_type="dev",
        project="TestProject",
    )
    assert result == (None, None)


def test_resolve_claude_flag_off_returns_none(monkeypatch):
    """Flag CLAUDE_CODE_CLI_RESUME_ENABLED OFF → (None, None) para claude."""
    from config import config
    from harness.resume import resolve

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_RESUME_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_RESUME_PROJECTS", "", raising=False)

    result = resolve(
        runtime="claude_code_cli",
        ticket_id=1,
        agent_type="dev",
        project="TestProject",
    )
    assert result == (None, None)


def test_resolve_unknown_runtime_raises():
    """Runtime desconocido → ValueError."""
    from harness.resume import resolve

    with pytest.raises(ValueError, match="runtime desconocido"):
        resolve(
            runtime="some_unknown_runtime",
            ticket_id=1,
            agent_type="dev",
            project=None,
        )


def test_resolve_codex_flag_on_no_prior_session(monkeypatch):
    """Flag ON pero no hay ejecución previa con codex_session_id → (None, None)."""
    from config import config
    from harness.resume import resolve

    monkeypatch.setattr(config, "CODEX_CLI_RESUME_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "CODEX_CLI_RESUME_PROJECTS", "", raising=False)

    # ticket_id 9998 nunca existirá en la DB de test
    result = resolve(
        runtime="codex_cli",
        ticket_id=9998,
        agent_type="dev",
        project=None,
    )
    assert result == (None, None)
