"""Plan 127 F5 — POST /api/devops/sections/<section_id>/doctor/local (C3).

Mockea copilot_bridge.invoke_local_llm; los estados "off" se logran apagando
a mano vía monkeypatch sobre config.config.
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
        "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED": getattr(cfg.config, "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED", False),
        "LOCAL_LLM_ENABLED": getattr(cfg.config, "LOCAL_LLM_ENABLED", False),
        "LOCAL_LLM_ENDPOINT": getattr(cfg.config, "LOCAL_LLM_ENDPOINT", ""),
        "STACKY_DEVOPS_AGENT_ENABLED": getattr(cfg.config, "STACKY_DEVOPS_AGENT_ENABLED", False),
        "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED": getattr(cfg.config, "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED", False),
    }
    cfg.config.STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED = True
    cfg.config.LOCAL_LLM_ENABLED = True
    cfg.config.LOCAL_LLM_ENDPOINT = "http://localhost:11434/v1/chat/completions"
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = False
    cfg.config.STACKY_DEVOPS_SECTION_DOCTOR_ENABLED = False

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


def test_flag_off_404(app_on, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED", False, raising=False)
    c = _c(app_on)
    r = c.post("/api/devops/sections/pipeline/doctor/local", json={"project": "p", "payload": {}})
    assert r.status_code == 404


def test_local_llm_off_404(app_on, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENABLED", False, raising=False)
    c = _c(app_on)
    r = c.post("/api/devops/sections/pipeline/doctor/local", json={"project": "p", "payload": {}})
    assert r.status_code == 404


def test_unknown_section_404(app_on):
    c = _c(app_on)
    r = c.post("/api/devops/sections/no_existe/doctor/local", json={"project": "p", "payload": {}})
    assert r.status_code == 404
    assert r.get_json()["error"] == "unknown_section"


def test_body_invalido_400(app_on):
    c = _c(app_on)
    r1 = c.post("/api/devops/sections/pipeline/doctor/local", json={"payload": {}})
    assert r1.status_code == 400
    r2 = c.post("/api/devops/sections/pipeline/doctor/local", json={"project": "p"})
    assert r2.status_code == 400


def test_ok_sin_agente_devops(app_on):
    """KPI-3 — con AGENT_ENABLED=false y SECTION_DOCTOR_ENABLED=false, el doctor
    local sigue funcionando (camino independiente al cloud)."""
    c = _c(app_on)
    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text="## Hallazgos\nTodo bien.", format="markdown", metadata={"model": "qwen-test"}),
    ):
        r = c.post(
            "/api/devops/sections/pipeline/doctor/local",
            json={"project": "proj-x", "payload": {"spec": {"name": "x"}}},
        )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["analysis"]
    assert body["elapsed_ms"] >= 0

    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, body["execution_id"])
        assert row.agent_type == "local_llm_devops_doctor"


def test_redacta_secretos_en_user(app_on):
    c = _c(app_on)
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return mock.Mock(text="ok", format="markdown", metadata={})

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=_spy):
        c.post(
            "/api/devops/sections/environments/doctor/local",
            json={"project": "proj-x", "payload": {"vars": {"DB_PASSWORD": "hunter2"}}},
        )
    assert "hunter2" not in captured["user"]


def test_bridge_caido_502(app_on):
    c = _c(app_on)
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("bridge down")):
        r = c.post(
            "/api/devops/sections/pipeline/doctor/local",
            json={"project": "proj-x", "payload": {"spec": {"name": "x"}}},
        )
    assert r.status_code == 502


def test_health_expone_local_doctor_enabled(app_on):
    c = _c(app_on)
    r = c.get("/api/devops/health")
    assert r.status_code == 200
    assert r.get_json()["local_doctor_enabled"] is True


def test_health_conjuncion_local_llm_off(app_on, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENABLED", False, raising=False)
    c = _c(app_on)
    r = c.get("/api/devops/health")
    assert r.status_code == 200
    assert r.get_json()["local_doctor_enabled"] is False
