"""
Test del filtro assigned_to en GET /api/tickets (Requerimiento B, plan 2026-05-27).

Verifica que pasar ?assigned_to=<uniqueName> devuelve únicamente los tickets
asignados a ese usuario, y que sin el filtro se listan todos.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app
    from db import init_db, session_scope
    from models import Ticket

    app = create_app()
    app.config["TESTING"] = True
    init_db()

    with session_scope() as session:
        session.query(Ticket).delete()
        session.add(Ticket(ado_id=101, project="X", title="Alice task",
                            assigned_to_ado="alice@x.com", ado_state="Active"))
        session.add(Ticket(ado_id=102, project="X", title="Bob task",
                            assigned_to_ado="bob@x.com", ado_state="Active"))
        session.add(Ticket(ado_id=103, project="X", title="Unassigned",
                            assigned_to_ado=None, ado_state="New"))

    with app.test_client() as c:
        yield c


def test_no_filter_lists_all(client):
    resp = client.get("/api/tickets")
    assert resp.status_code == 200
    ids = {t["ado_id"] for t in resp.get_json()}
    assert {101, 102, 103} <= ids


def test_assigned_to_filters_to_single_user(client):
    resp = client.get("/api/tickets?assigned_to=alice@x.com")
    assert resp.status_code == 200
    rows = resp.get_json()
    assert {t["ado_id"] for t in rows} == {101}
    assert rows[0]["assigned_to_ado"] == "alice@x.com"


def test_assigned_to_unknown_user_returns_empty(client):
    resp = client.get("/api/tickets?assigned_to=nobody@x.com")
    assert resp.status_code == 200
    assert resp.get_json() == []
