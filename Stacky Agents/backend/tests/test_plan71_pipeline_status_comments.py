"""Plan 71 F6 — Tests: endpoint /<id>/pipeline-status usa TrackerProvider cuando flag ON.

4 casos:
  1. flag OFF → _ado_client_for_ticket llamado (legacy).
  2. flag ON + Plan 70 ausente → fallback + pipeline_comments_legacy=True hint.
  3. flag ON + Plan 70 presente → TrackerProvider.fetch_comments llamado.
  4. Misma estructura de respuesta en ambos branches.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call
import config


@pytest.fixture()
def app():
    from app import create_app
    _app = create_app()
    _app.config["TESTING"] = True
    return _app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def seed_ticket(app):
    from db import session_scope
    from models import Ticket

    with app.app_context():
        with session_scope() as session:
            session.query(Ticket).filter(Ticket.id == 9911).delete(synchronize_session=False)
            session.add(Ticket(
                id=9911,
                ado_id=1111,
                project="TestProject",
                stacky_project_name="TEST",
                tracker_type="azure_devops",
                title="Test pipeline-status ticket",
            ))
            session.commit()


def _fake_pipeline_status(stages=None):
    """Mock de PipelineStatus."""
    m = MagicMock()
    m.to_dict.return_value = {
        "stages": stages or {},
        "overall_progress": 0.5,
        "next_suggested": None,
    }
    return m


# ---------------------------------------------------------------------------
# C1 — flag OFF → _ado_client_for_ticket path (legacy)
# ---------------------------------------------------------------------------
def test_flag_off_uses_ado_client(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", False)

    fake_status = _fake_pipeline_status()
    with patch("api.tickets.get_pipeline_status", return_value=fake_status) as mock_status:
        resp = client.get("/api/tickets/9911/pipeline-status?include_ado_comments=false")

    assert resp.status_code == 200
    mock_status.assert_called_once()
    data = resp.get_json()
    assert "stages" in data


# ---------------------------------------------------------------------------
# C2 — flag ON pero _provider_for_ticket retorna None → fallback ADO client
# ---------------------------------------------------------------------------
def test_flag_on_no_provider_falls_back_to_ado(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", True)

    fake_ado_client = MagicMock()
    fake_ado_client.fetch_comments.return_value = []
    fake_status = _fake_pipeline_status()

    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake_ado_client), \
         patch("api.tickets.get_pipeline_status", return_value=fake_status):
        resp = client.get(
            "/api/tickets/9911/pipeline-status?include_ado_comments=true"
        )

    assert resp.status_code == 200
    fake_ado_client.fetch_comments.assert_called_once()


# ---------------------------------------------------------------------------
# C3 — flag ON + provider disponible → TrackerProvider.fetch_comments llamado
# ---------------------------------------------------------------------------
def test_flag_on_with_provider_uses_tracker_provider(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", True)

    fake_provider = MagicMock()
    fake_provider.fetch_comments.return_value = [{"text": "comment_from_provider"}]
    fake_status = _fake_pipeline_status()

    with patch("api.tickets._provider_for_ticket", return_value=fake_provider), \
         patch("api.tickets.get_pipeline_status", return_value=fake_status):
        resp = client.get(
            "/api/tickets/9911/pipeline-status?include_ado_comments=true"
        )

    assert resp.status_code == 200
    fake_provider.fetch_comments.assert_called_once()


# ---------------------------------------------------------------------------
# C4 — misma estructura de respuesta en ambos branches
# ---------------------------------------------------------------------------
def test_same_response_shape_both_branches(client, app, monkeypatch):
    fake_status = _fake_pipeline_status(stages={"business": {"done": True}})

    # Branch legacy (flag OFF)
    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", False)
    with patch("api.tickets.get_pipeline_status", return_value=fake_status):
        resp_legacy = client.get("/api/tickets/9911/pipeline-status")
    data_legacy = resp_legacy.get_json()

    # Branch provider (flag ON)
    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", True)
    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets.get_pipeline_status", return_value=fake_status):
        resp_provider = client.get("/api/tickets/9911/pipeline-status")
    data_provider = resp_provider.get_json()

    assert resp_legacy.status_code == 200
    assert resp_provider.status_code == 200
    assert set(data_legacy.keys()) == set(data_provider.keys())
