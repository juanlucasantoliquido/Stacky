"""Plan 52 F0 — Paridad de runtimes: run_brief rechaza con 400 el combo
work_item_type ∈ {Epic, Issue} + runtime ≠ claude_code_cli, antes de gastar tokens.

El autopublish (Epic/Issue) SOLO lo ejecuta el finalizador de claude_code_cli_runner.
Codex CLI y GitHub Copilot NO autopublican → degradación controlada = 400 legible.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _patch_deps(execution_id=99):
    fake_ticket = MagicMock()
    fake_ticket.id = 1

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket
        yield sess

    import agent_runner as ar
    mock_run_agent = MagicMock(return_value=execution_id)
    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", mock_run_agent):
        yield mock_run_agent


def _post(client, body):
    return client.post(
        "/api/agents/run-brief",
        json={"brief": "texto", **body},
        headers={"X-User-Email": "test@test.com"},
    )


def test_run_brief_epic_codex_returns_400():
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {"runtime": "codex_cli", "work_item_type": "Epic"})
        assert resp.status_code == 400
        assert resp.get_json().get("error") == "autopublish_requires_claude_cli"
        mock_run_agent.assert_not_called()


def test_run_brief_issue_copilot_returns_400():
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_ISSUE_FROM_BRIEF_ENABLED", True):
        with app.test_client() as client:
            with _patch_deps() as mock_run_agent:
                resp = _post(client, {"runtime": "github_copilot", "work_item_type": "Issue"})
            assert resp.status_code == 400
            assert resp.get_json().get("error") == "autopublish_requires_claude_cli"
            mock_run_agent.assert_not_called()


def test_run_brief_epic_claude_cli_not_rejected_by_parity_guard():
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {
                "runtime": "claude_code_cli",
                "work_item_type": "Epic",
                "vscode_agent_filename": "BusinessAgent.agent.md",
            })
        # NO debe rechazarse por el guard de paridad. Puede ser 202 (lanzado) o
        # fallar por otra validación, pero el error NUNCA es el de paridad.
        assert resp.get_json().get("error") != "autopublish_requires_claude_cli"


def test_run_brief_epic_default_runtime_copilot_returns_400():
    # work_item_type por default normaliza a "Epic"; runtime por default es
    # github_copilot → el guard se dispara (correcto: hoy también falla en silencio).
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {})  # sin runtime, sin work_item_type
        assert resp.status_code == 400
        assert resp.get_json().get("error") == "autopublish_requires_claude_cli"
        mock_run_agent.assert_not_called()
