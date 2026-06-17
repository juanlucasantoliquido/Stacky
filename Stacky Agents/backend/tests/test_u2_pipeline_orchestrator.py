from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _init_app_for_schema():
    from app import create_app

    create_app()


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    from db import session_scope
    from models import AgentExecution, PipelineRun, Ticket

    yield
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(PipelineRun).delete()
        session.query(Ticket).delete()


def _seed_ticket() -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=93001,
            project="TEST",
            stacky_project_name="TEST",
            title="ticket pipeline",
            ado_state="Active",
        )
        session.add(t)
        session.flush()
        return t.id


def test_pipelines_endpoint_disabled_by_default(client):
    resp = client.post("/api/pipelines", json={"ticket_id": 1})
    assert resp.status_code == 404


def test_pipeline_start_and_advance(monkeypatch):
    from db import session_scope
    from models import AgentExecution, PipelineRun
    from services import pipeline_orchestrator

    ticket_id = _seed_ticket()
    monkeypatch.setattr(pipeline_orchestrator.config, "STACKY_PIPELINES_ENABLED", True)

    launches: list[int] = []

    def _fake_run_agent(*, agent_type, ticket_id, context_blocks, chain_from, user, runtime, project_name):
        with session_scope() as session:
            e = AgentExecution(
                ticket_id=ticket_id,
                agent_type=agent_type,
                status="running",
                input_context_json="[]",
                started_by="test",
            )
            session.add(e)
            session.flush()
            launches.append(e.id)
            return e.id

    monkeypatch.setattr(pipeline_orchestrator.agent_runner, "run_agent", _fake_run_agent)

    started = pipeline_orchestrator.start(ticket_id=ticket_id)
    first_exec = started["launched_execution_id"]
    assert first_exec in launches

    pipeline_orchestrator.on_execution_end(execution_id=first_exec, final_status="completed")

    with session_scope() as session:
        run = session.query(PipelineRun).first()
        assert run is not None
        assert run.status == "running"
        assert run.current_stage == 1
        assert run.last_execution_id in launches
        assert len(launches) == 2


def test_pipeline_pauses_on_error(monkeypatch):
    from db import session_scope
    from models import AgentExecution, PipelineRun
    from services import pipeline_orchestrator

    ticket_id = _seed_ticket()
    monkeypatch.setattr(pipeline_orchestrator.config, "STACKY_PIPELINES_ENABLED", True)

    def _fake_run_agent(*, agent_type, ticket_id, context_blocks, chain_from, user, runtime, project_name):
        with session_scope() as session:
            e = AgentExecution(
                ticket_id=ticket_id,
                agent_type=agent_type,
                status="running",
                input_context_json="[]",
                started_by="test",
            )
            session.add(e)
            session.flush()
            return e.id

    monkeypatch.setattr(pipeline_orchestrator.agent_runner, "run_agent", _fake_run_agent)

    started = pipeline_orchestrator.start(ticket_id=ticket_id)
    pipeline_orchestrator.on_execution_end(
        execution_id=started["launched_execution_id"],
        final_status="error",
    )

    with session_scope() as session:
        run = session.query(PipelineRun).first()
        assert run is not None
        assert run.status == "paused"
