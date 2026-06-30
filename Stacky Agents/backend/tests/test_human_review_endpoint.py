"""Plan 47 F1 — Endpoint POST /api/executions/{id}/human-review."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_ADO_SEQ = iter(range(810000, 819999))


@pytest.fixture
def client():
    from app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def _seed(status="needs_review"):
    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as session:
        tk = Ticket(ado_id=next(_ADO_SEQ), project="HRP", stacky_project_name="HRP",
                    title="t", ado_state="Active", work_item_type="Task")
        session.add(tk)
        session.flush()
        ex = AgentExecution(
            ticket_id=tk.id, agent_type="business", status=status,
            input_context_json="[]", started_by="op", started_at=datetime.utcnow(),
        )
        session.add(ex)
        session.flush()
        return ex.id


def _reload(exec_id):
    from db import session_scope
    from models import AgentExecution
    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        return row.verdict, row.metadata_dict


# Por default el flag de memoria está OFF → capture devuelve None; no hace falta mockear.

def test_human_review_on_needs_review_persists(client):
    eid = _seed("needs_review")
    r = client.post(f"/api/executions/{eid}/human-review",
                    json={"verdict": "rejected", "note": "falta proceso batch"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["human_review_persisted"] is True
    assert d["operator_note_captured"] is False
    verdict, meta = _reload(eid)
    assert meta["human_review"]["verdict"] == "rejected"
    assert meta["human_review"]["note"] == "falta proceso batch"
    assert verdict == "rejected"


def test_human_review_on_completed_persists(client):
    eid = _seed("completed")
    r = client.post(f"/api/executions/{eid}/human-review", json={"verdict": "approved"})
    assert r.status_code == 200
    verdict, meta = _reload(eid)
    assert verdict == "approved"
    assert meta["human_review"]["note"] is None


def test_approved_with_notes_maps_column_to_approved(client):
    eid = _seed("completed")
    r = client.post(f"/api/executions/{eid}/human-review",
                    json={"verdict": "approved_with_notes", "note": "ok pero revisar X"})
    assert r.status_code == 200
    verdict, meta = _reload(eid)
    assert verdict == "approved"
    assert meta["human_review"]["verdict"] == "approved_with_notes"


def test_human_review_running_returns_409(client):
    eid = _seed("running")
    r = client.post(f"/api/executions/{eid}/human-review", json={"verdict": "approved"})
    assert r.status_code == 409


def test_human_review_invalid_verdict_400(client):
    eid = _seed("completed")
    r = client.post(f"/api/executions/{eid}/human-review", json={"verdict": "maybe"})
    assert r.status_code == 400


def test_human_review_overwrites(client):
    eid = _seed("needs_review")
    client.post(f"/api/executions/{eid}/human-review", json={"verdict": "approved"})
    client.post(f"/api/executions/{eid}/human-review",
                json={"verdict": "rejected", "note": "cambié de opinión"})
    verdict, meta = _reload(eid)
    assert verdict == "rejected"
    assert meta["human_review"]["verdict"] == "rejected"


def test_capture_hook_invoked_but_offsafe(client):
    """Con capture mockeado devolviendo un id, la respuesta lo refleja."""
    eid = _seed("needs_review")
    with patch("services.post_run_memory.capture_operator_note", return_value="mem-123"):
        r = client.post(f"/api/executions/{eid}/human-review",
                        json={"verdict": "rejected", "note": "x"})
    d = r.get_json()
    assert d["stacky_memory_id"] == "mem-123"
    assert d["operator_note_captured"] is True


def test_response_reflects_persistence_and_capture_independently(client):
    """Si la captura falla, el veredicto igual se persiste (200, persisted=True)."""
    eid = _seed("needs_review")
    with patch("services.post_run_memory.capture_operator_note",
               side_effect=RuntimeError("boom")):
        r = client.post(f"/api/executions/{eid}/human-review",
                        json={"verdict": "rejected", "note": "x"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["human_review_persisted"] is True
    assert d["operator_note_captured"] is False
    verdict, _ = _reload(eid)
    assert verdict == "rejected"
