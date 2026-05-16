"""Tests del manifest gate en POST /tickets/<id>/finish-work.

Cubre:
  - 409 cuando el MANIFEST de la última ejecución dice work_completed=false.
  - Bypass con force_finish=true.
  - dry_run=true bypassa el gate (permite preview).
  - Sin MANIFEST en disco → no aplica gate (sigue al flujo normal).
  - Sin last_exec → no aplica gate.
  - MANIFEST con work_completed=true → no bloquea.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    runs = tmp_path / "codex_runs"
    runs.mkdir()

    def _fake_default_runs_dir() -> Path:
        return runs

    import services.manifest_watcher as mw

    monkeypatch.setattr(mw, "default_runs_dir", _fake_default_runs_dir)
    return runs


@pytest.fixture
def client(monkeypatch, runs_dir):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    # Stub de ado_publisher para que finish-work no falle por publish.
    # Como el gate corre ANTES del publish, en los tests del gate no se llega.
    # Lo seteamos por las dudas para los tests positivos.
    import sys as _sys
    import types

    if "services.ado_publisher" not in _sys.modules:
        stub = types.ModuleType("services.ado_publisher")

        class _PublishResult:
            ok = True
            reason = None
            html_sha256 = "deadbeef"
            record_id = 1
            duplicate = False

        def publish_from_execution(*a, **kw):
            return _PublishResult()

        stub.publish_from_execution = publish_from_execution
        _sys.modules["services.ado_publisher"] = stub

    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def _mk_ticket(ado_id: int, stacky_status: str = "running") -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="RSPacifico",
            title=f"t-{ado_id}",
            ado_state="To Do",
            stacky_status=stacky_status,
        )
        session.add(t)
        session.flush()
        return t.id


def _mk_execution(ticket_id: int) -> int:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status="running",
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow() - timedelta(minutes=1),
        )
        session.add(e)
        session.flush()
        return e.id


def _write_manifest(runs_dir: Path, exec_id: int, *, work_completed: bool, status: str = "error"):
    rd = runs_dir / str(exec_id)
    rd.mkdir(exist_ok=True)
    (rd / "MANIFEST.json").write_text(
        json.dumps({
            "schema_version": "1",
            "run_id": exec_id,
            "agent_type": "developer",
            "status": status,
            "signals": {"work_completed": work_completed},
            "written_at": datetime.utcnow().isoformat() + "Z",
        }),
        encoding="utf-8",
    )


# ── 409 cuando MANIFEST dice no completado ───────────────────────────────────


def test_returns_409_when_manifest_says_work_not_completed(client, runs_dir):
    tid = _mk_ticket(40001)
    eid = _mk_execution(tid)
    _write_manifest(runs_dir, eid, work_completed=False)

    r = client.post(
        f"/api/tickets/{tid}/finish-work",
        json={"operator_reason": "cierre manual de prueba", "publish_to_ado": False},
    )
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "manifest_work_not_completed"
    assert body["manifest"]["execution_id"] == eid
    assert body["manifest"]["work_completed"] is False


# ── Bypass con force_finish ──────────────────────────────────────────────────


def test_force_finish_bypasses_manifest_gate(client, runs_dir):
    tid = _mk_ticket(40002)
    eid = _mk_execution(tid)
    _write_manifest(runs_dir, eid, work_completed=False)

    r = client.post(
        f"/api/tickets/{tid}/finish-work",
        json={
            "operator_reason": "override consciente del operador",
            "publish_to_ado": False,
            "force_finish": True,
        },
    )
    # Bypass: no debe ser 409 por el gate (puede fallar por otras razones, pero no por el gate)
    assert r.status_code != 409 or "manifest_work_not_completed" not in (r.get_json().get("error") or "")


# ── dry_run bypassa el gate ──────────────────────────────────────────────────


def test_dry_run_bypasses_manifest_gate(client, runs_dir):
    tid = _mk_ticket(40003)
    eid = _mk_execution(tid)
    _write_manifest(runs_dir, eid, work_completed=False)

    r = client.post(
        f"/api/tickets/{tid}/finish-work",
        json={
            "operator_reason": "preview de cierre",
            "publish_to_ado": False,
            "dry_run": True,
        },
    )
    assert r.status_code != 409 or "manifest_work_not_completed" not in (r.get_json().get("error") or "")


# ── Sin MANIFEST → no aplica gate ────────────────────────────────────────────


def test_no_manifest_skips_gate(client, runs_dir):
    tid = _mk_ticket(40004)
    _mk_execution(tid)  # ejecución sí, pero sin MANIFEST en disco

    r = client.post(
        f"/api/tickets/{tid}/finish-work",
        json={"operator_reason": "cierre normal", "publish_to_ado": False},
    )
    # El gate no aplica → no 409 por manifest_work_not_completed
    assert "manifest_work_not_completed" not in (r.get_json().get("error") or "")


# ── MANIFEST con work_completed=true → no bloquea ────────────────────────────


def test_manifest_with_work_completed_true_passes_gate(client, runs_dir):
    tid = _mk_ticket(40005)
    eid = _mk_execution(tid)
    _write_manifest(runs_dir, eid, work_completed=True, status="completed")

    r = client.post(
        f"/api/tickets/{tid}/finish-work",
        json={"operator_reason": "cierre tras run completado", "publish_to_ado": False},
    )
    assert "manifest_work_not_completed" not in (r.get_json().get("error") or "")


# ── Sin last_exec → no aplica gate ───────────────────────────────────────────


def test_no_last_execution_skips_gate(client, runs_dir):
    tid = _mk_ticket(40006)  # sin ejecuciones

    r = client.post(
        f"/api/tickets/{tid}/finish-work",
        json={"operator_reason": "cierre sin ejecución previa", "publish_to_ado": False},
    )
    assert "manifest_work_not_completed" not in (r.get_json().get("error") or "")
