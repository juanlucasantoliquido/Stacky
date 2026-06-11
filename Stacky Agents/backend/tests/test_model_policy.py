"""H2.4 — Tests de harness.model_policy.resolve_model.

Casos:
  1. claude_code_cli: clampa opus a sonnet (cap §5.2)
  2. claude_code_cli: passthrough para sonnet (dentro del cap)
  3. codex_cli: passthrough cuando no hay denylist
  4. codex_cli: degrada cuando modelo matchea denylist
  5. otro runtime: passthrough sin restricciones
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


def test_claude_clamps_opus(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MODEL", "")
    from harness.model_policy import resolve_model

    model, reason = resolve_model("claude_code_cli", "claude-opus-4-5")
    assert "opus" not in model.lower()
    assert "clamped" in reason


def test_claude_passthrough_sonnet(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MODEL", "")
    from harness.model_policy import resolve_model

    model, reason = resolve_model("claude_code_cli", "claude-sonnet-4-6")
    assert model == "claude-sonnet-4-6"
    assert "passthrough" in reason


def test_codex_passthrough_no_denylist(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "CODEX_CLI_MODEL", "gpt-4o")
    monkeypatch.setattr(config, "CODEX_CLI_MODEL_DENYLIST", "")
    from harness.model_policy import resolve_model

    model, reason = resolve_model("codex_cli", "gpt-4o")
    assert model == "gpt-4o"
    assert reason == "passthrough"


def test_codex_degrades_when_in_denylist(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "CODEX_CLI_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(config, "CODEX_CLI_MODEL_DENYLIST", "gpt-4-turbo,gpt-4o-max")
    from harness.model_policy import resolve_model

    model, reason = resolve_model("codex_cli", "gpt-4o-max")
    assert model == "gpt-4o-mini"
    assert "denylist" in reason.lower()


def test_codex_denylist_case_insensitive(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "CODEX_CLI_MODEL", "safe-model")
    monkeypatch.setattr(config, "CODEX_CLI_MODEL_DENYLIST", "BadModel")
    from harness.model_policy import resolve_model

    model, reason = resolve_model("codex_cli", "BADMODEL")
    assert model == "safe-model"


def test_other_runtime_passthrough():
    from harness.model_policy import resolve_model

    model, reason = resolve_model("github_copilot", "gpt-4.1")
    assert model == "gpt-4.1"
    assert "passthrough" in reason


def test_codex_no_model_configured(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "CODEX_CLI_MODEL", "")
    monkeypatch.setattr(config, "CODEX_CLI_MODEL_DENYLIST", "")
    from harness.model_policy import resolve_model

    model, reason = resolve_model("codex_cli", None)
    assert model is None or model == ""
    assert reason == "passthrough"
