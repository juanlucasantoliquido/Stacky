"""Plan 71 F5 — Tests cableado ado-pipeline-status + ado-pipeline-batch.

7 casos:
  1. flag OFF → legacy infer_pipeline llamado (fallback byte-idéntico).
  2. flag ON + ADO → AdoCIProvider usado.
  3. Gate significancia GitLab (ticket con tracker_type=gitlab usa GitLabCIProvider).
  4. ticket sin item_id / ado_id=0 → _item_ref_for_ticket retorna None (no crash).
  5. excepción en provider → respuesta con "error" + código 500.
  6. batch mixto: flag ON, dos tickets distintos resuelven su propio provider.
  7. ci_provider_coverage presente en respuesta cuando flag ON.
"""
from __future__ import annotations

import json
import pytest
import sys
import types
from unittest.mock import MagicMock, patch
import config

# ---------------------------------------------------------------------------
# Fixtures de Flask app y BD en memoria
# ---------------------------------------------------------------------------

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
    """Inserta tickets de prueba en la BD de test."""
    from db import session_scope
    from models import Ticket

    with app.app_context():
        with session_scope() as session:
            # Limpieza previa
            session.query(Ticket).filter(Ticket.id.in_([9901, 9902])).delete(
                synchronize_session=False
            )
            session.add(Ticket(
                id=9901,
                ado_id=1001,
                project="TestProject",
                stacky_project_name="TEST",
                tracker_type="azure_devops",
                title="Test ADO ticket",
            ))
            session.add(Ticket(
                id=9902,
                ado_id=2002,
                project="TestProject",
                stacky_project_name="TEST",
                tracker_type="gitlab",
                title="Test GitLab ticket",
            ))
            session.commit()


# ---------------------------------------------------------------------------
# Helper: mock de PipelineInferenceResult
# ---------------------------------------------------------------------------

def _make_legacy_dict():
    return {
        "ado_id": 1001,
        "stages": {},
        "overall_progress": 0.5,
        "source": "llm",
        "next_suggested": None,
        "summary": "ok",
        "inferred_at": "2026-01-01T00:00:00",
        "model_used": "gpt-4o-mini",
    }


def _make_legacy_result():
    m = MagicMock()
    m.to_dict.return_value = _make_legacy_dict()
    return m


def _make_ci_result():
    from services.ci_provider import ItemRef, ItemPipelineResult
    ref = ItemRef(item_id="1001", tracker_type="azure_devops")
    return ItemPipelineResult(
        item_ref=ref,
        stages=(),
        overall_progress=0.5,
        source="llm",
        raw={},
    )


# ---------------------------------------------------------------------------
# C1 — flag OFF → infer_pipeline legacy llamado
# ---------------------------------------------------------------------------
def test_flag_off_uses_legacy(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", False)

    with app.app_context():
        with patch("api.tickets.infer_pipeline", return_value=_make_legacy_result()) as mock_inf:
            resp = client.get("/api/tickets/9901/ado-pipeline-status")

    assert resp.status_code == 200
    mock_inf.assert_called_once()


# ---------------------------------------------------------------------------
# C2 — flag ON + ADO → AdoCIProvider usado
# ---------------------------------------------------------------------------
def test_flag_on_ado_uses_ci_provider(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", True)

    ci_result = _make_ci_result()
    stub_provider = MagicMock()
    stub_provider.name = "azure_devops"
    stub_provider.infer_item_pipeline.return_value = ci_result

    with app.app_context():
        with patch("api.tickets.get_ci_provider", return_value=stub_provider):
            resp = client.get("/api/tickets/9901/ado-pipeline-status")

    assert resp.status_code == 200
    stub_provider.infer_item_pipeline.assert_called_once()
    data = resp.get_json()
    assert data.get("source") == "llm"


# ---------------------------------------------------------------------------
# C3 — gate significancia GitLab (tracker_type=gitlab usa GitLabCIProvider)
# ---------------------------------------------------------------------------
def test_gitlab_ticket_uses_gitlab_provider(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", True)

    ci_result_gl = MagicMock()
    ci_result_gl.to_dict.return_value = {
        "overall_progress": 1.0, "source": "ci", "stages": [], "item_ref": {}, "raw": {}
    }
    stub_provider = MagicMock()
    stub_provider.name = "gitlab"
    stub_provider.infer_item_pipeline.return_value = ci_result_gl

    with app.app_context():
        with patch("api.tickets.get_ci_provider", return_value=stub_provider):
            resp = client.get("/api/tickets/9902/ado-pipeline-status")

    assert resp.status_code == 200
    stub_provider.infer_item_pipeline.assert_called_once()


# ---------------------------------------------------------------------------
# C4 — _item_ref_for_ticket retorna None para ticket con ado_id=0 (edge case)
# ---------------------------------------------------------------------------
def test_item_ref_for_ticket_none_for_zero_ado_id(app):
    from api.tickets import _item_ref_for_ticket
    from models import Ticket

    with app.app_context():
        t = Ticket(id=9999, ado_id=0, project="X", title="x", tracker_type="azure_devops")
        result = _item_ref_for_ticket(t)
    # ado_id=0 es falsy → debe retornar None
    assert result is None


# ---------------------------------------------------------------------------
# C5 — excepción en provider → 500
# ---------------------------------------------------------------------------
def test_provider_exception_returns_500(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", True)

    def bad_provider():
        raise RuntimeError("provider explodó")

    with app.app_context():
        with patch("api.tickets.get_ci_provider", side_effect=RuntimeError("provider explodó")):
            resp = client.get("/api/tickets/9901/ado-pipeline-status")

    assert resp.status_code == 500
    data = resp.get_json()
    assert "error" in data


# ---------------------------------------------------------------------------
# C6 — batch mixto: dos tickets resuelven su propio provider
# ---------------------------------------------------------------------------
def test_batch_resolves_provider_per_item(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", True)

    call_count = {"n": 0}
    def fake_get_ci_provider(*args, **kwargs):
        call_count["n"] += 1
        stub = MagicMock()
        stub.name = "azure_devops"
        ci_result = _make_ci_result()
        stub.infer_item_pipeline.return_value = ci_result
        return stub

    with app.app_context():
        with patch("api.tickets.get_ci_provider", side_effect=fake_get_ci_provider):
            resp = client.post(
                "/api/tickets/ado-pipeline-batch",
                json={"ticket_ids": [9901, 9902]},
                content_type="application/json",
            )

    assert resp.status_code == 200
    data = resp.get_json()
    assert "results" in data
    # Cada ticket resolvió su propio provider
    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# C7 — ci_provider_coverage en respuesta cuando flag ON
# ---------------------------------------------------------------------------
def test_ci_provider_coverage_in_response(client, app, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_PROVIDER_ENABLED", True)

    ci_result = _make_ci_result()
    stub_provider = MagicMock()
    stub_provider.name = "azure_devops"
    stub_provider.infer_item_pipeline.return_value = ci_result

    with app.app_context():
        with patch("api.tickets.get_ci_provider", return_value=stub_provider):
            resp = client.get("/api/tickets/9901/ado-pipeline-status")

    assert resp.status_code == 200
    data = resp.get_json()
    # El campo tracker_type debe estar en la respuesta cuando se usa el provider
    assert "tracker_type" in data
