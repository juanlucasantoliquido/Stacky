"""Plan 71 F7 — Tests observabilidad + centinela + ratchet.

5 casos:
  1. Gate significancia GitLab: STACKY_PIPELINE_PROVIDER_ENABLED + gitlab ticket → GitLabCIProvider.
  2. flag OFF → legacy infer_pipeline llamado (no CIProvider).
  3. tracker_type + source presentes en respuesta cuando flag ON.
  4. ci_provider_coverage presente en respuesta cuando flag ON.
  5. harness_health expone ci_provider_coverage (Plan 71 F7).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
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
def seed_tickets(app):
    from db import session_scope
    from models import Ticket

    with app.app_context():
        with session_scope() as session:
            session.query(Ticket).filter(Ticket.id.in_([9981, 9982])).delete(
                synchronize_session=False
            )
            session.add(Ticket(
                id=9981,
                ado_id=8001,
                project="TestProject",
                stacky_project_name="TEST",
                tracker_type="azure_devops",
                title="ADO ticket F7",
            ))
            session.add(Ticket(
                id=9982,
                ado_id=8002,
                project="TestProject",
                stacky_project_name="TEST",
                tracker_type="gitlab",
                title="GitLab ticket F7",
            ))
            session.commit()


def _make_ci_result(tracker_type="azure_devops"):
    from services.ci_provider import ItemRef, ItemPipelineResult
    ref = ItemRef(item_id="8001", tracker_type=tracker_type)
    return ItemPipelineResult(
        item_ref=ref,
        stages=(),
        overall_progress=0.5,
        source="ci" if tracker_type == "gitlab" else "llm",
        raw={},
    )


def _make_legacy():
    m = MagicMock()
    m.to_dict.return_value = {
        "ado_id": 8001, "stages": {}, "overall_progress": 0.5,
        "source": "llm", "next_suggested": None,
        "summary": "ok", "inferred_at": "2026-01-01T00:00:00", "model_used": "gpt-4o-mini",
    }
    return m


# ---------------------------------------------------------------------------
# C1 — Gate significancia GitLab: GitLabCIProvider llamado para ticket gitlab
# ---------------------------------------------------------------------------
def test_gitlab_ticket_calls_gitlab_ci_provider(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", True)

    gl_result = _make_ci_result("gitlab")
    stub_gl = MagicMock()
    stub_gl.name = "gitlab"
    stub_gl.infer_item_pipeline.return_value = gl_result

    with patch("api.tickets.get_ci_provider", return_value=stub_gl):
        resp = client.get("/api/tickets/9982/ado-pipeline-status")

    assert resp.status_code == 200
    stub_gl.infer_item_pipeline.assert_called_once()


# ---------------------------------------------------------------------------
# C2 — flag OFF → infer_pipeline legacy llamado (nunca CIProvider)
# ---------------------------------------------------------------------------
def test_flag_off_no_ci_provider(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", False)

    legacy = _make_legacy()
    with patch("api.tickets.infer_pipeline", return_value=legacy) as mock_legacy, \
         patch("api.tickets.get_ci_provider") as mock_ci:
        resp = client.get("/api/tickets/9981/ado-pipeline-status")

    assert resp.status_code == 200
    mock_legacy.assert_called_once()
    mock_ci.assert_not_called()


# ---------------------------------------------------------------------------
# C3 — tracker_type + source presentes en respuesta con flag ON
# ---------------------------------------------------------------------------
def test_tracker_type_and_source_in_response(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", True)

    ado_result = _make_ci_result("azure_devops")
    stub = MagicMock()
    stub.name = "azure_devops"
    stub.infer_item_pipeline.return_value = ado_result

    with patch("api.tickets.get_ci_provider", return_value=stub):
        resp = client.get("/api/tickets/9981/ado-pipeline-status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "tracker_type" in data, f"Falta 'tracker_type' en {list(data.keys())}"
    assert "source" in data, f"Falta 'source' en {list(data.keys())}"


# ---------------------------------------------------------------------------
# C4 — ci_provider_coverage presente en respuesta con flag ON
# ---------------------------------------------------------------------------
def test_ci_provider_coverage_in_response(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", True)

    ado_result = _make_ci_result("azure_devops")
    stub = MagicMock()
    stub.name = "azure_devops"
    stub.infer_item_pipeline.return_value = ado_result

    with patch("api.tickets.get_ci_provider", return_value=stub):
        resp = client.get("/api/tickets/9981/ado-pipeline-status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "ci_provider_coverage" in data, (
        f"Falta 'ci_provider_coverage' en {list(data.keys())}"
    )


# ---------------------------------------------------------------------------
# C5 — harness_health expone ci_provider_coverage
# ---------------------------------------------------------------------------
def test_harness_health_exposes_ci_provider_coverage(client, app, monkeypatch):
    """GET /api/metrics/harness-health incluye ci_provider_coverage."""
    # Inyectar cobertura efímera
    import api.tickets as tix_mod
    tix_mod._ci_provider_coverage["azure_devops"] = 5

    resp = client.get("/api/metrics/harness-health")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "ci_provider_coverage" in data, (
        f"Falta 'ci_provider_coverage' en harness-health. Keys: {list(data.keys())}"
    )
    # cleanup
    tix_mod._ci_provider_coverage.clear()
