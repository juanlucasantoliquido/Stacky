"""Tests del endpoint GET /api/diag/execution/<id>.

Cubre cada categoría de diagnosis devuelta por _diagnose():
  - terminal_clean / terminal_no_manifest
  - alive
  - starting
  - manifest_orphan
  - heartbeat_stale_no_manifest
  - no_heartbeat_after_grace
Más:
  - 404 cuando execution_id no existe.
  - El payload incluye history, thresholds y todos los bloques esperados.
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

    def _fake_runs_dir() -> Path:
        return runs

    import services.heartbeat_monitor as hm
    import services.manifest_watcher as mw
    import api.diag as diag

    monkeypatch.setattr(hm, "default_runs_dir", _fake_runs_dir)
    monkeypatch.setattr(mw, "default_runs_dir", _fake_runs_dir)
    monkeypatch.setattr(diag, "default_runs_dir", _fake_runs_dir)
    return runs


@pytest.fixture
def client(runs_dir):
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


# ── Helpers ──────────────────────────────────────────────────────────────────


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


def _mk_execution(ticket_id: int, *, status: str, started_minutes_ago: int = 5) -> int:
    from db import session_scope
    from models import AgentExecution

    started = datetime.utcnow() - timedelta(minutes=started_minutes_ago)
    completed = datetime.utcnow() if status in {"completed", "error", "cancelled"} else None
    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=started,
            completed_at=completed,
        )
        session.add(e)
        session.flush()
        return e.id


def _write_manifest(runs_dir: Path, exec_id: int, *, status: str = "completed"):
    rd = runs_dir / str(exec_id)
    rd.mkdir(exist_ok=True)
    (rd / "MANIFEST.json").write_text(
        json.dumps({
            "schema_version": "1",
            "run_id": exec_id,
            "agent_type": "developer",
            "status": status,
            "signals": {"work_completed": status == "completed"},
            "written_at": datetime.utcnow().isoformat() + "Z",
        }),
        encoding="utf-8",
    )


def _write_heartbeat(runs_dir: Path, exec_id: int, *, age_seconds: float):
    rd = runs_dir / str(exec_id)
    rd.mkdir(exist_ok=True)
    ts = (datetime.utcnow() - timedelta(seconds=age_seconds)).isoformat() + "Z"
    (rd / "heartbeat.json").write_text(
        json.dumps({"execution_id": exec_id, "last_activity_ts": ts, "pid": 1, "phase": "running"}),
        encoding="utf-8",
    )


# ── Tests ────────────────────────────────────────────────────────────────────


def test_returns_404_when_execution_missing(client):
    r = client.get("/api/diag/execution/99999")
    assert r.status_code == 404
    assert r.get_json()["error"] == "execution_not_found"


def test_terminal_clean_diagnosis(client, runs_dir):
    tid = _mk_ticket(20001, stacky_status="completed")
    eid = _mk_execution(tid, status="completed")
    _write_manifest(runs_dir, eid, status="completed")

    body = client.get(f"/api/diag/execution/{eid}").get_json()
    assert body["ok"] is True
    assert body["diagnosis"] == "terminal_clean"
    assert body["execution"]["status"] == "completed"
    assert body["manifest"]["status"] == "completed"
    assert body["heartbeat"]["exists"] is False
    assert "thresholds" in body


def test_terminal_no_manifest_diagnosis(client, runs_dir):
    tid = _mk_ticket(20002, stacky_status="completed")
    eid = _mk_execution(tid, status="completed")
    # Sin MANIFEST en disco
    body = client.get(f"/api/diag/execution/{eid}").get_json()
    assert body["diagnosis"] == "terminal_no_manifest"


def test_alive_diagnosis(client, runs_dir):
    tid = _mk_ticket(20003)
    eid = _mk_execution(tid, status="running", started_minutes_ago=3)
    _write_heartbeat(runs_dir, eid, age_seconds=20)

    body = client.get(f"/api/diag/execution/{eid}").get_json()
    assert body["diagnosis"] == "alive"


def test_starting_diagnosis_in_grace_period(client, runs_dir):
    tid = _mk_ticket(20004)
    # started_at hace 10 segundos, sin heartbeat → dentro del grace
    eid = _mk_execution(tid, status="running")
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        e = session.get(AgentExecution, eid)
        e.started_at = datetime.utcnow() - timedelta(seconds=10)

    body = client.get(f"/api/diag/execution/{eid}").get_json()
    assert body["diagnosis"] == "starting"


def test_manifest_orphan_diagnosis(client, runs_dir):
    """DB todavía running pero MANIFEST terminal — el watcher debería haber actuado."""
    tid = _mk_ticket(20005)
    eid = _mk_execution(tid, status="running", started_minutes_ago=2)
    _write_manifest(runs_dir, eid, status="completed")

    body = client.get(f"/api/diag/execution/{eid}").get_json()
    assert body["diagnosis"] == "manifest_orphan"
    assert "recover-stale-status" in (body["recommended_action"] or "")


def test_heartbeat_stale_no_manifest_diagnosis(client, runs_dir):
    tid = _mk_ticket(20006)
    eid = _mk_execution(tid, status="running", started_minutes_ago=30)
    _write_heartbeat(runs_dir, eid, age_seconds=20 * 60)  # 20 min, > timeout

    body = client.get(f"/api/diag/execution/{eid}").get_json()
    assert body["diagnosis"] == "heartbeat_stale_no_manifest"
    assert body["heartbeat"]["exists"] is True


def test_no_heartbeat_after_grace_diagnosis(client, runs_dir):
    tid = _mk_ticket(20007)
    eid = _mk_execution(tid, status="running", started_minutes_ago=10)
    # Sin heartbeat ni manifest, started_at viejo → grace expiró

    body = client.get(f"/api/diag/execution/{eid}").get_json()
    assert body["diagnosis"] == "no_heartbeat_after_grace"


def test_payload_includes_recovery_history(client, runs_dir):
    """Si hay TicketStatusEvent vinculados a la execution, vienen en history."""
    from db import session_scope
    from services.ticket_status import TicketStatusEvent

    tid = _mk_ticket(20008)
    eid = _mk_execution(tid, status="error", started_minutes_ago=5)

    with session_scope() as session:
        ev = TicketStatusEvent(
            ticket_id=tid,
            execution_id=eid,
            agent_type="developer",
            old_status="running",
            new_status="error",
            changed_by="system:reaper:hb",
            reason="heartbeat_stale",
        )
        session.add(ev)

    body = client.get(f"/api/diag/execution/{eid}").get_json()
    assert len(body["recovery_history"]) == 1
    assert body["recovery_history"][0]["new_status"] == "error"
    assert body["recovery_history"][0]["changed_by"].startswith("system:reaper")
