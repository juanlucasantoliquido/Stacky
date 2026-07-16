"""Plan 127 F1 — Refactor extractivo build_diagnosis_snapshot() (api/diag.py).

Cubre: snapshot None si la ejecución no existe, keys completas del dict, y
que la route GET /api/diag/execution/<id> conserva exactamente su forma
(200 con las mismas keys, 404 con la forma exacta de antes del refactor).
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

_SNAPSHOT_KEYS = {
    "ok", "execution", "ticket", "manifest", "heartbeat",
    "recovery_history", "diagnosis", "recommended_action", "thresholds",
}


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
def client(runs_dir, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

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


def _mk_ticket(ado_id: int, stacky_status: str = "completed") -> int:
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
    return rd


def test_snapshot_none_si_no_existe(client):
    from api.diag import build_diagnosis_snapshot

    assert build_diagnosis_snapshot(999999) is None


def test_snapshot_keys_completas(client, runs_dir):
    tid = _mk_ticket(20101)
    eid = _mk_execution(tid, status="completed")
    _write_manifest(runs_dir, eid, status="completed")

    from api.diag import build_diagnosis_snapshot

    snapshot = build_diagnosis_snapshot(eid)
    assert snapshot is not None
    assert set(snapshot.keys()) == _SNAPSHOT_KEYS
    assert snapshot["ok"] is True
    assert snapshot["execution"]["id"] == eid


def test_route_intacta_200_y_404(client, runs_dir):
    tid = _mk_ticket(20102)
    eid = _mk_execution(tid, status="completed")
    _write_manifest(runs_dir, eid, status="completed")

    ok_resp = client.get(f"/api/diag/execution/{eid}")
    assert ok_resp.status_code == 200
    body = ok_resp.get_json()
    assert set(body.keys()) == _SNAPSHOT_KEYS

    missing_resp = client.get("/api/diag/execution/999999")
    assert missing_resp.status_code == 404
    assert missing_resp.get_json() == {
        "ok": False,
        "error": "execution_not_found",
        "execution_id": 999999,
    }
