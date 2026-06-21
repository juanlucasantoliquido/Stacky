"""Plan 61 F2+F3+F4 — Integración del Task Gate en create_child_task.

8 tests:
  TG-01  Gate OFF → respuesta sin clave task_gate (byte-identical)
  TG-02  Gate ON, payload limpio → task_gate.decision=="pass", 200
  TG-03  Gate ON, defecto reparable → task_gate en respuesta, task creada (no bloquea)
  TG-04  Gate ON + blocking, needs_review → 400 TASK_GATE_BLOCKED, sin calls ADO
  TG-05  Gate ON + blocking + dry_run → 200 (sin 400), task_gate en respuesta
  TG-06  Gate ON, plan file inexistente → plan_de_pruebas_empty en defectos
  TG-07  Gate ON, éxito → task_gate incluido en la respuesta de éxito (F3 audit)
  TG-08  Gate OFF → spy confirma que evaluate_task_gate NO fue llamado (F4)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── Fixtures mínimas (independientes del test_create_child_task_endpoint.py) ─


@pytest.fixture(scope="session")
def flask_app_gate():
    os.environ["STACKY_OUTPUT_WATCHER_ENABLED"] = "false"
    os.environ["STACKY_MANIFEST_WATCHER_ENABLED"] = "false"
    import app as app_module
    app_module._startup_sync = lambda logger: None
    application = app_module.create_app()
    application.config["TESTING"] = True
    try:
        from services.ticket_status import stop_stale_recovery
        stop_stale_recovery()
    except Exception:
        pass
    return application


@pytest.fixture(scope="session", autouse=True)
def init_db_gate(flask_app_gate):
    from db import Base, engine
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client_gate(flask_app_gate):
    with flask_app_gate.test_client() as c:
        yield c


@pytest.fixture
def tmp_repo_gate(monkeypatch, tmp_path):
    import api.tickets as tickets_mod
    monkeypatch.setattr(tickets_mod, "REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def epic_149(flask_app_gate):
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        if not session.query(Ticket).filter(Ticket.ado_id == 149).first():
            session.add(Ticket(
                ado_id=149, project="TestProject",
                title="Epic 149 — Gate Test", work_item_type="epic", ado_state="Active",
            ))
    return 149


# ── Fake ADO minimal ────────────────────────────────────────────────────────


class _FakeAdo:
    def __init__(self):
        self.create_calls: list = []
        self._next_id = 6000
        self._created: dict[int, int | None] = {}  # ado_id → parent_ado_id

    def create_work_item(self, work_item_type, title="", description="",
                         initial_state="", parent_id=None, fields=None, parent_ado_id=None):
        eid = self._next_id
        self._next_id += 1
        effective_parent = parent_ado_id if parent_ado_id is not None else parent_id
        self.create_calls.append(work_item_type)
        self._created[eid] = effective_parent
        return {"id": eid, "url": f"https://dev.azure.com/org/proj/_apis/wit/workitems/{eid}"}

    def upload_attachment(self, *a, **kw):
        return {"id": "fake-attach"}

    def link_attachment_to_work_item(self, *a, **kw):
        return {}

    def post_comment(self, *a, **kw):
        return {}

    def get_work_item(self, ado_id: int, fields=None):
        parent = self._created.get(ado_id)
        return {
            "id": ado_id,
            "fields": {
                "System.Rev": 1,
                "System.AreaPath": "Proj",
                "System.Title": "Task",
                "System.WorkItemType": "Task",
                "System.Parent": parent,
            },
        }

    def work_item_url(self, ado_id: int) -> str:
        return f"https://dev.azure.com/org/proj/_workitems/edit/{ado_id}"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_pt(base: Path, rf_id="RF-001", epic_id="149", extra: dict | None = None) -> tuple[Path, str]:
    """Escribe pending-task.json con descripción que incluye rf_id (clean default)."""
    folder = base / "Agentes" / "outputs" / f"epic-{epic_id}" / f"{rf_id}-slug"
    folder.mkdir(parents=True, exist_ok=True)
    plan_rel = f"Agentes/outputs/epic-{epic_id}/{rf_id}-slug/plan-de-pruebas.md"
    (base / plan_rel).write_text(f"# Pruebas {rf_id}\nContenido.", encoding="utf-8")
    payload = {
        "generated_at": "2026-06-21T00:00:00Z",
        "generated_by": "stacky",
        "epic_id": epic_id,
        "rf_id": rf_id,
        "title": f"{rf_id} — Título de tarea",
        "description_html": f"<p>{rf_id} Descripción de la tarea.</p>",
        "plan_de_pruebas_path": plan_rel,
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
        "status": "pending_manual_creation",
    }
    if extra:
        payload.update(extra)
    pt_path = folder / "pending-task.json"
    pt_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    rel = str(pt_path.relative_to(base)).replace("\\", "/")
    return pt_path, rel


# ── TG-01: Gate OFF → sin clave task_gate ────────────────────────────────────


def test_gate_off_response_has_no_task_gate_key(client_gate, epic_149, tmp_repo_gate, monkeypatch):
    monkeypatch.delenv("STACKY_TASK_GATE_ENABLED", raising=False)
    _, rel = _write_pt(tmp_repo_gate)
    with patch("api.tickets._ado_client_for_ticket", return_value=_FakeAdo()):
        resp = client_gate.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "task_gate" not in data


# ── TG-02: Gate ON, payload limpio → decision==pass ─────────────────────────


def test_gate_on_clean_payload_decision_pass(client_gate, epic_149, tmp_repo_gate, monkeypatch):
    monkeypatch.setenv("STACKY_TASK_GATE_ENABLED", "true")
    monkeypatch.delenv("STACKY_TASK_GATE_BLOCKING", raising=False)
    _, rel = _write_pt(tmp_repo_gate, rf_id="RF-002")
    with patch("api.tickets._ado_client_for_ticket", return_value=_FakeAdo()):
        resp = client_gate.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "task_gate" in data
    assert data["task_gate"]["decision"] == "pass"
    assert data["task_gate"]["defects"] == []
    assert data["ok"] is True


# ── TG-03: Gate ON, defecto reparable → avisa pero NO bloquea ───────────────


def test_gate_on_repair_defect_does_not_block(client_gate, epic_149, tmp_repo_gate, monkeypatch):
    monkeypatch.setenv("STACKY_TASK_GATE_ENABLED", "true")
    monkeypatch.delenv("STACKY_TASK_GATE_BLOCKING", raising=False)
    # description_empty → REPAIR, no bloquea
    _, rel = _write_pt(tmp_repo_gate, rf_id="RF-003", extra={"description_html": ""})
    with patch("api.tickets._ado_client_for_ticket", return_value=_FakeAdo()):
        resp = client_gate.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "task_gate" in data
    assert data["task_gate"]["decision"] == "repair"
    assert "description_empty" in data["task_gate"]["defects"]
    assert data["task_gate"]["blocking"] is False


# ── TG-04: Gate ON + blocking + needs_review → 400 ──────────────────────────


def test_gate_blocking_rejects_needs_review(client_gate, epic_149, tmp_repo_gate, monkeypatch):
    monkeypatch.setenv("STACKY_TASK_GATE_ENABLED", "true")
    monkeypatch.setenv("STACKY_TASK_GATE_BLOCKING", "true")
    fake = _FakeAdo()
    # rf_id vacío → needs_review
    _, rel = _write_pt(tmp_repo_gate, rf_id="RF-004", extra={"rf_id": ""})
    with patch("api.tickets._ado_client_for_ticket", return_value=fake):
        resp = client_gate.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel},
        )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "TASK_GATE_BLOCKED"
    assert "task_gate" in data
    assert "rf_id_empty" in data["task_gate"]["defects"]
    # Sin llamadas ADO
    assert fake.create_calls == []


# ── TG-05: Gate ON + blocking + dry_run → no 400, task_gate incluido ────────


def test_gate_blocking_dry_run_no_400(client_gate, epic_149, tmp_repo_gate, monkeypatch):
    monkeypatch.setenv("STACKY_TASK_GATE_ENABLED", "true")
    monkeypatch.setenv("STACKY_TASK_GATE_BLOCKING", "true")
    # rf_id vacío → needs_review → blocking=True, pero dry_run omite el 400
    _, rel = _write_pt(tmp_repo_gate, rf_id="RF-005", extra={"rf_id": ""})
    with patch("api.tickets._ado_client_for_ticket", return_value=_FakeAdo()):
        resp = client_gate.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel, "dry_run": True},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("dry_run") is True
    assert "task_gate" in data
    assert data["task_gate"]["blocking"] is True
    assert "rf_id_empty" in data["task_gate"]["defects"]


# ── TG-06: plan file inexistente → plan_de_pruebas_empty ────────────────────


def test_gate_plan_file_missing_emits_defect(client_gate, epic_149, tmp_repo_gate, monkeypatch):
    monkeypatch.setenv("STACKY_TASK_GATE_ENABLED", "true")
    monkeypatch.delenv("STACKY_TASK_GATE_BLOCKING", raising=False)
    # plan_de_pruebas_path apunta a un archivo que NO existe
    _, rel = _write_pt(tmp_repo_gate, rf_id="RF-006", extra={
        "plan_de_pruebas_path": "Agentes/outputs/epic-149/RF-006-slug/no-existe.md"
    })
    with patch("api.tickets._ado_client_for_ticket", return_value=_FakeAdo()):
        resp = client_gate.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "task_gate" in data
    assert "plan_de_pruebas_empty" in data["task_gate"]["defects"]


# ── TG-07: éxito → task_gate en respuesta de éxito (F3 audit) ───────────────


def test_gate_verdict_present_in_success_response(client_gate, epic_149, tmp_repo_gate, monkeypatch):
    monkeypatch.setenv("STACKY_TASK_GATE_ENABLED", "true")
    monkeypatch.delenv("STACKY_TASK_GATE_BLOCKING", raising=False)
    _, rel = _write_pt(tmp_repo_gate, rf_id="RF-007")
    with patch("api.tickets._ado_client_for_ticket", return_value=_FakeAdo()):
        resp = client_gate.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "task_gate" in data
    tg = data["task_gate"]
    assert "decision" in tg and "defects" in tg and "blocking" in tg


# ── TG-08: Gate OFF → evaluate_task_gate NO es llamado (F4 anti-regresión) ──


def test_evaluate_task_gate_not_called_when_flag_off(client_gate, epic_149, tmp_repo_gate, monkeypatch):
    monkeypatch.delenv("STACKY_TASK_GATE_ENABLED", raising=False)
    from harness import task_gate as tg_mod
    mock_fn = MagicMock(side_effect=AssertionError("no debería llamarse"))
    _, rel = _write_pt(tmp_repo_gate, rf_id="RF-008")
    with patch.object(tg_mod, "evaluate_task_gate", mock_fn), \
         patch("api.tickets._ado_client_for_ticket", return_value=_FakeAdo()):
        resp = client_gate.post(
            "/api/tickets/by-ado/149/create-child-task",
            json={"pending_task_path": rel},
        )
    assert resp.status_code == 200
    mock_fn.assert_not_called()
