"""Tests del endpoint /api/diag/metrics y del helper append_event().

Cubre:
  - counters por status reflejan las executions en DB.
  - p50/p95/p99 de duration_ms en runs completados.
  - recovery counters parsean reasons de TicketStatusEvent.
  - currently_running + oldest_running_age_seconds.
  - append_event() genera líneas JSONL válidas y append-only.
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
def client(monkeypatch):
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


def _mk_ticket(ado_id: int) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="RSPacifico",
            title=f"t-{ado_id}",
            ado_state="To Do",
            stacky_status="idle",
        )
        session.add(t)
        session.flush()
        return t.id


def _mk_execution(ticket_id: int, *, status: str, duration_seconds: float | None = None,
                  started_minutes_ago: float = 5) -> int:
    from db import session_scope
    from models import AgentExecution

    started = datetime.utcnow() - timedelta(minutes=started_minutes_ago)
    completed = None
    if status in {"completed", "error", "cancelled"} and duration_seconds is not None:
        completed = started + timedelta(seconds=duration_seconds)
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


# ── Endpoint /api/diag/metrics ──────────────────────────────────────────────


def test_metrics_returns_status_counters(client):
    baseline = client.get("/api/diag/metrics").get_json()["executions_by_status"]
    base_running = baseline.get("running", 0)
    base_completed = baseline.get("completed", 0)
    base_error = baseline.get("error", 0)

    t = _mk_ticket(30001)
    _mk_execution(t, status="running")
    _mk_execution(t, status="completed", duration_seconds=10)
    _mk_execution(t, status="completed", duration_seconds=20)
    _mk_execution(t, status="error", duration_seconds=5)

    body = client.get("/api/diag/metrics").get_json()
    assert body["ok"] is True
    assert body["executions_by_status"]["running"] == base_running + 1
    assert body["executions_by_status"]["completed"] == base_completed + 2
    assert body["executions_by_status"]["error"] == base_error + 1


def test_metrics_computes_duration_percentiles(client):
    t = _mk_ticket(30002)
    # 10 runs con durations 1000ms..10000ms
    for sec in range(1, 11):
        _mk_execution(t, status="completed", duration_seconds=float(sec))

    body = client.get("/api/diag/metrics").get_json()
    d = body["duration_ms"]
    assert d["count"] >= 10
    assert d["p50"] is not None
    assert d["p95"] is not None
    assert d["p99"] is not None
    assert d["max"] >= d["p99"] >= d["p95"] >= d["p50"]


def test_metrics_returns_well_formed_payload_with_empty_baseline(client):
    """Estructura del payload + tipos correctos (no asume DB limpia)."""
    body = client.get("/api/diag/metrics").get_json()
    assert body["ok"] is True
    assert isinstance(body["executions_by_status"], dict)
    d = body["duration_ms"]
    assert "count" in d and "p50" in d and "p95" in d and "p99" in d
    assert isinstance(body["currently_running"], int)
    assert isinstance(body["recoveries"], dict)


def test_metrics_oldest_running_age(client):
    """Oldest_running_age_seconds refleja el ticket más viejo en running."""
    baseline = client.get("/api/diag/metrics").get_json()
    baseline_running = baseline["currently_running"]

    t = _mk_ticket(30003)
    _mk_execution(t, status="running", started_minutes_ago=15)
    _mk_execution(t, status="running", started_minutes_ago=2)

    body = client.get("/api/diag/metrics").get_json()
    assert body["currently_running"] == baseline_running + 2
    # El más viejo (entre los nuestros o los previos) tiene al menos 15 min
    assert body["oldest_running_age_seconds"] is not None
    assert body["oldest_running_age_seconds"] >= 14 * 60


def test_metrics_classifies_recovery_reasons(client):
    """Inserta TicketStatusEvent con distintos reasons; el endpoint los agrupa."""
    from db import session_scope
    from services.ticket_status import TicketStatusEvent

    t = _mk_ticket(30004)
    e = _mk_execution(t, status="error", duration_seconds=1)

    with session_scope() as session:
        for reason, label in [
            ("Heartbeat stale [reaper]: heartbeat stale (700s)", "heartbeat_timeout"),
            ("Execution timed out after 120 min [reaper]", "execution_timeout"),
            ("Last execution was already terminal", "execution_ended"),
            ("No executions found for ticket marked as running [startup]", "no_execution"),
        ]:
            session.add(TicketStatusEvent(
                ticket_id=t,
                execution_id=e,
                agent_type="developer",
                old_status="running",
                new_status="error",
                changed_by="system:reaper:test",
                reason=reason,
            ))

    body = client.get("/api/diag/metrics").get_json()
    r = body["recoveries"]
    assert r.get("heartbeat_timeout", 0) >= 1
    assert r.get("execution_timeout", 0) >= 1
    assert r.get("execution_ended", 0) >= 1
    assert r.get("no_execution", 0) >= 1


def test_metrics_includes_thresholds(client):
    body = client.get("/api/diag/metrics").get_json()
    th = body["thresholds"]
    assert "execution_timeout_minutes" in th
    assert "heartbeat_timeout_minutes" in th
    assert "startup_grace_seconds" in th


# ── Helper append_event ──────────────────────────────────────────────────────


def test_append_event_creates_valid_jsonl(tmp_path):
    from services.manifest_watcher import EVENTS_FILENAME, append_event

    run_dir = tmp_path / "42"
    append_event(run_dir, execution_id=42, event_type="started", payload={"pid": 1234})
    append_event(run_dir, execution_id=42, event_type="completed", payload={"exit_code": 0})

    path = run_dir / EVENTS_FILENAME
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    rec0 = json.loads(lines[0])
    rec1 = json.loads(lines[1])
    assert rec0["event_type"] == "started"
    assert rec0["payload"]["pid"] == 1234
    assert rec1["event_type"] == "completed"
    assert "ts" in rec0 and "ts" in rec1


def test_append_event_is_append_only(tmp_path):
    """Llamar 3 veces produce 3 líneas, no truncamiento."""
    from services.manifest_watcher import EVENTS_FILENAME, append_event

    run_dir = tmp_path / "99"
    for i in range(3):
        append_event(run_dir, execution_id=99, event_type=f"event_{i}", payload={"n": i})

    lines = (run_dir / EVENTS_FILENAME).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    for i, line in enumerate(lines):
        rec = json.loads(line)
        assert rec["event_type"] == f"event_{i}"
        assert rec["payload"]["n"] == i


def test_append_event_tolerates_missing_dir(tmp_path):
    """append_event crea el directorio si no existe."""
    from services.manifest_watcher import append_event

    run_dir = tmp_path / "new" / "deep" / "100"
    assert not run_dir.exists()
    append_event(run_dir, execution_id=100, event_type="x")
    assert (run_dir / "events.jsonl").is_file()
