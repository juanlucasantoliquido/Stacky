"""Plan 127 F3 — POST /api/llm/executions/<id>/error-analysis (C1).

Mockea invoke_local_llm en el módulo origen copilot_bridge.invoke_local_llm
(la route lo importa lazy, gotcha documentado del repo). Los POST llevan json={}.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def app_flag_on():
    import config as cfg

    orig_local = getattr(cfg.config, "LOCAL_LLM_ENABLED", False)
    orig_endpoint = getattr(cfg.config, "LOCAL_LLM_ENDPOINT", "")
    orig_error_analysis = getattr(cfg.config, "STACKY_EXEC_ERROR_ANALYSIS_ENABLED", False)
    cfg.config.LOCAL_LLM_ENABLED = True
    cfg.config.LOCAL_LLM_ENDPOINT = "http://localhost:11434/v1/chat/completions"
    cfg.config.STACKY_EXEC_ERROR_ANALYSIS_ENABLED = True

    from app import create_app
    from db import init_db

    app = create_app()
    app.config["TESTING"] = True
    init_db()
    yield app

    cfg.config.LOCAL_LLM_ENABLED = orig_local
    cfg.config.LOCAL_LLM_ENDPOINT = orig_endpoint
    cfg.config.STACKY_EXEC_ERROR_ANALYSIS_ENABLED = orig_error_analysis


def _client(app):
    return app.test_client()


_counter = {"n": 60000}


def _mk_ticket(project="proj-err"):
    from db import session_scope
    from models import Ticket

    _counter["n"] += 1
    with session_scope() as session:
        t = Ticket(
            ado_id=-(_counter["n"]),
            project=project,
            title=f"t-{_counter['n']}",
            ado_state="To Do",
        )
        session.add(t)
        session.flush()
        return t.id


def _mk_execution(ticket_id: int, *, status: str, error_message: str = "", output: str = "boom output"):
    from db import session_scope
    from models import AgentExecution

    now = datetime.utcnow()
    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=now - timedelta(minutes=5),
            completed_at=now,
            error_message=error_message or None,
            output=output,
        )
        session.add(e)
        session.flush()
        return e.id


def _get_metadata(execution_id: int) -> dict:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        return row.metadata_dict or {}


def _get_row(execution_id: int):
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        return {"status": row.status, "agent_type": row.agent_type} if row else None


def test_flag_off_404(app_flag_on):
    import config as cfg

    monkeypatch_value = cfg.config.STACKY_EXEC_ERROR_ANALYSIS_ENABLED
    cfg.config.STACKY_EXEC_ERROR_ANALYSIS_ENABLED = False
    try:
        c = _client(app_flag_on)
        tid = _mk_ticket()
        eid = _mk_execution(tid, status="error", error_message="boom")
        r = c.post(f"/api/llm/executions/{eid}/error-analysis", json={})
        assert r.status_code == 404
        assert r.get_json()["error"] == "error_analysis_disabled"
    finally:
        cfg.config.STACKY_EXEC_ERROR_ANALYSIS_ENABLED = monkeypatch_value


def test_local_llm_off_404(app_flag_on):
    import config as cfg

    orig = cfg.config.LOCAL_LLM_ENABLED
    cfg.config.LOCAL_LLM_ENABLED = False
    try:
        c = _client(app_flag_on)
        tid = _mk_ticket()
        eid = _mk_execution(tid, status="error", error_message="boom")
        r = c.post(f"/api/llm/executions/{eid}/error-analysis", json={})
        assert r.status_code == 404
    finally:
        cfg.config.LOCAL_LLM_ENABLED = orig


def test_execution_inexistente_404(app_flag_on):
    c = _client(app_flag_on)
    r = c.post("/api/llm/executions/999999/error-analysis", json={})
    assert r.status_code == 404
    assert r.get_json()["error"] == "execution_not_found"


def test_nothing_to_analyze_409(app_flag_on):
    c = _client(app_flag_on)
    tid = _mk_ticket()
    eid = _mk_execution(tid, status="completed", error_message="")
    r = c.post(f"/api/llm/executions/{eid}/error-analysis", json={})
    assert r.status_code == 409
    assert r.get_json()["error"] == "nothing_to_analyze"


def test_ok_persiste_metadata(app_flag_on):
    c = _client(app_flag_on)
    tid = _mk_ticket()
    eid = _mk_execution(tid, status="error", error_message="boom: crashed")

    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text="## Qué pasó\nSe cayó.", format="markdown", metadata={"model": "qwen-test"}),
    ):
        r = c.post(f"/api/llm/executions/{eid}/error-analysis", json={})

    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["elapsed_ms"] >= 0
    assert isinstance(body["analyzer_execution_id"], int)

    md = _get_metadata(eid)
    assert md["error_analysis"]["analysis"]
    assert md["error_analysis"]["elapsed_ms"] >= 0

    analyzer_row = _get_row(body["analyzer_execution_id"])
    assert analyzer_row["agent_type"] == "local_llm_error_analyst"
    assert analyzer_row["status"] == "completed"


def test_regenerar_sobrescribe(app_flag_on):
    c = _client(app_flag_on)
    tid = _mk_ticket()
    eid = _mk_execution(tid, status="error", error_message="boom")

    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text="primer análisis", format="markdown", metadata={"model": "qwen-test"}),
    ):
        c.post(f"/api/llm/executions/{eid}/error-analysis", json={})
    first_generated_at = _get_metadata(eid)["error_analysis"]["generated_at"]

    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text="segundo análisis", format="markdown", metadata={"model": "qwen-test"}),
    ):
        c.post(f"/api/llm/executions/{eid}/error-analysis", json={})
    second_md = _get_metadata(eid)["error_analysis"]

    assert second_md["analysis"] == "segundo análisis"
    # generated_at se recalcula en cada llamada (idempotente por sobrescritura)
    assert "generated_at" in second_md
    assert first_generated_at is not None


def test_bridge_caido_502_sin_persistencia(app_flag_on):
    c = _client(app_flag_on)
    tid = _mk_ticket()
    eid = _mk_execution(tid, status="error", error_message="boom")

    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("bridge down")):
        r = c.post(f"/api/llm/executions/{eid}/error-analysis", json={})

    assert r.status_code == 502
    md = _get_metadata(eid)
    assert "error_analysis" not in md


def test_secreto_no_persiste(app_flag_on):
    c = _client(app_flag_on)
    tid = _mk_ticket()
    eid = _mk_execution(tid, status="error", error_message="password=hunter2 en el deploy")

    with mock.patch(
        "copilot_bridge.invoke_local_llm",
        return_value=mock.Mock(text="El error fue password=hunter2 en el deploy", format="markdown", metadata={}),
    ):
        r = c.post(f"/api/llm/executions/{eid}/error-analysis", json={})

    assert r.status_code == 200
    md = _get_metadata(eid)
    assert "hunter2" not in md["error_analysis"]["analysis"]


def test_agent_types_excluidos_de_insights():
    from services.local_insights import EXCLUDED_AGENT_TYPES

    assert "local_llm_error_analyst" in EXCLUDED_AGENT_TYPES
    assert "local_llm_devops_doctor" in EXCLUDED_AGENT_TYPES
    assert "local_llm_ci_explainer" in EXCLUDED_AGENT_TYPES
