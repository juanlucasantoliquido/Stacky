"""Plan 39 B1 — Manejo de error robusto en run-brief: nunca devuelve 500 genérico.

Tests TDD que deben pasar DESPUÉS de parchear api/agents.py:run_brief().

1. test_run_brief_runner_exception_returns_502_not_500
2. test_run_brief_unknown_agent_returns_400
3. test_run_brief_success_returns_202
4. test_run_brief_missing_brief_returns_400
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _patch_run_brief_deps(execution_id=99, run_agent_exc=None):
    fake_ticket = MagicMock()
    fake_ticket.id = 1

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket
        yield sess

    import agent_runner as ar

    if run_agent_exc:
        mock_run_agent = MagicMock(side_effect=run_agent_exc)
    else:
        mock_run_agent = MagicMock(return_value=execution_id)

    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", mock_run_agent):
        yield mock_run_agent


# ---------------------------------------------------------------------------
# 1. RuntimeError → 502, no 500
# ---------------------------------------------------------------------------

def test_run_brief_runner_exception_returns_502_not_500():
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(run_agent_exc=RuntimeError("boom")):
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "test brief", "runtime": "claude_code_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 502
        data = resp.get_json()
        assert data["ok"] is False
        assert data["error"] == "agent_launch_failed"
        assert "boom" in data["message"]


# ---------------------------------------------------------------------------
# 2. UnknownAgentError → 400
# ---------------------------------------------------------------------------

def test_run_brief_unknown_agent_returns_400():
    from agent_runner import UnknownAgentError
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(run_agent_exc=UnknownAgentError("business")):
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "test brief", "runtime": "codex_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Éxito → 202 con execution_id
# ---------------------------------------------------------------------------

def test_run_brief_success_returns_202():
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=123):
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "test brief"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["execution_id"] == 123


# ---------------------------------------------------------------------------
# 4. Body sin brief → 400
# ---------------------------------------------------------------------------

def test_run_brief_missing_brief_returns_400():
    app = _make_app()
    with app.test_client() as client:
        resp = client.post(
            "/api/agents/run-brief",
            json={"runtime": "claude_code_cli"},
            headers={"X-User-Email": "test@test.com"},
        )
        assert resp.status_code == 400
