"""Plan 43 F1 — clamp_model(allow_opus): Opus 4.8 de primera clase en brief→épica."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_opus48_capped_by_default():
    from services import llm_router
    assert llm_router.clamp_model("claude-opus-4-8", allow_opus=False) == "claude-sonnet-5"


def test_opus48_allowed_when_flag_true():
    from services import llm_router
    assert llm_router.clamp_model("claude-opus-4-8", allow_opus=True) == "claude-opus-4-8"


def test_opus48_capped_when_no_second_arg():
    from services import llm_router
    assert llm_router.clamp_model("claude-opus-4-8") == "claude-sonnet-5"


def test_sonnet_untouched_with_allow_opus():
    from services import llm_router
    assert llm_router.clamp_model("claude-sonnet-5", allow_opus=True) == "claude-sonnet-5"
    # sonnet-4-6 (fallback del CLI) tambien sigue siendo un modelo Claude valido.
    assert llm_router.clamp_model("claude-sonnet-4-6", allow_opus=True) == "claude-sonnet-4-6"


def test_haiku_untouched_with_allow_opus():
    from services import llm_router
    assert llm_router.clamp_model("claude-haiku-4-5", allow_opus=True) == "claude-haiku-4-5"


def test_fable_still_blocked_with_allow_opus():
    from services import llm_router
    assert llm_router.clamp_model("claude-fable-5", allow_opus=True) == "claude-sonnet-5"


def test_opus47_not_in_allowlist():
    from services import llm_router
    assert llm_router.clamp_model("claude-opus-4-7", allow_opus=True) == "claude-sonnet-5"


def test_empty_with_allow_opus():
    from services import llm_router
    assert llm_router.clamp_model("", allow_opus=True) == "claude-sonnet-5"


# Integración: run_brief pasa allow_opus=True SIEMPRE
def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _patch_run_brief_deps(execution_id=30):
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


def test_run_brief_opus48_not_clamped():
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps() as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "x", "runtime": "claude_code_cli", "model": "claude-opus-4-8"},
                headers={"X-User-Email": "test@test.com"},
            )
    assert resp.status_code == 202, resp.get_data(as_text=True)
    _, kwargs = mock_run_agent.call_args
    assert kwargs.get("model_override") == "claude-opus-4-8", (
        f"Opus 4.8 debe pasar sin clamp en brief→épica, fue {kwargs.get('model_override')!r}"
    )
