"""Plan 110 F4 — Revisión Haiku solo-lectura (sin herramientas) + timeout real (C2)."""
import os
import types
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def app_on():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_PR_REVIEWER_ENABLED", False)
    orig_model = getattr(cfg.config, "STACKY_PR_REVIEW_HAIKU_MODEL", "")
    cfg.config.STACKY_PR_REVIEWER_ENABLED = True
    cfg.config.STACKY_PR_REVIEW_HAIKU_MODEL = "claude-3.5-haiku"
    from app import create_app
    from db import init_db
    app = create_app()
    app.config["TESTING"] = True
    init_db()
    yield app
    cfg.config.STACKY_PR_REVIEWER_ENABLED = orig
    cfg.config.STACKY_PR_REVIEW_HAIKU_MODEL = orig_model


@pytest.fixture
def app_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_PR_REVIEWER_ENABLED", False)
    cfg.config.STACKY_PR_REVIEWER_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PR_REVIEWER_ENABLED = orig


def _provider(diff_text="algo de diff"):
    provider = mock.MagicMock()
    provider.name = "gitlab"
    provider.get_merge_request.return_value = {
        "id": "7", "state": "open", "pipeline_status": "success", "mergeable": True,
        "source_branch": "feat", "target_branch": "main", "web_url": "u",
    }
    provider.get_merge_request_diff.return_value = {
        "id": "7", "files": [{"path": "a.py", "change_type": "modified"}],
        "diff_text": diff_text, "diff_available": True, "note": "",
    }
    return provider


def _resp(text):
    return types.SimpleNamespace(text=text, metadata={})


def test_review_haiku_404_when_flag_off(app_off):
    c = app_off.test_client()
    assert c.post("/api/pr-review/review/haiku", json={"project": "p", "mr_id": "7"}).status_code == 404


def test_rejects_non_haiku_model(app_on):
    import config as cfg
    cfg.config.STACKY_PR_REVIEW_HAIKU_MODEL = "gpt-4o"
    c = app_on.test_client()
    with mock.patch("copilot_bridge.invoke_haiku") as inv:
        resp = c.post("/api/pr-review/review/haiku", json={"project": "p", "mr_id": "7"})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "model_not_haiku"
        inv.assert_not_called()
    cfg.config.STACKY_PR_REVIEW_HAIKU_MODEL = "claude-3.5-haiku"


def test_haiku_review_is_toolless_chat(app_on):
    c = app_on.test_client()
    captured = {}

    def _fake(**kwargs):
        captured.update(kwargs)
        return _resp('{"summary": "ok", "findings": [], '
                     '"recommended_action": {"type": "approve", "label": "Aprobar", "params": {}}, '
                     '"confidence": 0.8}')

    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider()):
        with mock.patch("copilot_bridge.invoke_haiku", side_effect=_fake):
            resp = c.post("/api/pr-review/review/haiku", json={"project": "p", "mr_id": "7"})
    assert resp.status_code == 200
    assert "haiku" in captured["model"].lower()
    # completion de chat pura: sin ningún parámetro de herramientas
    assert "tools" not in captured and "tool_choice" not in captured
    assert resp.get_json()["review"]["recommended_action"]["type"] == "approve"


def test_review_json_parsed_and_action_coerced(app_on):
    c = app_on.test_client()
    bad = '{"summary": "x", "findings": [], "recommended_action": {"type": "rm -rf", "label": "?", "params": {}}, "confidence": 0.5}'
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider()):
        with mock.patch("copilot_bridge.invoke_haiku", return_value=_resp(bad)):
            resp = c.post("/api/pr-review/review/haiku", json={"project": "p", "mr_id": "7"})
    assert resp.status_code == 200
    assert resp.get_json()["review"]["recommended_action"]["type"] == "none"


def test_execution_row_never_stores_raw_diff(app_on):
    c = app_on.test_client()
    secret_diff = "SENTINEL_DIFF_CONTENT_12345"
    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider(secret_diff)):
        with mock.patch("copilot_bridge.invoke_haiku", return_value=_resp('{"summary":"ok"}')):
            resp = c.post("/api/pr-review/review/haiku", json={"project": "p", "mr_id": "7"})
    execution_id = resp.get_json()["execution_id"]
    from db import session_scope
    from models import AgentExecution
    with session_scope() as s:
        ex = s.get(AgentExecution, execution_id)
        assert secret_diff not in (ex.input_context_json or "")
        assert '"diff_chars"' in ex.input_context_json  # solo metadatos


def test_invoke_haiku_raises_on_non_haiku():
    import copilot_bridge
    with pytest.raises(ValueError):
        copilot_bridge.invoke_haiku(agent_type="x", system="s", user="u",
                                    on_log=lambda l, m: None, model="gpt-4o")


def test_timeout_flag_is_wired(app_on):
    """C2 — el timeout de la flag llega a invoke_haiku y a requests.post."""
    import config as cfg
    cfg.config.STACKY_PR_REVIEW_TIMEOUT_SEC = 45
    c = app_on.test_client()
    captured = {}

    def _fake(**kwargs):
        captured.update(kwargs)
        return _resp('{"summary":"ok"}')

    with mock.patch("api.pr_review.get_merge_request_provider", return_value=_provider()):
        with mock.patch("copilot_bridge.invoke_haiku", side_effect=_fake):
            c.post("/api/pr-review/review/haiku", json={"project": "p", "mr_id": "7"})
    assert captured["timeout"] == 45
    cfg.config.STACKY_PR_REVIEW_TIMEOUT_SEC = 120

    # Unit: _invoke_copilot acepta timeout y lo propaga a requests.post
    import copilot_bridge
    with mock.patch("copilot_bridge._get_copilot_token", return_value="tok"):
        with mock.patch("copilot_bridge.requests.post") as post:
            post.return_value = types.SimpleNamespace(
                status_code=200,
                json=lambda: {"choices": [{"message": {"content": "hola"}}], "usage": {}},
                text="ok",
            )
            copilot_bridge.invoke_haiku(agent_type="x", system="s", user="u",
                                        on_log=lambda l, m: None, model="claude-3.5-haiku", timeout=45)
            assert post.call_args.kwargs["timeout"] == 45
