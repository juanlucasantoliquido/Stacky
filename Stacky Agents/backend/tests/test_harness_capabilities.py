"""H1.2 — Tests de harness.capabilities."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_capabilities_has_three_runtimes():
    from harness.capabilities import CAPABILITIES

    assert "claude_code_cli" in CAPABILITIES
    assert "codex_cli" in CAPABILITIES
    assert "github_copilot" in CAPABILITIES


def test_claude_capabilities():
    from harness.capabilities import CAPABILITIES

    cap = CAPABILITIES["claude_code_cli"]
    assert cap.writes_artifacts is True
    assert cap.supports_stdin_feedback is True
    assert cap.supports_resume is True
    assert cap.supports_mcp is True
    assert cap.has_stream_telemetry is True


def test_codex_capabilities():
    from harness.capabilities import CAPABILITIES

    cap = CAPABILITIES["codex_cli"]
    assert cap.writes_artifacts is True
    assert cap.supports_stdin_feedback is False  # usa exec resume
    assert cap.supports_resume is True
    # MCP no verificado como soportado
    assert cap.supports_mcp is False
    assert cap.has_stream_telemetry is True


def test_unknown_runtime_returns_none():
    from harness.capabilities import CAPABILITIES

    assert CAPABILITIES.get("nonexistent_runtime") is None
