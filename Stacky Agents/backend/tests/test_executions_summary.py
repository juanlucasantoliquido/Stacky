"""Plan 156 F1 — Tests del endpoint GET /api/executions/summary (latido unico).

Cubre:
- Agrupado por estado (running/preparing/queued) sin fugar completed.
- Paridad EXACTA de campos vs /api/executions (dict a dict) para el mismo scope.
- Filtrado por proyecto (scope=project) vs visibilidad global (scope=all_projects).
- Respuesta vacia bien formada (3 keys, arrays vacios, HTTP 200).

Patron de DB real: DATABASE_URL en memoria ANTES de importar la app; se siembra
AgentExecution/Ticket directo (evita el thread de agent_runner, ver
test_agent_history_endpoint.py). clean_db autouse aisla entre tests.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


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
    from models import AgentExecution, Ticket

    yield
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()


def _seed_ticket(ado_id: int, *, project: str = "RSPacifico", stacky_project_name=None) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project=project,
            stacky_project_name=stacky_project_name,
            title=f"ticket {ado_id}",
            ado_state="To Do",
        )
        session.add(t)
        session.flush()
        return t.id


def _seed_execution(ticket_id: int, *, status: str, agent_type: str = "developer", started_offset_min: int = 0) -> int:
    from db import session_scope
    from models import AgentExecution

    started = datetime.utcnow() - timedelta(minutes=started_offset_min)
    with session_scope() as session:
        row = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            output_format="markdown",
            started_by="test",
            started_at=started,
        )
        session.add(row)
        session.flush()
        return row.id


def test_summary_agrupa_por_estado(client):
    ticket = _seed_ticket(ado_id=20001)
    _seed_execution(ticket, status="running")
    _seed_execution(ticket, status="preparing")
    _seed_execution(ticket, status="queued")
    _seed_execution(ticket, status="completed")  # NO debe aparecer

    r = client.get("/api/executions/summary?scope=all_projects")
    assert r.status_code == 200
    body = r.get_json()
    assert set(("scope", "running", "preparing", "queued")).issubset(body.keys())
    assert len(body["running"]) == 1
    assert len(body["preparing"]) == 1
    assert len(body["queued"]) == 1
    # completed no debe estar en ninguno de los 3 arrays
    all_statuses = [
        e["status"] for e in body["running"] + body["preparing"] + body["queued"]
    ]
    assert "completed" not in all_statuses


def test_summary_paridad_de_campos_running(client):
    ticket = _seed_ticket(ado_id=20002)
    _seed_execution(ticket, status="running", started_offset_min=3)
    _seed_execution(ticket, status="running", started_offset_min=1)
    _seed_execution(ticket, status="preparing")

    list_resp = client.get("/api/executions?status=running&all_projects=true")
    summary_resp = client.get("/api/executions/summary?scope=all_projects")
    assert list_resp.status_code == 200
    assert summary_resp.status_code == 200

    list_running = list_resp.get_json()
    summary_running = summary_resp.get_json()["running"]

    # Paridad EXACTA dict a dict (mismos ids, mismo objeto campo por campo).
    assert list_running == summary_running
    assert len(list_running) == 2


def test_summary_scope_project_filtra(client, monkeypatch):
    import api.executions as execmod
    from services.project_context import ProjectContext

    ticket_a = _seed_ticket(ado_id=20003, project="ProjA", stacky_project_name="PROJ_A")
    ticket_b = _seed_ticket(ado_id=20004, project="ProjB", stacky_project_name="PROJ_B")
    _seed_execution(ticket_a, status="running")
    _seed_execution(ticket_b, status="running")

    fake_ctx = ProjectContext(
        stacky_project_name="PROJ_A",
        tracker_type="azure_devops",
        tracker_project="ProjA",
    )
    monkeypatch.setattr(execmod, "resolve_project_context", lambda *a, **k: fake_ctx)

    # scope=project (proyecto activo = PROJ_A) → solo runs de PROJ_A
    proj = client.get("/api/executions/summary?scope=project").get_json()
    proj_tickets = {e["ticket_id"] for e in proj["running"]}
    assert proj_tickets == {ticket_a}

    # scope=all_projects → todos
    all_p = client.get("/api/executions/summary?scope=all_projects").get_json()
    all_tickets = {e["ticket_id"] for e in all_p["running"]}
    assert all_tickets == {ticket_a, ticket_b}


def test_summary_vacio_ok(client):
    _seed_ticket(ado_id=20005)  # sin ejecuciones activas

    r = client.get("/api/executions/summary?scope=all_projects")
    assert r.status_code == 200
    body = r.get_json()
    assert body["running"] == []
    assert body["preparing"] == []
    assert body["queued"] == []
