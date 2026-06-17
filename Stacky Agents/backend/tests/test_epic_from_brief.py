"""B0 — Tests para POST /api/tickets/epics/from-brief."""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture()
def client():
    from app import create_app
    app = create_app()
    with app.test_client() as c:
        yield c


def _body(**kwargs):
    base = {
        "title": "Mi Épica",
        "description_html": "<p>Descripción</p>",
        "brief": "Brief del negocio",
        "project_name": "TestProject",
        "confirm": True,
    }
    base.update(kwargs)
    return json.dumps(base).encode()


def test_requires_confirm(client):
    """Sin confirm:true → 400 confirmation_required."""
    body = {
        "title": "X",
        "description_html": "<p>Y</p>",
        "brief": "Z",
        "project_name": "P",
        "confirm": False,
    }
    resp = client.post(
        "/api/tickets/epics/from-brief",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get("error") == "confirmation_required"


def test_requires_title(client):
    """Sin title → 400."""
    body = {
        "title": "",
        "description_html": "<p>Y</p>",
        "brief": "Z",
        "project_name": "P",
        "confirm": True,
    }
    resp = client.post(
        "/api/tickets/epics/from-brief",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get("error") in ("missing_title", "validation_error")


def test_requires_description(client):
    """Sin description_html → 400."""
    body = {
        "title": "Mi Épica",
        "description_html": "",
        "brief": "Z",
        "project_name": "P",
        "confirm": True,
    }
    resp = client.post(
        "/api/tickets/epics/from-brief",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get("error") in ("missing_description", "validation_error")


def test_happy_path_with_stub_ado(client, tmp_path, monkeypatch):
    """Happy path: ADO stub → 201 con ado_id, work_item_type, title, url."""
    # Stub del cliente ADO
    mock_client = MagicMock()
    mock_client.create_work_item.return_value = {
        "id": 9999,
        "fields": {"System.Title": "Mi Épica"},
        "_links": {"html": {"href": "https://dev.azure.com/org/proj/_workitems/edit/9999"}},
    }
    mock_client.work_item_url.return_value = "https://dev.azure.com/org/proj/_workitems/edit/9999"

    monkeypatch.setattr(
        "api.tickets._ado_client_for_ticket",
        lambda **kwargs: mock_client,
    )

    # Stub de la escritura en disco para no necesitar directorio real
    import api.tickets as t_mod
    monkeypatch.setattr(t_mod, "_epic_brief_save", lambda ado_id, brief, project_name: None)

    resp = client.post(
        "/api/tickets/epics/from-brief",
        data=_body(),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data.get("ado_id") == 9999
    assert data.get("work_item_type") == "Epic"
    assert data.get("title") == "Mi Épica"
    assert "url" in data


def test_ado_failure_no_persist(client, monkeypatch):
    """Si ADO falla → 502 y no se persiste ticket local."""
    from services.ado_client import AdoApiError

    mock_client = MagicMock()
    mock_client.create_work_item.side_effect = AdoApiError("ADO timeout", status_code=503)

    monkeypatch.setattr(
        "api.tickets._ado_client_for_ticket",
        lambda **kwargs: mock_client,
    )

    with patch("api.tickets.session_scope") as mock_ss:
        resp = client.post(
            "/api/tickets/epics/from-brief",
            data=_body(),
            content_type="application/json",
        )
        # La sesión NO debe haber sido comprometida (add no llamado con ticket)
        assert resp.status_code in (502, 503)
        # Verificar que no se llamó session.add con un ticket
        for call in mock_ss.return_value.__enter__.return_value.add.call_args_list:
            from models import Ticket
            if call.args and isinstance(call.args[0], Ticket):
                pytest.fail("Se persistió un Ticket pese al fallo ADO")
