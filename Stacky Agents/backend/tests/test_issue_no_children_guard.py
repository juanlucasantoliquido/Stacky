"""Plan 77 F4 — Guard en create_child_task: Issues no pueden tener hijos.

Verifica que un intento de crear un task hijo sobre un ticket tipo Issue
retorna 400 ISSUE_CANNOT_HAVE_CHILDREN. Epics y otros tipos pasan.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def client():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        with app.app_context():
            yield c


def _create_ticket(wi_type: str, ado_id: int, project: str = "Pacifico"):
    """Inserta un Ticket de tipo wi_type en la DB de test."""
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket()
        t.ado_id = ado_id
        t.title = f"{wi_type} {ado_id}"
        t.work_item_type = wi_type
        t.project = project
        t.stacky_project_name = project
        session.add(t)


def _create_child_task_body(ado_id: int, dry_run: bool = True) -> dict:
    """Cuerpo mínimo para create_child_task (dry_run para no tocar ADO real)."""
    return {
        "pending_task_path": "fake_task.json",
        "repo_root": "/tmp/fake_repo",
        "dry_run": dry_run,
    }


def test_issue_ticket_blocks_child_creation(client):
    """[C3] Ticket Issue → create_child_task devuelve 400 ISSUE_CANNOT_HAVE_CHILDREN."""
    _create_ticket("Issue", ado_id=9200)
    body = _create_child_task_body(ado_id=9200)
    resp = client.post(
        "/api/tickets/by-ado/9200/create-child-task",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert resp.status_code == 400, (
        f"Esperado 400 para Issue, recibido {resp.status_code}: {resp.data[:400]}"
    )
    data = json.loads(resp.data)
    assert data.get("error") == "ISSUE_CANNOT_HAVE_CHILDREN", (
        f"Error esperado ISSUE_CANNOT_HAVE_CHILDREN, recibido: {data}"
    )


def test_issue_block_message_is_helpful(client):
    """El mensaje de error del guard indica por qué y qué hacer."""
    _create_ticket("Issue", ado_id=9201)
    body = _create_child_task_body(ado_id=9201)
    resp = client.post(
        "/api/tickets/by-ado/9201/create-child-task",
        data=json.dumps(body),
        content_type="application/json",
    )
    data = json.loads(resp.data)
    msg = data.get("message", "")
    assert "comentarios" in msg.lower() or "issue" in msg.lower(), (
        f"Mensaje no orientativo: {msg!r}"
    )


def test_epic_ticket_is_not_blocked(client):
    """Ticket Epic no es bloqueado por el guard del plan 77 (sigue el flujo normal)."""
    _create_ticket("Epic", ado_id=9202)
    body = _create_child_task_body(ado_id=9202)
    resp = client.post(
        "/api/tickets/by-ado/9202/create-child-task",
        data=json.dumps(body),
        content_type="application/json",
    )
    # El epic pasa el guard del plan 77; puede fallar en otro validador (ej.
    # MISSING_PENDING_TASK_PATH, 400 con otro error, o 422/500 por body incompleto)
    # lo que NO debe ser es error ISSUE_CANNOT_HAVE_CHILDREN.
    if resp.status_code == 400:
        data = json.loads(resp.data)
        assert data.get("error") != "ISSUE_CANNOT_HAVE_CHILDREN", (
            "Epic NO debe ser bloqueado por el guard de Issue."
        )


def test_unknown_ado_id_is_not_blocked(client):
    """Si el ado_id no está en DB, el guard no bloquea (el ticket no es Issue)."""
    body = _create_child_task_body(ado_id=99999)
    resp = client.post(
        "/api/tickets/by-ado/99999/create-child-task",
        data=json.dumps(body),
        content_type="application/json",
    )
    if resp.status_code == 400:
        data = json.loads(resp.data)
        assert data.get("error") != "ISSUE_CANNOT_HAVE_CHILDREN", (
            "Un ado_id desconocido NO debe bloquearse como Issue."
        )
