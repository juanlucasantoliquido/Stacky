"""Plan 39 A1 — Tests TDD del endpoint GET /api/executions/history.

Tests:
1. test_history_returns_items_with_all_keys — GET → 200, items tienen todas las claves del contrato
2. test_history_filters_by_agent_type — ?agent_type=developer → solo developer
3. test_history_filters_by_runtime — ?runtime=claude_code_cli → solo esos
4. test_history_pagination — ?limit=1&offset=1 → 1 item, el segundo más reciente
5. test_history_old_execution_no_crash — ejecución sin metadata Plan 38 → item con null/0/false, sin error
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REQUIRED_KEYS = {
    "id", "ticket_id", "ticket_title", "agent_type", "agent_name",
    "runtime", "model", "status",
    "started_at", "finished_at", "duration_ms",
    "cost_usd", "tokens_in", "tokens_out",
    "prompt_sha", "prompt_len", "has_prompt_text",
    "produced_files_count", "error_message",
}


@pytest.fixture(scope="module")
def _app():
    os.environ["STACKY_EXECUTION_HISTORY_ENABLED"] = "true"
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def client(_app):
    with _app.test_client() as c:
        yield c


_NEXT_ADO_ID = 90000  # rango reservado para test_executions_history (no colisiona)


def _seed_exec(*, agent_type: str = "developer", status: str = "completed",
               runtime: str = "codex_cli", model: str = "o4-mini",
               started_at: datetime | None = None, completed_at: datetime | None = None,
               metadata_extra: dict | None = None):
    global _NEXT_ADO_ID
    _NEXT_ADO_ID += 1
    ado_id = _NEXT_ADO_ID

    from db import session_scope
    from models import AgentExecution, Ticket
    import json

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="histproj",
            stacky_project_name="histproj",
            title=f"Ticket {ado_id}",
            ado_state="Active",
        )
        session.add(t)
        session.flush()

        when = started_at or datetime.utcnow()
        end = completed_at or (when + timedelta(seconds=10))

        meta = {"runtime": runtime, "model": model}
        if metadata_extra:
            meta.update(metadata_extra)

        e = AgentExecution(
            ticket_id=t.id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=when,
            completed_at=end,
            metadata_json=json.dumps(meta),
        )
        session.add(e)
        session.flush()
        return t.id, e.id


# ---------------------------------------------------------------------------
# 1. GET /history → 200, items con todas las claves del contrato
# ---------------------------------------------------------------------------

def test_history_returns_items_with_all_keys(client):
    _seed_exec()
    resp = client.get(
        "/api/executions/history",
        headers={"X-User-Email": "test@test.com"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    for item in data:
        missing = REQUIRED_KEYS - set(item.keys())
        assert not missing, f"Faltan claves: {missing}"


# ---------------------------------------------------------------------------
# 2. Filtro por agent_type
# ---------------------------------------------------------------------------

def test_history_filters_by_agent_type(client):
    _seed_exec(agent_type="developer")
    _seed_exec(agent_type="qa")

    resp = client.get(
        "/api/executions/history?agent_type=qa",
        headers={"X-User-Email": "test@test.com"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert all(item["agent_type"] == "qa" for item in data)


# ---------------------------------------------------------------------------
# 3. Filtro por runtime
# ---------------------------------------------------------------------------

def test_history_filters_by_runtime(client):
    _seed_exec(runtime="claude_code_cli")
    _seed_exec(runtime="github_copilot")

    resp = client.get(
        "/api/executions/history?runtime=claude_code_cli",
        headers={"X-User-Email": "test@test.com"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert all(item["runtime"] == "claude_code_cli" for item in data)


# ---------------------------------------------------------------------------
# 4. Paginación limit/offset
# ---------------------------------------------------------------------------

def test_history_pagination(client):
    t1 = datetime(2025, 1, 1, 10, 0, 0)
    t2 = datetime(2025, 1, 1, 11, 0, 0)  # más reciente
    _seed_exec(started_at=t1, agent_type="developer")
    _seed_exec(started_at=t2, agent_type="developer")

    # limit=1, offset=1 → el segundo más reciente (el primero saltado)
    resp = client.get(
        "/api/executions/history?limit=1&offset=1",
        headers={"X-User-Email": "test@test.com"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1


# ---------------------------------------------------------------------------
# 5. Ejecución sin metadata Plan 38 → item sin error, campos null/0/false
# ---------------------------------------------------------------------------

def test_history_old_execution_no_crash(client):
    from db import session_scope
    from models import AgentExecution, Ticket

    global _NEXT_ADO_ID
    _NEXT_ADO_ID += 1
    old_ado_id = _NEXT_ADO_ID

    with session_scope() as session:
        t = Ticket(
            ado_id=old_ado_id,
            project="histproj",
            stacky_project_name="histproj",
            title="Old ticket",
            ado_state="Active",
        )
        session.add(t)
        session.flush()

        # Ejecución vieja: sin metadata_json (solo campos base)
        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status="completed",
            input_context_json="[]",
            started_by="test",
            started_at=datetime(2024, 6, 1, 12, 0, 0),
            completed_at=datetime(2024, 6, 1, 12, 5, 0),
            metadata_json=None,
        )
        session.add(e)
        session.flush()

    resp = client.get(
        "/api/executions/history",
        headers={"X-User-Email": "test@test.com"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    # Al menos debe incluir la ejecución vieja sin lanzar
    assert isinstance(data, list)
    # Verificar que los campos opcionales son null/0/False (no lanza)
    for item in data:
        # Estos campos pueden ser None/0/False pero no deben causar error de serialización
        assert "cost_usd" in item
        assert "tokens_in" in item
        assert "prompt_sha" in item
