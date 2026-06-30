"""Plan 43 F0 — Set ampliado de efforts (low/medium/high/xhigh/max) + clamp por modelo."""
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
def _patch_run_brief_deps(execution_id=99):
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


def _post_effort(effort, model=None):
    app = _make_app()
    body = {"brief": "x", "runtime": "claude_code_cli", "effort": effort}
    if model:
        body["model"] = model
    with app.test_client() as client:
        with _patch_run_brief_deps() as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json=body,
                headers={"X-User-Email": "test@test.com"},
            )
    assert resp.status_code == 202, resp.get_data(as_text=True)
    _, kwargs = mock_run_agent.call_args
    return kwargs.get("effort_override")


# Whitelist de efforts en run_brief
def test_effort_xhigh_passes():
    # con model opus para que el clamp por modelo no lo degrade
    assert _post_effort("xhigh", model="claude-opus-4-8") == "xhigh"


def test_effort_max_passes():
    assert _post_effort("max", model="claude-opus-4-8") == "max"


def test_effort_invalid_defaults_high():
    assert _post_effort("turbo") == "high"


# _clamp_effort_for_model
def test_clamp_xhigh_sonnet_to_high():
    from api.agents import _clamp_effort_for_model
    assert _clamp_effort_for_model("xhigh", "claude-sonnet-4-6") == "high"


def test_clamp_max_sonnet_keeps_max():
    from api.agents import _clamp_effort_for_model
    assert _clamp_effort_for_model("max", "claude-sonnet-4-6") == "max"


def test_clamp_xhigh_haiku_to_high():
    from api.agents import _clamp_effort_for_model
    assert _clamp_effort_for_model("xhigh", "claude-haiku-4-5") == "high"


def test_clamp_xhigh_opus_keeps_xhigh():
    from api.agents import _clamp_effort_for_model
    assert _clamp_effort_for_model("xhigh", "claude-opus-4-8") == "xhigh"


def test_clamp_max_opus_keeps_max():
    from api.agents import _clamp_effort_for_model
    assert _clamp_effort_for_model("max", "claude-opus-4-8") == "max"
