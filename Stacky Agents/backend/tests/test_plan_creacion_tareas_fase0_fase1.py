"""Tests de regresion para el plan creacion-tareas-comentarios-100-efectiva
(2026-05-29), fases 0 y 1.

Cobertura:
  F1-A  post_comment levanta AdoApiError cuando ADO falla (ya no devuelve {}).
  F1-B  post_comment levanta AdoApiError cuando la respuesta no trae comment_id.
  F1-C  ado_publisher persiste comment_id y marker tras publish exitoso.
  F1-D  ado_publisher inyecta marcador stacky-comment en el HTML publicado.
  F0-A  create_child_task incluye operation_id y payload_sha256 en la respuesta.
  F0-B  create_child_task persiste operation_id y payload_sha256 en el archivo
        marcado como consumed.
  F0-C  endpoint /artifact-status devuelve el detalle de cada pending-task.json
        y los system_logs recientes.
  F0-D  Replay (mismo archivo consumed) devuelve idempotent + sha256.
  ORM   AgentExecution.html_output_path y completion_source son columnas reales.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── Fixtures comunes ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def flask_app():
    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    try:
        from services.ticket_status import stop_stale_recovery
        stop_stale_recovery()
    except Exception:
        pass
    return application


@pytest.fixture(scope="session", autouse=True)
def init_db(flask_app):
    from db import Base, engine
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client(flask_app):
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def tmp_repo(monkeypatch, tmp_path):
    import api.tickets as tickets_mod
    monkeypatch.setattr(tickets_mod, "REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def epic_ticket(flask_app):
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        existing = session.query(Ticket).filter(Ticket.ado_id == 8167).first()
        if existing:
            return 8167
        t = Ticket(
            ado_id=8167,
            project="TestProject",
            title="Epic 8167 — plan test",
            work_item_type="epic",
            ado_state="Active",
        )
        session.add(t)
    return 8167


def _write_pending_task(base: Path, epic_id: str, rf_id: str, slug: str = "test-rf") -> Path:
    folder = base / "Agentes" / "outputs" / f"epic-{epic_id}" / f"{rf_id.lower()}-{slug}"
    folder.mkdir(parents=True, exist_ok=True)
    plan_rel = f"Agentes/outputs/epic-{epic_id}/{rf_id.lower()}-{slug}/plan-de-pruebas.md"
    (base / plan_rel).write_text("# Plan\n", encoding="utf-8")
    payload = {
        "generated_at": "2026-05-29T10:00:00",
        "generated_by": "test",
        "epic_id": epic_id,
        "rf_id": rf_id,
        "target_state": "Technical review",
        "title": f"{rf_id} — Test plan fase 0",
        "description_html": "<p>desc</p>",
        "plan_de_pruebas_path": plan_rel,
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
        "status": "pending_manual_creation",
    }
    pt = folder / "pending-task.json"
    pt.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return pt


def _rel(base: Path, full: Path) -> str:
    return str(full.relative_to(base)).replace("\\", "/")


class FakeAdoClient:
    """Fake minimal para create_child_task con todas las operaciones."""

    def __init__(self):
        self.created = []
        self.comments = []

    def create_work_item(self, work_item_type, fields=None, parent_ado_id=None,
                         title="", description="", initial_state="", parent_id=None):
        self.created.append({"type": work_item_type, "parent": parent_ado_id or parent_id})
        return {"id": 9172, "url": "https://ado.test/wi/9172"}

    def update_work_item_state(self, ado_id, new_state):
        return {"id": ado_id, "state": new_state}

    def upload_attachment(self, file_path, file_name):
        return {"id": "att-1", "url": f"https://ado.test/att/{file_name}"}

    def link_attachment_to_work_item(self, work_item_id, attachment_url, comment=""):
        return {}

    def post_comment(self, ado_id, text, fmt="html"):
        self.comments.append({"ado_id": ado_id, "text": text, "fmt": fmt})
        return {"id": 4242}

    def work_item_url(self, ado_id):
        return f"https://ado.test/wi/{ado_id}"


# ── F1-A / F1-B — post_comment no oculta errores ─────────────────────────────

def test_post_comment_raises_on_empty_response(monkeypatch):
    """F1-B: si ADO responde sin id, post_comment debe levantar AdoApiError."""
    from services.ado_client import AdoClient, AdoApiError

    client = AdoClient.__new__(AdoClient)
    client.org = "TestOrg"
    client.project = "TestProj"
    client._base_proj = "https://dev.azure.com/TestOrg/TestProj"
    client._auth = "Basic test"

    monkeypatch.setattr(
        AdoClient,
        "_request_with_retry",
        lambda self, *a, **kw: {},  # respuesta vacia => debe lanzar
    )
    with pytest.raises(AdoApiError):
        client.post_comment(123, "<p>hola</p>")


def test_post_comment_raises_on_api_error(monkeypatch):
    """F1-A: si ADO responde con error HTTP, post_comment propaga AdoApiError."""
    from services.ado_client import AdoClient, AdoApiError

    client = AdoClient.__new__(AdoClient)
    client.org = "TestOrg"
    client.project = "TestProj"
    client._base_proj = "https://dev.azure.com/TestOrg/TestProj"
    client._auth = "Basic test"

    def _raise(self, *a, **kw):
        raise AdoApiError("ADO 500 simulated", status_code=500)

    monkeypatch.setattr(AdoClient, "_request_with_retry", _raise)
    with pytest.raises(AdoApiError):
        client.post_comment(123, "<p>hola</p>")


# ── ORM — html_output_path y completion_source son columnas reales ───────────

def test_agent_execution_columns_persist_across_sessions(flask_app, init_db):
    """F1.3: html_output_path y completion_source persisten tras commit+reload."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=99999,
            project="TestProject",
            title="Persist columns test",
            work_item_type="epic",
            ado_state="Active",
        )
        session.add(t)
        session.flush()
        exec_row = AgentExecution(
            ticket_id=t.id,
            agent_type="analyst",
            status="completed",
            input_context_json="[]",
            started_by="test",
        )
        exec_row.html_output_path = "Agentes/outputs/persist/comment.html"
        exec_row.completion_source = "agent_gateway"
        session.add(exec_row)
        session.flush()
        eid = exec_row.id

    with session_scope() as session:
        reloaded = session.get(AgentExecution, eid)
        assert reloaded is not None
        assert reloaded.html_output_path == "Agentes/outputs/persist/comment.html"
        assert reloaded.completion_source == "agent_gateway"


# ── F0-A — create_child_task incluye operation_id y payload_sha256 ──────────

def test_create_child_task_response_includes_operation_id_and_sha(client, epic_ticket, tmp_repo):
    pt = _write_pending_task(tmp_repo, "8167", "RF-201")
    rel_path = _rel(tmp_repo, pt)

    with patch("api.tickets._ado_client_for_ticket", return_value=FakeAdoClient()):
        resp = client.post(
            "/api/tickets/by-ado/8167/create-child-task",
            json={"pending_task_path": rel_path},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data.get("operation_id"), "operation_id ausente en la respuesta"
    assert data.get("payload_sha256"), "payload_sha256 ausente en la respuesta"
    assert len(data["payload_sha256"]) == 64


# ── F0-B — operation_id y sha persisten en el archivo consumed ──────────────

def test_pending_task_consumed_records_operation_id_and_sha(client, epic_ticket, tmp_repo):
    from api.tickets import _payload_logical_sha256
    pt = _write_pending_task(tmp_repo, "8167", "RF-202")
    rel_path = _rel(tmp_repo, pt)
    original_payload = json.loads(pt.read_text(encoding="utf-8"))
    expected_sha = _payload_logical_sha256(original_payload)

    with patch("api.tickets._ado_client_for_ticket", return_value=FakeAdoClient()):
        resp = client.post(
            "/api/tickets/by-ado/8167/create-child-task",
            json={"pending_task_path": rel_path},
        )
    assert resp.status_code == 200

    saved = json.loads(pt.read_text(encoding="utf-8"))
    assert saved["status"] == "consumed"
    assert saved.get("task_ado_id") == 9172
    assert saved.get("payload_sha256") == expected_sha
    assert saved.get("operation_id"), "operation_id no se persistio en el archivo"


# ── F0-D — Replay: archivo consumed devuelve idempotent ──────────────────────

def test_replay_returns_idempotent_with_sha(client, epic_ticket, tmp_repo):
    pt = _write_pending_task(tmp_repo, "8167", "RF-203")
    rel_path = _rel(tmp_repo, pt)
    with patch("api.tickets._ado_client_for_ticket", return_value=FakeAdoClient()):
        first = client.post(
            "/api/tickets/by-ado/8167/create-child-task",
            json={"pending_task_path": rel_path},
        )
        second = client.post(
            "/api/tickets/by-ado/8167/create-child-task",
            json={"pending_task_path": rel_path},
        )
    assert first.status_code == 200
    assert second.status_code == 200
    second_data = second.get_json()
    assert second_data["ok"] is True
    assert second_data.get("idempotent") is True
    assert second_data.get("reason") == "PENDING_TASK_ALREADY_CONSUMED"
    assert second_data.get("task_ado_id") == 9172
    assert second_data.get("payload_sha256")
    assert second_data.get("operation_id")


# ── F0-C — endpoint /artifact-status ─────────────────────────────────────────

def test_artifact_status_returns_artifacts_after_consume(client, epic_ticket, tmp_repo):
    pt = _write_pending_task(tmp_repo, "8167", "RF-204")
    rel_path = _rel(tmp_repo, pt)
    with patch("api.tickets._ado_client_for_ticket", return_value=FakeAdoClient()):
        client.post(
            "/api/tickets/by-ado/8167/create-child-task",
            json={"pending_task_path": rel_path},
        )

    resp = client.get("/api/tickets/by-ado/8167/artifact-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["epic_ado_id"] == 8167
    assert data["epic_outputs_exists"] is True
    assert data["artifact_count"] >= 1

    found = [a for a in data["artifacts"] if a.get("rf_id") == "RF-204"]
    assert found, "RF-204 no aparece en artifact-status"
    artifact = found[0]
    assert artifact["status"] == "consumed"
    assert artifact["task_ado_id"] == 9172
    assert artifact["payload_sha256_current"]
    assert artifact["payload_sha256_at_consume"] == artifact["payload_sha256_current"]
    assert artifact["payload_hash_diverged"] is False
    assert artifact["plan_exists"] is True


def test_artifact_status_detects_diverged_hash(client, epic_ticket, tmp_repo):
    """Despues de consumir, si el operador edita el archivo, payload_hash_diverged=True."""
    pt = _write_pending_task(tmp_repo, "8167", "RF-205")
    rel_path = _rel(tmp_repo, pt)
    with patch("api.tickets._ado_client_for_ticket", return_value=FakeAdoClient()):
        client.post(
            "/api/tickets/by-ado/8167/create-child-task",
            json={"pending_task_path": rel_path},
        )

    # Modificar el archivo (simulando refresh del agente)
    saved = json.loads(pt.read_text(encoding="utf-8"))
    saved["description_html"] = "<p>contenido NUEVO</p>"
    pt.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    resp = client.get("/api/tickets/by-ado/8167/artifact-status")
    data = resp.get_json()
    artifact = next(a for a in data["artifacts"] if a.get("rf_id") == "RF-205")
    assert artifact["payload_hash_diverged"] is True
    assert artifact["payload_sha256_current"] != artifact["payload_sha256_at_consume"]


# ── F1-C / F1-D — ado_publisher inyecta marker y persiste comment_id ────────

def test_publisher_persists_comment_id_and_marker(flask_app, init_db, tmp_path, monkeypatch):
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import ado_publisher

    # 1. Crear ticket y execution
    with session_scope() as session:
        t = Ticket(
            ado_id=88001,
            project="TestProject",
            title="publisher marker test",
            work_item_type="task",
            ado_state="Active",
        )
        session.add(t)
        session.flush()
        ticket_id = t.id
        exec_row = AgentExecution(
            ticket_id=ticket_id,
            agent_type="analyst",
            status="completed",
            input_context_json="[]",
            started_by="test",
            html_output_path=None,
            completion_source="agent_gateway",
        )
        session.add(exec_row)
        session.flush()
        execution_id = exec_row.id

    # 2. Escribir comment.html
    html_dir = tmp_path / "Agentes" / "outputs" / "88001"
    html_dir.mkdir(parents=True, exist_ok=True)
    html_path = html_dir / "comment.html"
    html_path.write_text("<h2>Resultado</h2><p>OK</p>", encoding="utf-8")

    # 3. Patchear default_html_path para que apunte al tmp
    from services import agent_html_output as html_io
    monkeypatch.setattr(html_io, "default_html_path", lambda ado_id: html_path)

    # 4. Fake client que captura el texto publicado
    captured = {}

    class FakeClient:
        def post_comment(self, ado_id, text, fmt="html"):
            captured["ado_id"] = ado_id
            captured["text"] = text
            return {"id": 7777}

        def upload_attachment(self, *a, **kw):
            return {"id": "x", "url": "https://ado/x"}

        def link_attachment_to_work_item(self, *a, **kw):
            return {}

    result = ado_publisher.publish_from_execution(
        execution_id,
        triggered_by="pytest",
        client_factory=lambda: FakeClient(),
    )

    assert result.ok is True
    assert result.status == "ok"
    assert result.comment_id == 7777
    assert result.marker and result.marker.startswith("stacky-comment:")
    # El marker debe estar embebido en el texto publicado.
    assert result.marker in captured["text"], "marker no inyectado en el HTML publicado"

    # Persistido en DB
    with session_scope() as session:
        from services.ado_publisher import AgentHtmlPublish
        row = session.get(AgentHtmlPublish, result.record_id)
        assert row is not None
        assert row.comment_id == 7777
        assert row.marker == result.marker
