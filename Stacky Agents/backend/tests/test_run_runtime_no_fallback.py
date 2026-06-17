"""Plan 36 — F1: backend default explícito + runtime_defaulted + rechazo unknown.

Tests:
1. runtime explícito claude_code_cli → se conserva + runtime_defaulted=False
2. runtime explícito codex_cli → se conserva + runtime_defaulted=False
3. runtime ausente → default github_copilot + runtime_defaulted=True
4. runtime="" → tratado como ausente → default github_copilot + runtime_defaulted=True
5. runtime="foo" → 400, error=unknown_runtime, run_agent NO llamado
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_FAKE_EXEC_ID = 99


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

@contextmanager
def _null_session():
    """session_scope que no toca DB real."""
    mock_session = MagicMock()
    mock_session.get.return_value = None
    yield mock_session


def _make_app():
    """App Flask mínima con blueprint de agents."""
    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True
    from api.agents import bp
    app.register_blueprint(bp, url_prefix="/api/agents")
    return app


def _patch_all_deps(monkeypatch):
    """Parchea todo lo que toca DB o procesos en el endpoint /run."""
    # run_agent — parchear el módulo fuente (importado por api.agents al top-level)
    import agent_runner as ar_mod
    mock_run = MagicMock(return_value=_FAKE_EXEC_ID)
    monkeypatch.setattr(ar_mod, "run_agent", mock_run)

    # session_scope usado en FA-32 (prev_exec_id path — no activamos ese path en tests)
    monkeypatch.setattr("db.session_scope", _null_session)

    # run_guard.find_active_run → None (sin duplicados)
    import services.run_guard as rg_mod
    monkeypatch.setattr(rg_mod, "find_active_run", lambda *a, **kw: None)

    # ticket_assigner.auto_assign_on_run → no-op
    import services.ticket_assigner as ta_mod
    monkeypatch.setattr(ta_mod, "auto_assign_on_run", lambda *a, **kw: None)

    # run_slots → siempre adquiere
    import services.run_slots as rs_mod
    monkeypatch.setattr(rs_mod, "try_acquire", lambda: True)
    monkeypatch.setattr(rs_mod, "active_count", lambda: 0)
    monkeypatch.setattr(rs_mod, "release", lambda: None)

    # V2.4 run_cache — deshabilitar
    import config as cfg_mod
    monkeypatch.setattr(cfg_mod.config, "STACKY_RUN_CACHE_DAYS", 0, raising=False)

    return mock_run


# ---------------------------------------------------------------------------
# Test 1: runtime explícito claude_code_cli → conservado, runtime_defaulted=False
# ---------------------------------------------------------------------------

def test_run_with_explicit_claude_code_cli_keeps_runtime(monkeypatch):
    mock_run = _patch_all_deps(monkeypatch)
    app = _make_app()
    payload = {
        "agent_type": "dev",
        "ticket_id": 1,
        "runtime": "claude_code_cli",
        "vscode_agent_filename": "Dev.agent.md",
    }

    with app.test_client() as c:
        resp = c.post("/api/agents/run", json=payload)

    data = resp.get_json()
    assert resp.status_code in (200, 202), f"Status {resp.status_code}: {data}"
    assert data.get("runtime") == "claude_code_cli", data
    assert data.get("runtime_defaulted") is False, data
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: runtime explícito codex_cli → conservado, runtime_defaulted=False
# ---------------------------------------------------------------------------

def test_run_with_explicit_codex_cli_keeps_runtime(monkeypatch):
    mock_run = _patch_all_deps(monkeypatch)
    app = _make_app()
    payload = {
        "agent_type": "dev",
        "ticket_id": 1,
        "runtime": "codex_cli",
        "vscode_agent_filename": "Dev.agent.md",
    }

    with app.test_client() as c:
        resp = c.post("/api/agents/run", json=payload)

    data = resp.get_json()
    assert resp.status_code in (200, 202), f"Status {resp.status_code}: {data}"
    assert data.get("runtime") == "codex_cli", data
    assert data.get("runtime_defaulted") is False, data
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: runtime ausente → default github_copilot + runtime_defaulted=True
# ---------------------------------------------------------------------------

def test_run_absent_runtime_defaults_explicitly(monkeypatch):
    mock_run = _patch_all_deps(monkeypatch)
    app = _make_app()
    payload = {
        "agent_type": "dev",
        "ticket_id": 1,
        # Sin "runtime" — debe defaultear a github_copilot
    }

    with app.test_client() as c:
        resp = c.post("/api/agents/run", json=payload)

    data = resp.get_json()
    assert resp.status_code in (200, 202), f"Status {resp.status_code}: {data}"
    assert data.get("runtime") == "github_copilot", data
    assert data.get("runtime_defaulted") is True, data
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: runtime="" → tratado como ausente → default github_copilot + runtime_defaulted=True
# ---------------------------------------------------------------------------

def test_run_empty_runtime_treated_as_absent(monkeypatch):
    mock_run = _patch_all_deps(monkeypatch)
    app = _make_app()
    payload = {
        "agent_type": "dev",
        "ticket_id": 1,
        "runtime": "",
    }

    with app.test_client() as c:
        resp = c.post("/api/agents/run", json=payload)

    data = resp.get_json()
    assert resp.status_code in (200, 202), f"Status {resp.status_code}: {data}"
    assert data.get("runtime") == "github_copilot", data
    assert data.get("runtime_defaulted") is True, data
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: runtime="foo" → 400, error=unknown_runtime, run_agent NO llamado
# ---------------------------------------------------------------------------

def test_run_unknown_runtime_rejected_400(monkeypatch):
    mock_run = _patch_all_deps(monkeypatch)
    app = _make_app()
    payload = {
        "agent_type": "dev",
        "ticket_id": 1,
        "runtime": "foo_bar_invalid",
    }

    with app.test_client() as c:
        resp = c.post("/api/agents/run", json=payload)

    data = resp.get_json()
    assert resp.status_code == 400, f"Status {resp.status_code}: {data}"
    assert data.get("error") == "unknown_runtime", data
    mock_run.assert_not_called()
