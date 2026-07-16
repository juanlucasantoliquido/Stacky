"""Plan 127 F7 (opcional) — POST /api/devops/doctor/explain-failure (C2).

Explica UN job fallido con el modelo local a partir del log ya clasificado
(Plan 96 failure_doctor). El log NO se persiste en input_context_json.
"""
from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def app_on():
    import config as cfg

    orig = {
        "STACKY_DEVOPS_DOCTOR_ENABLED": getattr(cfg.config, "STACKY_DEVOPS_DOCTOR_ENABLED", False),
        "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED": getattr(cfg.config, "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED", False),
        "LOCAL_LLM_ENABLED": getattr(cfg.config, "LOCAL_LLM_ENABLED", False),
        "LOCAL_LLM_ENDPOINT": getattr(cfg.config, "LOCAL_LLM_ENDPOINT", ""),
    }
    cfg.config.STACKY_DEVOPS_DOCTOR_ENABLED = True
    cfg.config.STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED = True
    cfg.config.LOCAL_LLM_ENABLED = True
    cfg.config.LOCAL_LLM_ENDPOINT = "http://localhost:11434/v1/chat/completions"

    from app import create_app
    from db import init_db

    app = create_app()
    app.config["TESTING"] = True
    init_db()
    yield app

    for key, value in orig.items():
        setattr(cfg.config, key, value)


def _c(app):
    return app.test_client()


def _fake_provider(log_text: str):
    provider = mock.MagicMock()
    provider.name = "gitlab"
    provider.get_job_log.return_value = log_text
    return provider


def test_404_sin_flag_96(app_on, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_DOCTOR_ENABLED", False, raising=False)
    c = _c(app_on)
    r = c.post("/api/devops/doctor/explain-failure", json={"project": "p", "pipeline_id": "1", "job_id": "1"})
    assert r.status_code == 404


def test_404_sin_flag_local(app_on, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED", False, raising=False)
    c = _c(app_on)
    r = c.post("/api/devops/doctor/explain-failure", json={"project": "p", "pipeline_id": "1", "job_id": "1"})
    assert r.status_code == 404


def test_400_body_incompleto(app_on):
    c = _c(app_on)
    r1 = c.post("/api/devops/doctor/explain-failure", json={"pipeline_id": "1", "job_id": "1"})
    assert r1.status_code == 400
    r2 = c.post("/api/devops/doctor/explain-failure", json={"project": "p", "job_id": "1"})
    assert r2.status_code == 400
    r3 = c.post("/api/devops/doctor/explain-failure", json={"project": "p", "pipeline_id": "1"})
    assert r3.status_code == 400


def test_ok_con_mocks(app_on):
    c = _c(app_on)
    provider = _fake_provider("step 1\nnpm ERR! code E404\nstep 2")
    with mock.patch("services.ci_logs_provider.get_ci_logs_provider", return_value=provider):
        with mock.patch(
            "copilot_bridge.invoke_local_llm",
            return_value=mock.Mock(text="## Qué falló\nDependencia inexistente.", format="markdown", metadata={}),
        ):
            r = c.post(
                "/api/devops/doctor/explain-failure",
                json={"project": "proj-x", "pipeline_id": "55", "job_id": "1"},
            )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["analysis"]


def test_log_no_persiste(app_on):
    c = _c(app_on)
    provider = _fake_provider("step 1\nnpm ERR! code E404\nstep 2")
    with mock.patch("services.ci_logs_provider.get_ci_logs_provider", return_value=provider):
        with mock.patch(
            "copilot_bridge.invoke_local_llm",
            return_value=mock.Mock(text="ok", format="markdown", metadata={}),
        ):
            r = c.post(
                "/api/devops/doctor/explain-failure",
                json={"project": "proj-x", "pipeline_id": "55", "job_id": "1"},
            )
    execution_id = r.get_json()["execution_id"]

    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        assert "npm ERR!" not in row.input_context_json
        assert '"log_chars"' in row.input_context_json


def test_log_con_secreto_no_llega_al_modelo(app_on):
    c = _c(app_on)
    provider = _fake_provider("step 1\npassword=hunter2\nnpm ERR! code E404\nstep 2")
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(text="ok", format="markdown", metadata={})

    with mock.patch("services.ci_logs_provider.get_ci_logs_provider", return_value=provider):
        with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy):
            c.post(
                "/api/devops/doctor/explain-failure",
                json={"project": "proj-x", "pipeline_id": "55", "job_id": "1"},
            )
    assert "hunter2" not in captured["user"]
