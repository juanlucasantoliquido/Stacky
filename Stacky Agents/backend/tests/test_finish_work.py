"""Tests para Fase 4: endpoint POST /api/tickets/{id}/finish-work.

Verifica:
  - operator_reason < 5 chars → 400.
  - ticket ya completed → 409.
  - dry_run retorna preconditions sin tocar nada.
  - publish con HTML válido invoca ado_publisher y devuelve ok.
  - sin HTML pero publish_to_ado=True → publica fallback note.
  - target_ado_state invoca update_work_item_state.
  - update_stacky_status final es 'completed'.
  - HTML con secreto → 422 antes de tocar ADO.
  - update_work_item_state que falla queda registrado en actions con ok=False.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_repo(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setenv("STACKY_REPO_ROOT", tmp.name)
    yield Path(tmp.name)
    tmp.cleanup()


class FakeAdoClient:
    instances: list["FakeAdoClient"] = []
    post_comment_calls: list[tuple[int, str, str]] = []
    update_state_calls: list[tuple[int, str]] = []
    raise_on: dict[str, Exception | None] = {}

    def __init__(self, *a, **kw):
        FakeAdoClient.instances.append(self)

    def post_comment(self, ado_id: int, text: str, fmt: str = "html") -> dict:
        if self.raise_on.get("post_comment"):
            raise self.raise_on["post_comment"]
        FakeAdoClient.post_comment_calls.append((ado_id, text, fmt))
        return {"id": 999, "url": "fake://comment"}

    def update_work_item_state(self, ado_id: int, new_state: str) -> dict:
        if self.raise_on.get("update_work_item_state"):
            raise self.raise_on["update_work_item_state"]
        FakeAdoClient.update_state_calls.append((ado_id, new_state))
        return {"id": ado_id, "fields": {"System.State": new_state}}


@pytest.fixture
def fake_ado(monkeypatch):
    FakeAdoClient.instances.clear()
    FakeAdoClient.post_comment_calls.clear()
    FakeAdoClient.update_state_calls.clear()
    FakeAdoClient.raise_on = {}
    # Parchea AdoClient en services.ado_client (donde finish_work lo importa)
    # y en services.ado_publisher._default_client.
    import services.ado_client as ado_client_mod
    import services.ado_publisher as pub_mod
    monkeypatch.setattr(ado_client_mod, "AdoClient", FakeAdoClient)
    monkeypatch.setattr(pub_mod, "_default_client", lambda: FakeAdoClient())
    return FakeAdoClient


@pytest.fixture
def client(tmp_repo):
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    from services.ticket_status import stop_stale_recovery
    stop_stale_recovery()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()


def _write_html(repo_root: Path, ado_id: int, html: str) -> Path:
    out_dir = repo_root / "Agentes" / "outputs" / str(ado_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "comment.html"
    p.write_text(html, encoding="utf-8")
    return p


def _mk_ticket(ado_id: int, stacky_status: str = "running") -> int:
    from db import session_scope
    from models import Ticket, AgentExecution

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id, project="RSPacifico",
            title=f"t-{ado_id}", ado_state="In Progress",
            stacky_status=stacky_status,
        )
        session.add(t)
        session.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status="running",
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(e)
        session.flush()
        return t.id


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_finish_work_rejects_short_reason(client, fake_ado):
    ticket_id = _mk_ticket(ado_id=3001)
    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={"operator_reason": "x"},
    )
    assert r.status_code == 400
    assert "operator_reason" in r.get_json()["error"]


def test_finish_work_409_when_already_completed(client, fake_ado):
    ticket_id = _mk_ticket(ado_id=3002, stacky_status="completed")
    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={"operator_reason": "ya estaba"},
    )
    assert r.status_code == 409


def test_finish_work_dry_run_no_side_effects(client, fake_ado, tmp_repo):
    ticket_id = _mk_ticket(ado_id=3003)
    _write_html(tmp_repo, 3003, "<p>Listo</p>")

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={"operator_reason": "dry-run check", "dry_run": True},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["dry_run"] is True
    assert body["preconditions"]["html_exists"] is True
    assert body["actions"] == []
    # No ADO calls
    assert FakeAdoClient.post_comment_calls == []
    assert FakeAdoClient.update_state_calls == []
    # Stacky status NO cambió
    assert body["current_status"] != "completed"


def test_finish_work_publishes_html_and_updates_state(client, fake_ado, tmp_repo):
    ticket_id = _mk_ticket(ado_id=3004)
    _write_html(tmp_repo, 3004, "<p>Listo desde finish-work</p>")

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "cierre manual",
            "publish_to_ado": True,
            "target_ado_state": "Done",
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    actions_by = {a["action"]: a for a in body["actions"]}
    assert actions_by["publish_ado_comment"]["ok"] is True
    assert actions_by["update_ado_state"]["ok"] is True
    assert actions_by["update_ado_state"]["to"] == "Done"
    assert actions_by["update_stacky_status"]["ok"] is True
    assert body["current_status"] == "completed"

    # ADO recibió la publicación + cambio de estado
    assert any(c[0] == 3004 for c in FakeAdoClient.post_comment_calls)
    assert (3004, "Done") in FakeAdoClient.update_state_calls


def test_finish_work_publishes_fallback_note_when_no_html(client, fake_ado, tmp_repo):
    ticket_id = _mk_ticket(ado_id=3005)
    # NO escribir HTML

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "no había html",
            "publish_to_ado": True,
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    actions_by = {a["action"]: a for a in body["actions"]}
    assert actions_by["publish_ado_comment"]["ok"] is True
    assert actions_by["publish_ado_comment"]["reason"] == "no_agent_html_fallback_note"
    # Verificamos que el contenido sea la nota fallback (sin _agent_html)
    posted = [c for c in FakeAdoClient.post_comment_calls if c[0] == 3005]
    assert posted, "se esperaba post_comment a ADO con la nota fallback"
    assert "Cierre manual" in posted[0][1]


def test_finish_work_rejects_html_with_secrets(client, fake_ado, tmp_repo):
    ticket_id = _mk_ticket(ado_id=3006)
    _write_html(tmp_repo, 3006, "<p>oops AKIAIOSFODNN7EXAMPLE</p>")

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "intento con secret",
            "publish_to_ado": True,
        },
    )
    assert r.status_code == 422
    # ADO no fue tocado
    assert FakeAdoClient.post_comment_calls == []
    assert FakeAdoClient.update_state_calls == []


def test_finish_work_records_ado_state_failure(client, fake_ado, tmp_repo):
    from services.ado_client import AdoApiError

    ticket_id = _mk_ticket(ado_id=3007)
    _write_html(tmp_repo, 3007, "<p>ok</p>")
    FakeAdoClient.raise_on = {
        "update_work_item_state": AdoApiError("ADO 400: invalid state"),
    }

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "ado va a fallar",
            "publish_to_ado": True,
            "target_ado_state": "InvalidState",
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    actions_by = {a["action"]: a for a in body["actions"]}
    assert actions_by["update_ado_state"]["ok"] is False
    assert "invalid state" in (actions_by["update_ado_state"]["reason"] or "").lower()
    # stacky_status sí pasa a completed (decisión: cerrar en BD aunque ADO falle)
    assert actions_by["update_stacky_status"]["ok"] is True
    # ok global = False porque al menos una acción falló
    assert body["ok"] is False


def test_finish_work_skips_publish_when_publish_to_ado_false(client, fake_ado, tmp_repo):
    ticket_id = _mk_ticket(ado_id=3008)
    _write_html(tmp_repo, 3008, "<p>x</p>")

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "solo cerrar en stacky",
            "publish_to_ado": False,
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    actions_by = {a["action"]: a for a in body["actions"]}
    assert "publish_ado_comment" not in actions_by
    assert actions_by["update_stacky_status"]["ok"] is True
    assert FakeAdoClient.post_comment_calls == []
