"""
Tests para el endpoint /api/agents/vscode/<filename>/history.

Cubre:
- Mapeo filename → agent_type (developer, qa, technical, custom).
- Filtrado de ejecuciones por tipo inferido.
- Agrupado por ticket: cada ticket aparece una sola vez con su última ejecución.
- `executions_count` cuenta todas las ejecuciones del tipo en ese ticket.
- Validación de filename (path traversal, extensión obligatoria).
- Caso "custom" → tickets vacío + mapping_note explicativo.

Notas de implementación
-----------------------
1) Sembramos AgentExecution directamente en la BD en lugar de usar
   `/api/agents/run`. Razón: `agent_runner.py` lanza un thread que abre su
   propia sesión de DB; con `sqlite:///:memory:` cada conexión obtiene su
   propio in-memory database, lo que produce errores `no such table` en el
   thread (el smoke test `test_run_agent_creates_execution` exhibe el mismo
   problema preexistente). Sembrar directo evita la concurrencia.

2) Los tests usan `clean_db` (autouse) para vaciar AgentExecution + Ticket
   entre cada test. El engine de SQLAlchemy es module-level y compartido,
   así que sin esto la state de un test contamina al siguiente.
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
    """Vacía AgentExecution y Ticket entre tests para aislamiento."""
    from db import session_scope
    from models import AgentExecution, Ticket

    yield  # corre el test
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()


def _seed_ticket(ado_id: int, title: str = "dummy") -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="RSPacifico", title=title, ado_state="To Do")
        session.add(t)
        session.flush()
        return t.id


def _seed_execution(
    ticket_id: int,
    agent_type: str,
    *,
    status: str = "completed",
    verdict: str | None = "approved",
    started_offset_min: int = 0,
) -> int:
    """Crea un AgentExecution sin pasar por agent_runner (evita el thread)."""
    from db import session_scope
    from models import AgentExecution

    started = datetime.utcnow() - timedelta(minutes=started_offset_min)
    with session_scope() as session:
        row = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status=status,
            verdict=verdict,
            input_context_json="[]",
            output_format="markdown",
            started_by="test",
            started_at=started,
            completed_at=started + timedelta(seconds=2) if status == "completed" else None,
        )
        session.add(row)
        session.flush()
        return row.id


def test_history_invalid_filename_rejects(client):
    # Sin .agent.md → 400
    r = client.get("/api/agents/vscode/DevPacifico/history")
    assert r.status_code == 400
    # Path traversal → 400
    r2 = client.get("/api/agents/vscode/..%2Fevil.agent.md/history")
    assert r2.status_code == 400


def test_history_developer_filename_groups_by_ticket(client):
    ticket_a = _seed_ticket(ado_id=12001, title="ticket A")
    ticket_b = _seed_ticket(ado_id=12002, title="ticket B")

    # Dos ejecuciones developer en ticket A, una en ticket B
    _seed_execution(ticket_a, "developer", started_offset_min=10)
    _seed_execution(ticket_a, "developer", started_offset_min=5)
    _seed_execution(ticket_b, "developer", started_offset_min=20)
    # Una ejecución qa que NO debe aparecer
    _seed_execution(ticket_a, "qa", started_offset_min=2)

    r = client.get("/api/agents/vscode/DevPacifico.agent.md/history")
    assert r.status_code == 200
    data = r.get_json()
    assert data["agent_filename"] == "DevPacifico.agent.md"
    assert data["inferred_agent_type"] == "developer"

    by_ticket = {t["ticket_id"]: t for t in data["tickets"]}
    assert ticket_a in by_ticket
    assert ticket_b in by_ticket
    assert by_ticket[ticket_a]["executions_count"] == 2
    assert by_ticket[ticket_b]["executions_count"] == 1
    assert data["total_executions"] == 3
    assert by_ticket[ticket_a]["ado_id"] == 12001
    assert by_ticket[ticket_a]["last_execution_status"] == "completed"


def test_history_custom_filename_returns_empty_with_note(client):
    # No sembramos nada → custom devuelve estructura vacía con nota.
    r = client.get("/api/agents/vscode/SomeWeirdAgent.agent.md/history")
    assert r.status_code == 200
    data = r.get_json()
    assert data["inferred_agent_type"] == "custom"
    assert data["tickets"] == []
    assert data["total_executions"] == 0
    assert data["mapping_note"]  # texto explicativo no vacío


def test_history_qa_filename_filters_correctly(client):
    ticket = _seed_ticket(ado_id=13001, title="qa ticket")
    _seed_execution(ticket, "qa", started_offset_min=5)
    _seed_execution(ticket, "developer", started_offset_min=2)  # no debe aparecer

    r = client.get("/api/agents/vscode/QATester.agent.md/history")
    assert r.status_code == 200
    data = r.get_json()
    assert data["inferred_agent_type"] == "qa"
    by_ticket = {t["ticket_id"]: t for t in data["tickets"]}
    assert ticket in by_ticket
    assert by_ticket[ticket]["executions_count"] == 1
    assert data["total_executions"] == 1


def test_history_no_executions_returns_empty_list(client):
    # Filename válido (developer), sin ejecuciones sembradas → tickets vacío.
    r = client.get("/api/agents/vscode/DevAnother.agent.md/history?limit=10")
    assert r.status_code == 200
    data = r.get_json()
    assert data["inferred_agent_type"] == "developer"
    assert data["total_executions"] == 0
    assert data["tickets"] == []
    assert data["mapping_note"]


def test_history_mapping_developer_keyword_es(client):
    # "desarrollador" en el filename también mapea a developer (alineación con
    # frontend/EmployeeCard.inferType).
    ticket = _seed_ticket(ado_id=14001, title="es-keyword ticket")
    _seed_execution(ticket, "developer", started_offset_min=1)

    r = client.get("/api/agents/vscode/Desarrollador.agent.md/history")
    assert r.status_code == 200
    data = r.get_json()
    assert data["inferred_agent_type"] == "developer"
    assert any(t["ticket_id"] == ticket for t in data["tickets"])
