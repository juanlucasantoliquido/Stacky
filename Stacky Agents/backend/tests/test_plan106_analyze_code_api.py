"""Plan 106 F3 — Blueprint /api/llm/analyze-code + /api/llm/local-health.

Fixtures: patrón test_plan90_devops_agent_endpoints.py (create_app + init_db + test_client).
Mocks: copilot_bridge.invoke_local_llm se importa lazy dentro de la ruta, así que
parchear en el módulo origen (mock.patch("copilot_bridge.invoke_local_llm", ...), gotcha plan 28).
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


def test_f3_flag_off_404(app_flag_off):
    c = _client(app_flag_off)
    assert c.get("/api/llm/local-health").status_code == 404
    assert c.post("/api/llm/analyze-code", json={"project": "p"}).status_code == 404


def test_f3_endpoint_empty_503(app_flag_on):
    import config as cfg
    cfg.config.LOCAL_LLM_ENDPOINT = ""
    c = _client(app_flag_on)
    assert c.post("/api/llm/analyze-code", json={"project": "p"}).status_code == 503
    cfg.config.LOCAL_LLM_ENDPOINT = "http://localhost:11434/v1/chat/completions"


def test_f3_no_project_400(app_flag_on):
    c = _client(app_flag_on)
    r = c.post("/api/llm/analyze-code", json={})
    assert r.status_code == 400


def test_f3_no_json_400(app_flag_on):
    c = _client(app_flag_on)
    r = c.post("/api/llm/analyze-code", data="project=p", content_type="application/x-www-form-urlencoded")
    assert r.status_code == 400


def test_f3_success_returns_markdown_analysis(app_flag_on):
    c = _client(app_flag_on)
    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text="## Hallazgos\nTodo bien.", format="markdown", metadata={}),
    ):
        r = c.post("/api/llm/analyze-code", json={"project": "proj-x", "files": []})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert "analysis" in body
    assert isinstance(body["execution_id"], int)


def test_f3_invoke_receives_hitl_prompt(app_flag_on):
    c = _client(app_flag_on)
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(text="ok", format="markdown", metadata={})

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy):
        c.post("/api/llm/analyze-code", json={"project": "proj-x"})
    assert "REGLA ABSOLUTA (HITL)" in captured["system"]
    assert "NUNCA ejecutes comandos" in captured["system"]


def test_f3_execution_created_and_completed(app_flag_on):
    c = _client(app_flag_on)
    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text="ok", format="markdown", metadata={}),
    ):
        r = c.post("/api/llm/analyze-code", json={"project": "proj-y"})
    body = r.get_json()
    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as s:
        ex = s.get(AgentExecution, body["execution_id"])
        assert ex is not None
        assert ex.started_by == "local_llm_api"
        assert ex.status == "completed"
        ticket = s.get(Ticket, ex.ticket_id)
        assert ticket.ado_id == -5


def test_f3_error_marks_execution_error_502(app_flag_on):
    c = _client(app_flag_on)
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("boom")):
        r = c.post("/api/llm/analyze-code", json={"project": "proj-z"})
    assert r.status_code == 502
    body = r.get_json()
    from db import session_scope
    from models import AgentExecution
    with session_scope() as s:
        ex = s.get(AgentExecution, body["execution_id"])
        assert ex.status == "error"
        assert ex.error_message


def test_f3_local_health_reachable_and_unreachable(app_flag_on):
    c = _client(app_flag_on)
    with mock.patch("api.local_llm_analysis.requests.get", return_value=mock.Mock(status_code=200)):
        r = c.get("/api/llm/local-health")
    assert r.status_code == 200
    assert r.get_json()["reachable"] is True

    import requests as _requests
    with mock.patch("api.local_llm_analysis.requests.get", side_effect=_requests.ConnectionError()):
        r = c.get("/api/llm/local-health")
    assert r.status_code == 200
    assert r.get_json()["reachable"] is False
