"""Tests para Fase 4: endpoint POST /api/tickets/{id}/finish-work.

Verifica:
  - operator_reason < 5 chars → 400.
  - ticket ya completed → 409.
  - dry_run retorna preconditions sin tocar nada.
  - publish con HTML válido invoca ado_publisher y devuelve ok.
  - sin HTML pero publish_to_ado=True → publica nota manual via ado_publisher.
  - target_ado_state invoca update_work_item_state.
  - update_stacky_status final es 'completed'.
  - HTML con secreto → 422 antes de tocar ADO.
  - update_work_item_state que falla queda registrado en actions con ok=False.
"""
from __future__ import annotations

import os
import sys
import tempfile
import json
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
    import api.tickets as tickets_mod
    monkeypatch.setattr(ado_client_mod, "AdoClient", FakeAdoClient)
    monkeypatch.setattr(pub_mod, "_default_client", lambda: FakeAdoClient())
    monkeypatch.setattr(tickets_mod, "_ado_client_for_ticket", lambda *a, **kw: FakeAdoClient())
    return FakeAdoClient


@pytest.fixture
def client(tmp_repo, monkeypatch):
    import app as app_module

    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setattr(app_module, "_startup_sync", lambda logger: None)
    app = app_module.create_app()
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


def _write_pending_task(repo_root: Path, ado_id: int) -> Path:
    out_dir = repo_root / "Agentes" / "outputs" / f"epic-{ado_id}" / "RF-001"
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_rel = f"Agentes/outputs/epic-{ado_id}/RF-001/plan-de-pruebas.md"
    (repo_root / plan_rel).write_text("# plan", encoding="utf-8")
    p = out_dir / "pending-task.json"
    p.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-04T00:00:00Z",
                "generated_by": "test",
                "epic_id": str(ado_id),
                "rf_id": "RF-001",
                "target_state": "Technical review",
                "title": "RF-001",
                "description_html": "<p>detalle</p>",
                "plan_de_pruebas_path": plan_rel,
                "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
                "status": "pending_manual_creation",
            }
        ),
        encoding="utf-8",
    )
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


def test_finish_work_publishes_manual_note_via_publisher_when_no_html(client, fake_ado, tmp_repo):
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
    assert actions_by["publish_ado_comment"]["reason"] == "manual_finish_note_via_publisher"
    assert actions_by["publish_ado_comment"]["html_sha256"]
    # Verificamos que el contenido sea la nota manual publicada via ado_publisher.
    posted = [c for c in FakeAdoClient.post_comment_calls if c[0] == 3005]
    assert posted, "se esperaba post_comment a ADO con la nota manual"
    assert "Cierre manual" in posted[0][1]
    assert "stacky-comment:ado=3005" in posted[0][1]


def test_finish_work_rejects_pending_tasks_without_force(client, fake_ado, tmp_repo):
    ticket_id = _mk_ticket(ado_id=3020)
    _write_pending_task(tmp_repo, 3020)

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "hay tareas pendientes",
            "publish_to_ado": True,
        },
    )

    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "PENDING_TASKS_NOT_CONSUMED"
    assert body["preconditions"]["pending_tasks"]["total_pending"] == 1
    assert FakeAdoClient.post_comment_calls == []


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
            "cancel_active_execution": False,
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    actions_by = {a["action"]: a for a in body["actions"]}
    assert "publish_ado_comment" not in actions_by
    assert actions_by["update_stacky_status"]["ok"] is True
    assert FakeAdoClient.post_comment_calls == []


# ── Feature #5 — TerminarTrabajo: tests de cancelación ───────────────────────


def _mk_ticket_with_active_exec(ado_id: int, exec_status: str = "running") -> tuple[int, int]:
    """Crea un ticket con una AgentExecution de status=exec_status.
    Retorna (ticket_id, execution_id)."""
    from db import session_scope
    from models import Ticket, AgentExecution

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id, project="RSPacifico",
            title=f"t-cancel-{ado_id}", ado_state="In Progress",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status=exec_status,
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(e)
        session.flush()
        return t.id, e.id


def test_finish_work_with_active_execution_calls_cancel(client, fake_ado, tmp_repo, monkeypatch):
    """CA-5.2: con ejecución activa, cancel_and_wait se invoca y cancel_result
    aparece en la respuesta con cancel_ok=True."""
    ticket_id, exec_id = _mk_ticket_with_active_exec(ado_id=5001)
    _write_html(tmp_repo, 5001, "<p>ok</p>")

    cancel_called: list[int] = []

    def fake_cancel_and_wait(execution_id: int, timeout_seconds: float = 5.0) -> dict:
        cancel_called.append(execution_id)
        # Simular que la ejecución paró correctamente
        from db import session_scope
        from models import AgentExecution
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row:
                row.status = "cancelled"
        return {"cancel_ok": True, "cancel_reason": None, "final_status": "cancelled"}

    import agent_runner
    monkeypatch.setattr(agent_runner, "cancel_and_wait", fake_cancel_and_wait)

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "terminar con ejecución activa",
            "publish_to_ado": False,
            "cancel_active_execution": True,
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()

    # cancel_and_wait fue invocado con el execution_id correcto
    assert cancel_called == [exec_id]

    # cancel_result presente con ok=True
    cr = body["cancel_result"]
    assert cr is not None
    assert cr["cancel_ok"] is True
    assert cr["execution_id"] == exec_id
    assert cr["agent_type"] == "developer"
    assert cr["cancel_reason"] is None

    # El cierre se completó igualmente
    actions_by = {a["action"]: a for a in body["actions"]}
    assert actions_by["update_stacky_status"]["ok"] is True
    assert body["current_status"] == "completed"


def test_finish_work_without_active_execution_cancel_result_is_none(client, fake_ado, tmp_repo, monkeypatch):
    """CA-5.4: sin ejecución activa, cancel_result es null y flujo es idéntico
    al cierre normal."""
    from db import session_scope
    from models import Ticket, AgentExecution

    # Ticket sin ejecución running (la única ejecución tiene status='completed')
    with session_scope() as session:
        t = Ticket(
            ado_id=5002, project="RSPacifico",
            title="t-no-active", ado_state="In Progress",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status="completed",  # no está running
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(e)
        session.flush()
        ticket_id = t.id

    _write_html(tmp_repo, 5002, "<p>ok</p>")

    cancel_called: list[int] = []

    def fake_cancel_and_wait(execution_id: int, timeout_seconds: float = 5.0) -> dict:
        cancel_called.append(execution_id)
        return {"cancel_ok": True, "cancel_reason": None, "final_status": "cancelled"}

    import agent_runner
    monkeypatch.setattr(agent_runner, "cancel_and_wait", fake_cancel_and_wait)

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "cierre sin ejecucion activa",
            "publish_to_ado": False,
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()

    # cancel_and_wait NO fue invocado
    assert cancel_called == []
    # cancel_result es null
    assert body["cancel_result"] is None

    actions_by = {a["action"]: a for a in body["actions"]}
    assert actions_by["update_stacky_status"]["ok"] is True


def test_finish_work_cancel_timeout_continues_close(client, fake_ado, tmp_repo, monkeypatch):
    """CA-5.3: cuando cancel_and_wait retorna cancel_ok=False (timeout),
    el cierre continúa igualmente y cancel_result refleja el fallo."""
    ticket_id, exec_id = _mk_ticket_with_active_exec(ado_id=5003)
    _write_html(tmp_repo, 5003, "<p>ok</p>")

    def fake_cancel_and_wait(execution_id: int, timeout_seconds: float = 5.0) -> dict:
        # Simular timeout: la ejecución sigue running
        return {"cancel_ok": False, "cancel_reason": "timeout", "final_status": "running"}

    import agent_runner
    monkeypatch.setattr(agent_runner, "cancel_and_wait", fake_cancel_and_wait)

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "cancelacion fallara",
            "publish_to_ado": False,
            "cancel_active_execution": True,
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()

    # cancel_result presente con cancel_ok=False
    cr = body["cancel_result"]
    assert cr is not None
    assert cr["cancel_ok"] is False
    assert cr["cancel_reason"] == "timeout"
    assert cr["execution_id"] == exec_id

    # A pesar del fallo de cancelación, el cierre se ejecutó
    actions_by = {a["action"]: a for a in body["actions"]}
    assert actions_by["update_stacky_status"]["ok"] is True
    assert body["current_status"] == "completed"


def test_finish_work_dry_run_shows_active_execution_in_preconditions(client, fake_ado, tmp_repo):
    """CA-5.1: dry_run muestra la ejecución activa en preconditions.active_execution."""
    ticket_id, exec_id = _mk_ticket_with_active_exec(ado_id=5004)
    _write_html(tmp_repo, 5004, "<p>ok</p>")

    r = client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "dry run con activa",
            "dry_run": True,
            "cancel_active_execution": True,
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["dry_run"] is True
    assert body["cancel_result"] is None  # dry_run no ejecuta cancelación

    ae = body["preconditions"]["active_execution"]
    assert ae is not None
    assert ae["execution_id"] == exec_id
    assert ae["agent_type"] == "developer"
    assert ae["will_cancel"] is True
