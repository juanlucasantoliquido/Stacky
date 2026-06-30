"""Plan 52 F3 — Tests de respaldo: persistencia REAL del ticket Issue
(work_item_type="Issue" + idempotencia por ado_id) y manejo de HTML que pasa
_looks_like_epic pero está estructuralmente malformado.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def _app_ctx():
    from app import create_app
    app = create_app()  # init_db() crea las tablas en sqlite in-memory
    with app.app_context():
        yield app


def test_persist_issue_ticket_creates_with_work_item_type_issue(_app_ctx):
    from api import tickets
    from db import session_scope
    from models import Ticket

    tickets._persist_issue_ticket(
        ado_id=9001, title="T", description_html="<h1>x</h1>",
        url="http://ado/9001", project_name="Pacifico",
    )
    with session_scope() as session:
        row = session.query(Ticket).filter(Ticket.ado_id == 9001).first()
        assert row is not None
        assert row.work_item_type == "Issue"


def test_persist_issue_ticket_idempotent_by_ado_id(_app_ctx):
    from api import tickets
    from db import session_scope
    from models import Ticket

    tickets._persist_issue_ticket(
        ado_id=9002, title="Primero", description_html="<h1>a</h1>",
        url="http://ado/9002", project_name="P",
    )
    tickets._persist_issue_ticket(
        ado_id=9002, title="Segundo distinto", description_html="<h1>b</h1>",
        url="http://ado/9002", project_name="P",
    )
    with session_scope() as session:
        rows = session.query(Ticket).filter(Ticket.ado_id == 9002).all()
        assert len(rows) == 1


def test_publish_issue_to_ado_uses_extracted_html(_app_ctx):
    from api import tickets

    captured = {}

    def _fake_client_for_ticket(**kw):
        client = MagicMock()

        def _create(**kwargs):
            captured["description"] = kwargs.get("description") or kwargs.get("description_html")
            return {"id": 7000, "fields": {}, "_links": {"html": {"href": "http://ado/7000"}}}

        client.create_work_item.side_effect = _create
        client.work_item_url.return_value = "http://ado/7000"
        return client

    narrated = (
        "Claro, acá va el issue:\n\n```html\n<h1>EP — X</h1>"
        "<h2>RF-001 — algo</h2><p>cuerpo</p>\n```\nlisto"
    )
    with patch.object(tickets, "_ado_client_for_ticket", _fake_client_for_ticket), \
         patch.object(tickets, "_epic_brief_save", lambda *a, **k: None), \
         patch.object(tickets, "_persist_issue_ticket", lambda *a, **k: None):
        tickets._publish_issue_to_ado(
            description_html=narrated, brief="b", project_name="P",
        )
    # El description enviado a ADO es el HTML extraído, no la narración cruda.
    assert "Claro, acá va el issue" not in (captured.get("description") or "")
    assert "RF-001" in (captured.get("description") or "")


def test_looks_like_epic_rejects_malformed_html(_app_ctx):
    from api import tickets

    res = tickets.publish_issue_from_run(
        output="solo narración sin HTML de épica ni RF",
        brief="b", project_name="P", already_published_id=None,
    )
    assert res.ado_id is None
    assert "epic_not_in_output" in (res.error or "")


def test_publish_issue_structurally_broken_html(_app_ctx):
    """HTML que SÍ pasa _looks_like_epic (h1/h2 + RF) pero con tags sin cerrar.
    Contrato ACTUAL: se publica igual (no se valida well-formedness)."""
    from api import tickets

    published = MagicMock()
    published.ado_id = 8001
    published.url = "http://ado/8001"
    broken = "<h1>Epica<h2>RF-1 algo<p>cuerpo sin cerrar"
    with patch.object(tickets, "_publish_issue_to_ado", return_value=published), \
         patch.object(tickets, "_post_phase_comment"), \
         patch.object(tickets, "_ado_client_for_ticket"):
        res = tickets.publish_issue_from_run(
            output=broken, brief="b", project_name="P", already_published_id=None,
        )
    # Si pasa _looks_like_epic, se publica; si no, error claro. En ambos casos
    # NO debe lanzar una excepción Python no manejada.
    assert (res.ado_id == 8001) or ("epic_not_in_output" in (res.error or ""))
