"""Plan 106 F4 — /api/llm/suggest-pipeline (sugerencias de pipeline, sin tool use).

Mismo patrón de fixtures/mock que test_plan106_analyze_code_api.py.
"""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def app_flag_on():
    import config as cfg
    orig = getattr(cfg.config, "LOCAL_LLM_ENABLED", False)
    orig_endpoint = getattr(cfg.config, "LOCAL_LLM_ENDPOINT", "")
    cfg.config.LOCAL_LLM_ENABLED = True
    cfg.config.LOCAL_LLM_ENDPOINT = "http://localhost:11434/v1/chat/completions"
    from app import create_app
    from db import init_db
    app = create_app()
    app.config["TESTING"] = True
    init_db()
    yield app
    cfg.config.LOCAL_LLM_ENABLED = orig
    cfg.config.LOCAL_LLM_ENDPOINT = orig_endpoint


@pytest.fixture
def app_flag_off():
    import config as cfg
    orig = getattr(cfg.config, "LOCAL_LLM_ENABLED", False)
    cfg.config.LOCAL_LLM_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.LOCAL_LLM_ENABLED = orig


def _client(app):
    return app.test_client()


def test_f4_flag_off_404(app_flag_off):
    c = _client(app_flag_off)
    r = c.post("/api/llm/suggest-pipeline", json={"project": "p", "stack": "python"})
    assert r.status_code == 404


def test_f4_no_project_or_stack_400(app_flag_on):
    c = _client(app_flag_on)
    assert c.post("/api/llm/suggest-pipeline", json={}).status_code == 400
    assert c.post("/api/llm/suggest-pipeline", json={"project": "p"}).status_code == 400
    assert c.post("/api/llm/suggest-pipeline", json={"stack": "python"}).status_code == 400


def test_f4_success_returns_suggestions_json(app_flag_on):
    c = _client(app_flag_on)
    payload = {
        "working_directory": "backend",
        "condition": "branch == main",
        "environment_variables": {"ENV": "prod"},
        "justification": "Detecté un proyecto Python en backend/.",
    }
    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text=__import__("json").dumps(payload), format="markdown", metadata={}),
    ):
        r = c.post("/api/llm/suggest-pipeline", json={"project": "proj-x", "stack": "python"})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    s = body["suggestions"]
    assert s["working_directory"] == "backend"
    assert s["condition"] == "branch == main"
    assert s["environment_variables"] == {"ENV": "prod"}
    assert s["justification"]


def test_f4_parse_strips_markdown_fence(app_flag_on):
    c = _client(app_flag_on)
    import json as _json
    payload = {
        "working_directory": "", "condition": "", "environment_variables": {}, "justification": "n/a",
    }
    fenced = "```json\n" + _json.dumps(payload) + "\n```"
    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text=fenced, format="markdown", metadata={}),
    ):
        r = c.post("/api/llm/suggest-pipeline", json={"project": "proj-x", "stack": "python"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["suggestions"]["justification"] == "n/a"


def test_f4_json_parse_error_502(app_flag_on):
    c = _client(app_flag_on)
    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text="esto no es json", format="markdown", metadata={}),
    ):
        r = c.post("/api/llm/suggest-pipeline", json={"project": "proj-x", "stack": "python"})
    assert r.status_code == 502
    body = r.get_json()
    assert body["error"] == "json_parse_error"
    assert "raw_response" in body

    from db import session_scope
    from models import AgentExecution
    with session_scope() as s:
        ex = s.get(AgentExecution, body["execution_id"])
        assert ex.status == "error"


def test_f4_invoke_receives_hitl_prompt(app_flag_on):
    c = _client(app_flag_on)
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(text='{"working_directory":"","condition":"","environment_variables":{},"justification":""}', format="markdown", metadata={})

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy):
        c.post("/api/llm/suggest-pipeline", json={"project": "proj-x", "stack": "python"})
    assert "REGLA ABSOLUTA (HITL)" in captured["system"]
