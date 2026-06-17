from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_cli_runtimes_check_warns_when_binary_missing(monkeypatch):
    from services import local_diagnostics

    local_diagnostics._CLI_RUNTIME_CACHE["checks"] = None
    local_diagnostics._CLI_RUNTIME_CACHE["expires_at"] = 0

    def _run(*_args, **_kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", _run)
    result = local_diagnostics._check_cli_runtimes()

    assert result["status"] == "warning"
    checks = result["detail"]["checks"]
    assert any(c["name"] == "claude" and not c["ok"] for c in checks)
    assert any(c["name"] == "codex" and not c["ok"] for c in checks)


def test_cli_runtimes_check_ok_when_versions_resolve(monkeypatch):
    from services import local_diagnostics

    local_diagnostics._CLI_RUNTIME_CACHE["checks"] = None
    local_diagnostics._CLI_RUNTIME_CACHE["expires_at"] = 0

    class _Proc:
        returncode = 0
        stdout = "v1.2.3\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Proc())
    result = local_diagnostics._check_cli_runtimes()

    assert result["status"] == "ok"
