"""
Tests de services.ticket_assigner.auto_assign_on_run (B3, plan 2026-06-02).

Verifica:
  - Asigna al operador cuando el ticket está sin responsable (PATCH ADO + espejo local).
  - No-op idempotente si el ticket ya tiene assigned_to_ado.
  - Skip silencioso (sin romper) si la identidad ADO no se resuelve.
  - Nunca propaga excepciones del cliente ADO.
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


class _FakeClient:
    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    def update_work_item_assigned_to(self, ado_id, unique_name):
        self.calls.append((ado_id, unique_name))
        return {"ok": True}


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app  # noqa: F401 — fuerza el wiring de la app/DB
    from db import init_db

    create_app()
    init_db()
    yield


def _new_ticket(**kw):
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=kw.get("ado_id", 555),
            project="X",
            stacky_project_name=kw.get("stacky_project_name", "X"),
            title="t",
            ado_state="Technical review",
            assigned_to_ado=kw.get("assigned_to_ado"),
        )
        session.add(t)
        session.flush()
        return t.id


def _patch_identity(monkeypatch, me, client=None):
    import services.ado_identity as ai
    import services.project_context as pc

    monkeypatch.setattr(ai, "resolve_me_unique_name", lambda *_a, **_k: me)
    monkeypatch.setattr(pc, "build_ado_client", lambda *_a, **_k: client or _FakeClient())


def test_assigns_when_unassigned(monkeypatch, db):
    from services.ticket_assigner import auto_assign_on_run
    from db import session_scope
    from models import Ticket

    fake = _FakeClient()
    _patch_identity(monkeypatch, "JLuca@Ubimia.com", client=fake)
    tid = _new_ticket(ado_id=777, assigned_to_ado=None)

    result = auto_assign_on_run(tid, project_name="X")

    assert result == "JLuca@Ubimia.com"
    assert fake.calls == [(777, "JLuca@Ubimia.com")]
    with session_scope() as session:
        t = session.get(Ticket, tid)
        # Espejo local normalizado a minúsculas (coherente con B1).
        assert t.assigned_to_ado == "jluca@ubimia.com"


def test_noop_when_already_assigned(monkeypatch, db):
    from services.ticket_assigner import auto_assign_on_run

    fake = _FakeClient()
    _patch_identity(monkeypatch, "jluca@ubimia.com", client=fake)
    tid = _new_ticket(ado_id=778, assigned_to_ado="someone@x.com")

    assert auto_assign_on_run(tid, project_name="X") is None
    assert fake.calls == []  # no PATCH a ADO


def test_skip_when_identity_unresolved(monkeypatch, db):
    from services.ticket_assigner import auto_assign_on_run

    fake = _FakeClient()
    _patch_identity(monkeypatch, "", client=fake)  # identidad vacía
    tid = _new_ticket(ado_id=779, assigned_to_ado=None)

    assert auto_assign_on_run(tid, project_name="X") is None
    assert fake.calls == []


def test_never_raises_on_client_error(monkeypatch, db):
    from services.ticket_assigner import auto_assign_on_run

    class _Boom(_FakeClient):
        def update_work_item_assigned_to(self, *_a, **_k):
            raise RuntimeError("ADO caído")

    _patch_identity(monkeypatch, "jluca@ubimia.com", client=_Boom())
    tid = _new_ticket(ado_id=780, assigned_to_ado=None)

    # No debe propagar — el lanzamiento del agente nunca se rompe por esto.
    assert auto_assign_on_run(tid, project_name="X") is None
