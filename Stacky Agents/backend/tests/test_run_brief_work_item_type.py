"""Plan 45 F2 — run_brief acepta work_item_type y rutea/valida según flag.

Tests TDD:
1. body sin work_item_type → run_agent recibe work_item_type="Epic" (no 400)
2. body con work_item_type="Epic" → Epic (no 400)
3. body con work_item_type="Issue" + flag OFF → HTTP 400 issue_from_brief_disabled
4. body con work_item_type="Issue" + flag ON → run_agent recibe work_item_type="Issue"
5. body con work_item_type="Bug" → HTTP 400 invalid_work_item_type
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
        json={"brief": "texto", "runtime": "claude_code_cli", **body},
        headers={"X-User-Email": "test@test.com"},
    )


def test_no_work_item_type_defaults_epic():
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {})
        assert resp.status_code == 202
        assert mock_run_agent.call_args.kwargs.get("work_item_type") == "Epic"


def test_explicit_epic():
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {"work_item_type": "Epic"})
        assert resp.status_code == 202
        assert mock_run_agent.call_args.kwargs.get("work_item_type") == "Epic"


def test_issue_with_flag_off_is_400():
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_ISSUE_FROM_BRIEF_ENABLED", False):
        with app.test_client() as client:
            with _patch_deps() as mock_run_agent:
                resp = _post(client, {"work_item_type": "Issue"})
            assert resp.status_code == 400
            assert resp.get_json().get("error") == "issue_from_brief_disabled"
            mock_run_agent.assert_not_called()


def test_issue_with_flag_on_routes_issue():
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_ISSUE_FROM_BRIEF_ENABLED", True):
        with app.test_client() as client:
            with _patch_deps() as mock_run_agent:
                resp = _post(client, {"work_item_type": "Issue"})
            assert resp.status_code == 202
            assert mock_run_agent.call_args.kwargs.get("work_item_type") == "Issue"


def test_invalid_type_is_400():
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {"work_item_type": "Bug"})
        assert resp.status_code == 400
        assert resp.get_json().get("error") == "invalid_work_item_type"
        mock_run_agent.assert_not_called()
