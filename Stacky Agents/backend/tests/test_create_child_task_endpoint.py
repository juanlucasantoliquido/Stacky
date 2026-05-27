"""Tests de integración para POST /api/tickets/by-ado/{epic_ado_id}/create-child-task
y GET /api/tickets/by-ado/{epic_ado_id}/pending-tasks (Fase 2).

TU-01   POST exitoso: crea Task, sube adjunto, linkea, marca consumido.
TU-03   Tras éxito: pending-task.json tiene consumed_at y task_ado_id.
TU-04   Segunda invocación con mismo archivo → idempotent=true, sin llamar ADO.
TU-05   dry_run=true: no llama ADO, no modifica archivo, devuelve actions.
TU-06   upload_attachment falla: Task creada, pending_task_consumed=false.
TU-07   operator_reason en SystemLog y en la cadena de acciones.
TU-08   Header X-Completion-Source: manual_ui → registrado en SystemLog.
TU-10a  Schema inválido (title faltante) → 400, sin llamadas ADO.
TU-10b  Archivo no encontrado → 400 con PENDING_TASK_FILE_NOT_FOUND.
TU-10c  epic_id mismatch → 400 con PENDING_TASK_EPIC_MISMATCH.
TU-11a  GET pending-tasks lista solo los pendientes.
TU-11b  GET pending-tasks no lista los consumidos.
TU-11c  GET pending-tasks devuelve conteos correctos.
TU-11d  GET pending-tasks devuelve plan_exists=false si plan no existe.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ---------------------------------------------------------------------------
# Setup de la app Flask y BD en memoria
# ---------------------------------------------------------------------------

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
    """Client por función para evitar contaminación de contexto entre tests."""
    with flask_app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Fixtures: tickets y pending-task.json en disco
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_repo(monkeypatch, tmp_path):
    """Repositorio temporal con estructura de outputs.

    Patchea api.tickets.REPO_ROOT para que el endpoint use el directorio temporal.
    """
    import api.tickets as tickets_mod
    monkeypatch.setattr(tickets_mod, "REPO_ROOT", tmp_path)
    return tmp_path


def _write_pending_task(
    base: Path,
    epic_id: str = "149",
    rf_id: str = "RF-001",
    slug: str = "gestión-perfiles",
    extra_fields: dict | None = None,
    omit_fields: list[str] | None = None,
) -> Path:
    """Helper: escribe un pending-task.json válido y retorna su ruta."""
    folder = base / "Agentes" / "outputs" / f"epic-{epic_id}" / f"{rf_id}-{slug}"
    folder.mkdir(parents=True, exist_ok=True)

    plan_rel = f"Agentes/outputs/epic-{epic_id}/{rf_id}-{slug}/plan-de-pruebas.md"
    plan_path = base / plan_rel
    plan_path.write_text("# Plan de Pruebas\n\nContenido.", encoding="utf-8")

    payload = {
        "generated_at": "2026-05-15T10:30:00",
        "generated_by": "AnalistaFuncional v1.2.0",
        "epic_id": epic_id,
        "rf_id": rf_id,
        "target_state": "Technical review",
        "title": f"{rf_id} — Gestión de perfiles de usuario",
        "description_html": "<h2>Análisis</h2><p>Contenido del análisis.</p>",
        "plan_de_pruebas_path": plan_rel,
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
        "status": "pending_manual_creation",
    }
    if extra_fields:
        payload.update(extra_fields)
    if omit_fields:
        for f in omit_fields:
            payload.pop(f, None)

    pt_path = folder / "pending-task.json"
    pt_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return pt_path


@pytest.fixture
def epic_ticket(flask_app):
    """Crea un ticket Epic en BD y retorna su ado_id."""
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        existing = session.query(Ticket).filter(Ticket.ado_id == 149).first()
        if existing:
            return 149
        t = Ticket(
            ado_id=149,
            project="TestProject",
            title="Epic 149 — Test",
            work_item_type="epic",
            ado_state="Active",
        )
        session.add(t)
    return 149


# ---------------------------------------------------------------------------
# Fake AdoClient para las extensiones
# ---------------------------------------------------------------------------

class FakeAdoClientExt:
    """Mock de las 3 operaciones nuevas de AdoClient."""

    def __init__(self, *a, **kw):
        self.create_calls: list[dict] = []
        self.upload_calls: list[dict] = []
        self.link_calls: list[dict] = []
        self.comment_calls: list[dict] = []
        self.state_calls: list[dict] = []
        self._raise_on_upload: Exception | None = None
        self._raise_on_state: Exception | None = None

    def create_work_item(
        self,
        work_item_type: str,
        title: str = "",
        description: str = "",
        initial_state: str = "",
        parent_id=None,
        fields: dict | None = None,
        parent_ado_id=None,
    ):
        # Firma unificada WS1+WS2: acepta tanto keywords nuevos como alias de compatibilidad.
        effective_parent = parent_ado_id if parent_ado_id is not None else parent_id
        self.create_calls.append({
            "type": work_item_type,
            "fields": fields,
            "parent": effective_parent,
        })
        return {"id": 5000, "url": "https://dev.azure.com/TestOrg/TestProject/_apis/wit/workitems/5000"}

    def update_work_item_state(self, ado_id, new_state):
        if self._raise_on_state:
            raise self._raise_on_state
        self.state_calls.append({"ado_id": ado_id, "new_state": new_state})
        return {"id": ado_id, "state": new_state}

    def upload_attachment(self, file_path, file_name):
        if self._raise_on_upload:
            raise self._raise_on_upload
        self.upload_calls.append({"file_path": str(file_path), "file_name": file_name})
        return {
            "id": "attach-uuid-001",
            "url": "https://dev.azure.com/TestOrg/TestProject/_apis/wit/attachments/attach-uuid-001",
        }

    def link_attachment_to_work_item(self, work_item_id, attachment_url, comment=""):
        self.link_calls.append({
            "work_item_id": work_item_id,
            "attachment_url": attachment_url,
            "comment": comment,
        })

    def post_comment(self, ado_id, text, fmt="html"):
        self.comment_calls.append({"ado_id": ado_id, "text": text, "fmt": fmt})
        return {"id": 9001}

    def work_item_url(self, ado_id: int) -> str:
        return f"https://dev.azure.com/TestOrg/TestProject/_workitems/edit/{ado_id}"


# ---------------------------------------------------------------------------
# Helpers para el path relativo al repo
# ---------------------------------------------------------------------------

def _rel_path(base: Path, full_path: Path) -> str:
    return str(full_path.relative_to(base)).replace("\\", "/")


# ---------------------------------------------------------------------------
# TU-01 — POST exitoso: crea Task, sube adjunto, linkea, marca consumido
# ---------------------------------------------------------------------------

def test_create_child_task_success(client, epic_ticket, tmp_repo):
    """TU-01: Flujo completo exitoso — Task creada, adjunto subido y linkeado."""
    pt_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-001")
    rel_path = _rel_path(tmp_repo, pt_path)

    fake_ado = FakeAdoClientExt()

    with patch("api.tickets._ado_client_for_ticket", return_value=fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path, "operator_reason": "Aprobado en daily"},
            headers={"X-Completion-Source": "manual_ui"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["task_ado_id"] == 5000
    assert data["task_url"] is not None and "5000" in data["task_url"]
    assert data["attachment_id"] == "attach-uuid-001"
    assert data["pending_task_consumed"] is True
    assert data["dry_run"] is False

    # Verificar cadena de acciones
    action_names = [a["action"] for a in data["actions"]]
    assert "create_work_item" in action_names
    assert "upload_attachment" in action_names
    assert "link_attachment" in action_names

    # Verificar que AdoClient fue llamado correctamente
    assert len(fake_ado.create_calls) == 1
    assert fake_ado.create_calls[0]["parent"] == 149
    assert len(fake_ado.upload_calls) == 1
    assert len(fake_ado.link_calls) == 1


# ---------------------------------------------------------------------------
# TU-03 — pending-task.json se marca como consumido
# ---------------------------------------------------------------------------

def test_pending_task_marked_consumed(client, epic_ticket, tmp_repo):
    """TU-03: Tras éxito, el archivo tiene consumed_at y task_ado_id."""
    pt_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-003")
    rel_path = _rel_path(tmp_repo, pt_path)
    fake_ado = FakeAdoClientExt()

    with patch("api.tickets._ado_client_for_ticket", return_value=fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path},
        )

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    # Verificar el archivo en disco
    payload = json.loads(pt_path.read_text(encoding="utf-8"))
    assert "consumed_at" in payload, "El archivo debe tener consumed_at"
    assert payload["task_ado_id"] == 5000
    assert payload["status"] == "consumed"

    # Verificar que consumed_at es un ISO 8601 válido
    datetime.fromisoformat(payload["consumed_at"])


# ---------------------------------------------------------------------------
# TU-04 — Idempotencia: segunda invocación devuelve tarea previa
# ---------------------------------------------------------------------------

def test_idempotency_already_consumed(client, epic_ticket, tmp_repo):
    """TU-04: Segunda invocación con archivo ya consumido → idempotent=true, sin llamar ADO."""
    pt_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-004")
    rel_path = _rel_path(tmp_repo, pt_path)
    fake_ado = FakeAdoClientExt()

    # Primera invocación
    with patch("api.tickets._ado_client_for_ticket", return_value=fake_ado):
        r1 = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path},
        )
    assert r1.get_json()["ok"] is True

    # Reiniciar fake para la segunda invocación
    fake_ado2 = FakeAdoClientExt()

    # Segunda invocación
    with patch("api.tickets._ado_client_for_ticket", return_value=fake_ado2), \
         patch("api.tickets.REPO_ROOT", tmp_repo):
        r2 = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path},
        )

    data2 = r2.get_json()
    assert r2.status_code == 200
    assert data2["ok"] is True
    assert data2["idempotent"] is True
    assert data2["reason"] == "PENDING_TASK_ALREADY_CONSUMED"
    assert data2["task_ado_id"] == 5000
    assert data2["pending_task_consumed"] is True

    # ADO NO debe haber sido llamado en la segunda invocación
    assert len(fake_ado2.create_calls) == 0
    assert len(fake_ado2.upload_calls) == 0
    assert len(fake_ado2.link_calls) == 0


# ---------------------------------------------------------------------------
# TU-05 — dry_run: no toca ADO ni el archivo
# ---------------------------------------------------------------------------

def test_dry_run_no_ado_calls(client, epic_ticket, tmp_repo):
    """TU-05: dry_run=true → plan de acciones, sin llamadas ADO, archivo intacto."""
    pt_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-005")
    rel_path = _rel_path(tmp_repo, pt_path)
    content_before = pt_path.read_bytes()
    fake_ado = FakeAdoClientExt()

    with patch("api.tickets.AdoClient", new=lambda *a, **kw: fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path, "dry_run": True},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["dry_run"] is True
    assert data["pending_task_consumed"] is False
    assert data["task_ado_id"] is None

    # El archivo no fue modificado
    assert pt_path.read_bytes() == content_before

    # ADO no fue llamado
    assert len(fake_ado.create_calls) == 0
    assert len(fake_ado.upload_calls) == 0
    assert len(fake_ado.link_calls) == 0

    # Debe haber un plan de acciones con would_call
    action_names = [a["action"] for a in data["actions"]]
    assert "create_work_item" in action_names


# ---------------------------------------------------------------------------
# TU-06 — Fallo parcial: Task creada, adjunto falla → no se marca consumido
# ---------------------------------------------------------------------------

def test_partial_failure_attachment_upload(client, epic_ticket, tmp_repo):
    """TU-06: Si upload_attachment falla, Task existe en ADO pero archivo no se consume."""
    from services.ado_client import AdoApiError

    pt_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-006")
    rel_path = _rel_path(tmp_repo, pt_path)

    fake_ado = FakeAdoClientExt()
    fake_ado._raise_on_upload = AdoApiError("ADO _apis/wit/attachments → 503: Service Unavailable")

    with patch("api.tickets._ado_client_for_ticket", return_value=fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path},
        )

    data = resp.get_json()
    assert resp.status_code == 200  # El endpoint devuelve 200 con ok=false (degraded state)
    assert data["ok"] is False
    assert data["task_ado_id"] == 5000, "La Task fue creada aunque el adjunto falló"
    assert data["pending_task_consumed"] is False

    # El archivo NO debe tener consumed_at
    payload = json.loads(pt_path.read_text(encoding="utf-8"))
    assert "consumed_at" not in payload

    # human_action_required debe estar presente
    assert "human_action_required" in data and data["human_action_required"]

    # actions debe mostrar create ok y upload fail
    actions_by_name = {a["action"]: a for a in data["actions"]}
    assert actions_by_name.get("create_work_item", {}).get("ok") is True
    assert actions_by_name.get("upload_attachment", {}).get("ok") is False


# ---------------------------------------------------------------------------
# TU-07 — operator_reason en SystemLog
# ---------------------------------------------------------------------------

def test_operator_reason_in_system_log(client, epic_ticket, tmp_repo):
    """TU-07: operator_reason persiste en SystemLog."""
    from db import session_scope
    from models import SystemLog

    pt_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-007")
    rel_path = _rel_path(tmp_repo, pt_path)
    fake_ado = FakeAdoClientExt()

    reason = "Revisado por PO en reunión del 2026-05-15"

    with patch("api.tickets.AdoClient", new=lambda *a, **kw: fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path, "operator_reason": reason},
        )

    assert resp.get_json()["ok"] is True

    # Verificar en BD
    with session_scope() as session:
        logs = (
            session.query(SystemLog)
            .filter(SystemLog.source == "create_child_task")
            .order_by(SystemLog.id.desc())
            .limit(5)
            .all()
        )
    assert len(logs) > 0
    context = json.loads(logs[0].context_json or "{}")
    assert context.get("operator_reason") == reason


# ---------------------------------------------------------------------------
# TU-08 — X-Completion-Source registrado en auditoría
# ---------------------------------------------------------------------------

def test_completion_source_header_in_audit(client, epic_ticket, tmp_repo):
    """TU-08: Header X-Completion-Source: manual_ui → completion_source en SystemLog."""
    from db import session_scope
    from models import SystemLog

    pt_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-008")
    rel_path = _rel_path(tmp_repo, pt_path)
    fake_ado = FakeAdoClientExt()

    with patch("api.tickets.AdoClient", new=lambda *a, **kw: fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path},
            headers={"X-Completion-Source": "manual_ui"},
        )

    assert resp.get_json()["ok"] is True

    with session_scope() as session:
        logs = (
            session.query(SystemLog)
            .filter(SystemLog.source == "create_child_task")
            .order_by(SystemLog.id.desc())
            .limit(3)
            .all()
        )
    assert len(logs) > 0
    context = json.loads(logs[0].context_json or "{}")
    assert context.get("completion_source") == "manual_ui"


# ---------------------------------------------------------------------------
# TU-10a — Schema inválido: title faltante → 400
# ---------------------------------------------------------------------------

def test_schema_invalid_missing_title(client, epic_ticket, tmp_repo):
    """TU-10a: pending-task.json sin 'title' → 400 PENDING_TASK_SCHEMA_INVALID."""
    pt_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-010a", omit_fields=["title"])
    rel_path = _rel_path(tmp_repo, pt_path)
    fake_ado = FakeAdoClientExt()

    with patch("api.tickets.AdoClient", new=lambda *a, **kw: fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path},
        )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "PENDING_TASK_SCHEMA_INVALID"
    assert "title" in (data.get("missing_fields") or [])

    # ADO no fue llamado
    assert len(fake_ado.create_calls) == 0


# ---------------------------------------------------------------------------
# TU-10b — Archivo no encontrado → 400
# ---------------------------------------------------------------------------

def test_file_not_found(client, epic_ticket, tmp_repo):
    """TU-10b: pending_task_path inexistente → 400 PENDING_TASK_FILE_NOT_FOUND."""
    fake_ado = FakeAdoClientExt()

    with patch("api.tickets.AdoClient", new=lambda *a, **kw: fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": "Agentes/outputs/epic-149/no-existe/pending-task.json"},
        )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "PENDING_TASK_FILE_NOT_FOUND"
    assert len(fake_ado.create_calls) == 0


# ---------------------------------------------------------------------------
# TU-10c — epic_id mismatch → 400
# ---------------------------------------------------------------------------

def test_epic_id_mismatch(client, epic_ticket, tmp_repo):
    """TU-10c: epic_id en JSON no coincide con epic_ado_id en URL → 400 PENDING_TASK_EPIC_MISMATCH."""
    # epic_id en el archivo dice "999" pero la URL es /by-ado/149/...
    pt_path = _write_pending_task(
        tmp_repo, epic_id="149", rf_id="RF-010c",
        extra_fields={"epic_id": "999"}  # mismatch intencional
    )
    rel_path = _rel_path(tmp_repo, pt_path)
    fake_ado = FakeAdoClientExt()

    with patch("api.tickets.AdoClient", new=lambda *a, **kw: fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path},
        )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "PENDING_TASK_EPIC_MISMATCH"
    assert len(fake_ado.create_calls) == 0


# ---------------------------------------------------------------------------
# TU-11a — GET pending-tasks lista solo pendientes
# ---------------------------------------------------------------------------

def test_list_pending_tasks_only_pending(client, epic_ticket, tmp_repo):
    """TU-11a: Solo los archivos con status=pending_manual_creation aparecen en la lista."""
    # Crear 2 pendientes y 1 consumido
    _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-011a1")
    _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-011a2")
    consumed_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-011a3")

    # Marcar el tercero como consumido
    payload = json.loads(consumed_path.read_text(encoding="utf-8"))
    payload["consumed_at"] = "2026-05-14T09:00:00"
    payload["task_ado_id"] = 4000
    payload["status"] = "consumed"
    consumed_path.write_text(json.dumps(payload), encoding="utf-8")

    resp = client.get("/api/tickets/by-ado/149/pending-tasks")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True

    pending_rf_ids = [item["rf_id"] for item in data["pending_tasks"]]
    assert "RF-011a1" in pending_rf_ids
    assert "RF-011a2" in pending_rf_ids
    assert "RF-011a3" not in pending_rf_ids


# ---------------------------------------------------------------------------
# TU-11b — GET pending-tasks no lista consumidos
# ---------------------------------------------------------------------------

def test_list_pending_tasks_excludes_consumed(client, epic_ticket, tmp_repo):
    """TU-11b: pending-task.json con consumed_at no aparece en la lista."""
    consumed_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-011b")
    payload = json.loads(consumed_path.read_text(encoding="utf-8"))
    payload["consumed_at"] = "2026-05-10T08:00:00"
    payload["task_ado_id"] = 3001
    payload["status"] = "consumed"
    consumed_path.write_text(json.dumps(payload), encoding="utf-8")

    resp = client.get("/api/tickets/by-ado/149/pending-tasks")

    data = resp.get_json()
    assert "RF-011b" not in [item["rf_id"] for item in data["pending_tasks"]]


# ---------------------------------------------------------------------------
# TU-11c — GET pending-tasks devuelve conteos correctos
# ---------------------------------------------------------------------------

def test_list_pending_tasks_counts(client, epic_ticket, tmp_repo):
    """TU-11c: total_pending y total_consumed son correctos."""
    # Arrancar con un Epic limpio para este test
    # Crear estructura para epic-1110 (distinto al 149 de otros tests)
    _write_pending_task(tmp_repo, epic_id="1110", rf_id="RF-001")
    _write_pending_task(tmp_repo, epic_id="1110", rf_id="RF-002")
    consumed_path = _write_pending_task(tmp_repo, epic_id="1110", rf_id="RF-003")
    payload = json.loads(consumed_path.read_text(encoding="utf-8"))
    payload.update({"consumed_at": "2026-05-01T00:00:00", "task_ado_id": 9999, "status": "consumed"})
    consumed_path.write_text(json.dumps(payload), encoding="utf-8")

    # Crear ticket Epic para 1110
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        if not session.query(Ticket).filter(Ticket.ado_id == 1110).first():
            session.add(Ticket(ado_id=1110, project="TestProject", title="Epic 1110", work_item_type="epic"))

    resp = client.get("/api/tickets/by-ado/1110/pending-tasks")

    data = resp.get_json()
    assert data["total_pending"] == 2
    assert data["total_consumed"] == 1


# ---------------------------------------------------------------------------
# TU-11d — GET pending-tasks plan_exists=false si plan no existe
# ---------------------------------------------------------------------------

def test_list_pending_tasks_plan_exists_false(client, epic_ticket, tmp_repo):
    """TU-11d: Si el plan-de-pruebas.md no existe, plan_exists=false."""
    pt_path = _write_pending_task(tmp_repo, epic_id="149", rf_id="RF-011d")

    # Eliminar el plan
    payload = json.loads(pt_path.read_text(encoding="utf-8"))
    plan_full = tmp_repo / payload["plan_de_pruebas_path"]
    if plan_full.exists():
        plan_full.unlink()

    resp = client.get("/api/tickets/by-ado/149/pending-tasks")

    data = resp.get_json()
    items_rf11d = [item for item in data["pending_tasks"] if item["rf_id"] == "RF-011d"]
    assert len(items_rf11d) > 0
    assert items_rf11d[0]["plan_exists"] is False


# ---------------------------------------------------------------------------
# Fase P4 — Consistencia del valor de `status`
# ---------------------------------------------------------------------------

def test_resolve_repo_root_is_lazy_when_not_overridden(monkeypatch, tmp_path):
    """Con REPO_ROOT=None, _resolve_repo_root() resuelve en vivo (no congela en
    import). Regresión: create-child-task fallaba con FILE_NOT_FOUND porque
    REPO_ROOT quedaba cacheado en import antes de activarse el proyecto."""
    import api.tickets as tickets_mod

    monkeypatch.setattr(tickets_mod, "REPO_ROOT", None)
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    assert tickets_mod._resolve_repo_root() == tmp_path.resolve()

    # Y si un test fija REPO_ROOT explícito, se respeta.
    other = tmp_path / "explicit"
    monkeypatch.setattr(tickets_mod, "REPO_ROOT", other)
    assert tickets_mod._resolve_repo_root() == other


def test_create_child_task_rejects_invalid_status(client, epic_ticket, tmp_repo):
    """status no canónico (ni alias legacy ni consumed) → 400 con mensaje claro."""
    pt_path = _write_pending_task(
        tmp_repo, epic_id="149", rf_id="RF-BADST",
        extra_fields={"status": "lo_que_sea"},
    )
    rel_path = _rel_path(tmp_repo, pt_path)

    resp = client.post(
        "/api/tickets/by-ado/149/create-child-task",
        json={"pending_task_path": rel_path},
    )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "PENDING_TASK_STATUS_INVALID"
    assert data["status_found"] == "lo_que_sea"
    assert "pending_manual_creation" in data["status_allowed"]


def test_create_child_task_accepts_legacy_pending_status(client, epic_ticket, tmp_repo):
    """El alias legacy status='pending' sigue siendo aceptado (no rompe en vuelo)."""
    pt_path = _write_pending_task(
        tmp_repo, epic_id="149", rf_id="RF-LEGACY",
        extra_fields={"status": "pending"},
    )
    rel_path = _rel_path(tmp_repo, pt_path)

    fake_ado = FakeAdoClientExt()
    with patch("api.tickets._ado_client_for_ticket", return_value=fake_ado):
        resp = client.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel_path},
        )

    # No debe rechazarse por status; procede a crear la Task.
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
