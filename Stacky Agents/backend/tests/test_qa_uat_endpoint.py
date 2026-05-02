"""
Unit tests for the QA UAT Flask endpoint (api/qa_uat.py).

Tests cover:
- POST /api/qa-uat/run returns 202 + execution_id
- POST /api/qa-uat/run missing ticket_id → 400
- POST /api/qa-uat/run invalid mode → 400
- POST /api/qa-uat/run ticket not found → 404
- POST /api/qa-uat/run defaults mode to dry-run
- GET /api/qa-uat/run/<id> returns execution data
- GET /api/qa-uat/run/<id> with completed execution includes pipeline_result
- GET /api/qa-uat/run/<id> for wrong agent_type → 404

Background thread is mocked — no actual pipeline execution.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(scope="module")
def app():
    from app import create_app
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture
def ticket_in_db(app):
    """Create a Ticket row with ado_id=70 in the in-memory DB."""
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        existing = session.query(Ticket).filter(Ticket.ado_id == 70).first()
        if existing:
            return existing.id
        t = Ticket(ado_id=70, project="RSPacifico",
                   title="RF-003 Validación de filtros", ado_state="Active")
        session.add(t)
        session.flush()
        return t.id


# ── POST /api/qa-uat/run ──────────────────────────────────────────────────────

def test_run_returns_202_with_execution_id(client, ticket_in_db):
    """Happy path: valid request creates execution and returns 202."""
    with patch("threading.Thread") as mock_thread_cls:
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        r = client.post(
            "/api/qa-uat/run",
            json={"ticket_id": 70, "mode": "dry-run"},
            content_type="application/json",
        )

    assert r.status_code == 202
    body = r.get_json()
    assert "execution_id" in body
    assert isinstance(body["execution_id"], int)
    assert body["ticket_id"] == 70
    assert body["mode"] == "dry-run"
    assert "stream_url" in body
    mock_thread.start.assert_called_once()


def test_run_defaults_to_dry_run(client, ticket_in_db):
    """If mode is omitted, default is dry-run."""
    with patch("threading.Thread") as mock_thread_cls:
        mock_thread_cls.return_value = MagicMock()
        r = client.post(
            "/api/qa-uat/run",
            json={"ticket_id": 70},
            content_type="application/json",
        )

    assert r.status_code == 202
    assert r.get_json()["mode"] == "dry-run"


def test_run_missing_ticket_id_returns_400(client):
    """ticket_id is required."""
    r = client.post(
        "/api/qa-uat/run",
        json={"mode": "dry-run"},
        content_type="application/json",
    )
    assert r.status_code == 400


def test_run_invalid_ticket_id_returns_400(client):
    """ticket_id must be a positive integer."""
    r = client.post(
        "/api/qa-uat/run",
        json={"ticket_id": -5, "mode": "dry-run"},
        content_type="application/json",
    )
    assert r.status_code == 400


def test_run_invalid_mode_returns_400(client, ticket_in_db):
    """mode must be 'dry-run' or 'publish'."""
    r = client.post(
        "/api/qa-uat/run",
        json={"ticket_id": 70, "mode": "destroy"},
        content_type="application/json",
    )
    assert r.status_code == 400


def test_run_ticket_not_found_returns_404(client):
    """Ticket not in Stacky DB → 404."""
    r = client.post(
        "/api/qa-uat/run",
        json={"ticket_id": 99999, "mode": "dry-run"},
        content_type="application/json",
    )
    assert r.status_code == 404


def test_run_invalid_timeout_ms_returns_400(client, ticket_in_db):
    """timeout_ms out of range returns 400."""
    r = client.post(
        "/api/qa-uat/run",
        json={"ticket_id": 70, "timeout_ms": 999},
        content_type="application/json",
    )
    assert r.status_code == 400


# ── GET /api/qa-uat/run/<execution_id> ───────────────────────────────────────

def test_get_run_returns_execution_data(client, ticket_in_db):
    """GET returns execution dict with status and agent_type."""
    with patch("threading.Thread") as mock_thread_cls:
        mock_thread_cls.return_value = MagicMock()
        r = client.post(
            "/api/qa-uat/run",
            json={"ticket_id": 70, "mode": "dry-run"},
        )
    exec_id = r.get_json()["execution_id"]

    r2 = client.get(f"/api/qa-uat/run/{exec_id}")
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["id"] == exec_id
    assert body["agent_type"] == "qa-uat"
    assert body["status"] == "running"


def test_get_run_not_found_returns_404(client):
    """Unknown execution_id → 404."""
    r = client.get("/api/qa-uat/run/99999")
    assert r.status_code == 404


def test_get_run_completed_includes_pipeline_result(client, ticket_in_db):
    """When execution has JSON output, pipeline_result is parsed and returned."""
    from db import session_scope
    from models import AgentExecution

    with patch("threading.Thread") as mock_thread_cls:
        mock_thread_cls.return_value = MagicMock()
        r = client.post(
            "/api/qa-uat/run",
            json={"ticket_id": 70, "mode": "dry-run"},
        )
    exec_id = r.get_json()["execution_id"]

    pipeline_result = {
        "ok": True, "ticket_id": 70, "verdict": "PASS",
        "stages": {}, "elapsed_s": 5.0,
    }

    # Simulate pipeline completing
    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        row.status = "completed"
        row.output = json.dumps(pipeline_result)

    r2 = client.get(f"/api/qa-uat/run/{exec_id}")
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["status"] == "completed"
    assert body["pipeline_result"]["verdict"] == "PASS"
    assert body["pipeline_result"]["ok"] is True
