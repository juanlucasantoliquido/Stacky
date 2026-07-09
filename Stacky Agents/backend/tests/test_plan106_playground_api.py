"""Plan 106 (mejora aditiva) — Playground IA local + selector de modelos.

Cubre:
- GET  /api/llm/local-models   (flag OFF→404, endpoint vacío→503, server ok→lista,
                                 server caído→models vacíos sin 500)
- POST /api/llm/playground     (prompt requerido→400, happy path, error bridge→502)
- pass-through de `model` por request en analyze-code y suggest-pipeline

Mocks: copilot_bridge.invoke_local_llm se importa lazy dentro de la ruta → parchear
en el módulo origen (gotcha plan 28). requests.get se parchea en el módulo del blueprint.
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


# ── GET /local-models ──────────────────────────────────────────────────────────

def test_models_flag_off_404(app_flag_off):
    c = _client(app_flag_off)
    assert c.get("/api/llm/local-models").status_code == 404


def test_models_endpoint_empty_503(app_flag_on):
    import config as cfg
    cfg.config.LOCAL_LLM_ENDPOINT = ""
    c = _client(app_flag_on)
    assert c.get("/api/llm/local-models").status_code == 503
    cfg.config.LOCAL_LLM_ENDPOINT = "http://localhost:11434/v1/chat/completions"


def test_models_server_ok_returns_parsed_list(app_flag_on):
    c = _client(app_flag_on)
    fake = mock.Mock(status_code=200)
    fake.json.return_value = {"data": [{"id": "qwen3:32b"}, {"id": "llama3"}]}
    with mock.patch("api.local_llm_analysis.requests.get", return_value=fake):
        r = c.get("/api/llm/local-models")
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["reachable"] is True
    assert body["models"] == ["qwen3:32b", "llama3"]
    import config as cfg
    assert body["current"] == cfg.config.LOCAL_LLM_MODEL


def test_models_server_down_empty_no_500(app_flag_on):
    import requests as _requests
    c = _client(app_flag_on)
    with mock.patch(
        "api.local_llm_analysis.requests.get",
        side_effect=_requests.ConnectionError(),
    ):
        r = c.get("/api/llm/local-models")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["reachable"] is False
    assert body["models"] == []


def test_models_malformed_json_empty_no_500(app_flag_on):
    c = _client(app_flag_on)
    fake = mock.Mock(status_code=200)
    fake.json.return_value = {"unexpected": "shape"}
    with mock.patch("api.local_llm_analysis.requests.get", return_value=fake):
        r = c.get("/api/llm/local-models")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["models"] == []


# ── POST /playground ─────────────────────────────────────────────────────────────

def test_playground_flag_off_404(app_flag_off):
    c = _client(app_flag_off)
    assert c.post("/api/llm/playground", json={"prompt": "hola"}).status_code == 404


def test_playground_prompt_required_400(app_flag_on):
    c = _client(app_flag_on)
    assert c.post("/api/llm/playground", json={}).status_code == 400
    assert c.post("/api/llm/playground", json={"prompt": "  "}).status_code == 400


def test_playground_happy_path(app_flag_on):
    c = _client(app_flag_on)
    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(
            text="respuesta del modelo",
            format="markdown",
            metadata={"model": "qwen3:32b"},
        ),
    ):
        r = c.post("/api/llm/playground", json={"prompt": "hola mundo"})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["response"] == "respuesta del modelo"
    assert body["model"] == "qwen3:32b"
    assert isinstance(body["execution_id"], int)

    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as s:
        ex = s.get(AgentExecution, body["execution_id"])
        assert ex is not None
        assert ex.status == "completed"
        ticket = s.get(Ticket, ex.ticket_id)
        assert ticket.ado_id == -5


def test_playground_forwards_model_and_system(app_flag_on):
    c = _client(app_flag_on)
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(text="ok", format="markdown", metadata={"model": "my-model"})

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy):
        c.post(
            "/api/llm/playground",
            json={"prompt": "probando", "model": "my-model", "system": "sos un test"},
        )
    assert captured["model"] == "my-model"
    assert captured["user"] == "probando"
    assert captured["system"] == "sos un test"


def test_playground_default_system_is_hitl(app_flag_on):
    c = _client(app_flag_on)
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(text="ok", format="markdown", metadata={"model": "m"})

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy):
        c.post("/api/llm/playground", json={"prompt": "hola"})
    assert "REGLA ABSOLUTA (HITL)" in captured["system"]


def test_playground_bridge_error_502(app_flag_on):
    c = _client(app_flag_on)
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("boom")):
        r = c.post("/api/llm/playground", json={"prompt": "hola"})
    assert r.status_code == 502
    body = r.get_json()
    from db import session_scope
    from models import AgentExecution
    with session_scope() as s:
        ex = s.get(AgentExecution, body["execution_id"])
        assert ex.status == "error"
        assert ex.error_message


# ── model pass-through en endpoints existentes ──────────────────────────────────

def test_analyze_code_forwards_model(app_flag_on):
    c = _client(app_flag_on)
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(text="ok", format="markdown", metadata={})

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy):
        c.post("/api/llm/analyze-code", json={"project": "p", "model": "codellama"})
    assert captured["model"] == "codellama"


def test_analyze_code_no_model_forwards_none(app_flag_on):
    c = _client(app_flag_on)
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(text="ok", format="markdown", metadata={})

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy):
        c.post("/api/llm/analyze-code", json={"project": "p"})
    assert captured.get("model") is None


def test_suggest_pipeline_forwards_model(app_flag_on):
    c = _client(app_flag_on)
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(
            text='{"working_directory":"","condition":"","environment_variables":{},"justification":""}',
            format="markdown",
            metadata={},
        )

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy):
        c.post(
            "/api/llm/suggest-pipeline",
            json={"project": "p", "stack": "python", "model": "qwen3:14b"},
        )
    assert captured["model"] == "qwen3:14b"
