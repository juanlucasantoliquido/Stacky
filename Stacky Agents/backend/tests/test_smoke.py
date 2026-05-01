import os
import sys
import time
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


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}


def test_list_agents(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    types = {a["type"] for a in r.get_json()}
    assert {"business", "functional", "technical", "developer", "qa"} <= types


def test_list_packs(client):
    r = client.get("/api/packs")
    assert r.status_code == 200
    ids = {p["id"] for p in r.get_json()}
    assert {"desarrollo", "qa-express", "discovery", "hotfix", "refactor"} <= ids


def test_run_agent_creates_execution(client):
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=999, project="RSPacifico", title="dummy", ado_state="To Do")
        session.add(t)
        session.flush()
        ticket_id = t.id

    payload = {
        "agent_type": "functional",
        "ticket_id": ticket_id,
        "context_blocks": [
            {"id": "b1", "kind": "editable", "title": "Notas", "content": "Hola"}
        ],
    }
    r = client.post("/api/agents/run", json=payload)
    assert r.status_code == 202
    data = r.get_json()
    execution_id = data["execution_id"]

    # esperar la ejecución mock
    deadline = time.time() + 5
    while time.time() < deadline:
        r2 = client.get(f"/api/executions/{execution_id}")
        if r2.get_json()["status"] in ("completed", "error", "cancelled"):
            break
        time.sleep(0.2)
    assert r2.get_json()["status"] == "completed"
    assert "Mock" in r2.get_json()["output"]
