"""Tests del heartbeat_monitor + integración Caso C en recover_stale_running_tickets.

Cubre:
  - read_heartbeat con archivo ausente, válido, malformado.
  - is_execution_heartbeat_stale: período de gracia, heartbeat reciente,
    heartbeat viejo, ausencia tras gracia.
  - recover_stale_running_tickets: execution con heartbeat stale es marcada
    error con kind=heartbeat_timeout.
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

    # heartbeat_monitor importa default_runs_dir desde manifest_watcher
    import services.heartbeat_monitor as hm

    monkeypatch.setattr(hm, "default_runs_dir", _fake_default_runs_dir)
    return runs


def _write_hb(runs_dir: Path, execution_id: int, *, age_seconds: float, pid: int = 1234, phase: str = "running"):
    rd = runs_dir / str(execution_id)
    rd.mkdir(exist_ok=True)
    ts = (datetime.utcnow() - timedelta(seconds=age_seconds)).isoformat() + "Z"
    (rd / "heartbeat.json").write_text(
        json.dumps({"execution_id": execution_id, "last_activity_ts": ts, "pid": pid, "phase": phase}),
        encoding="utf-8",
    )


# ── read_heartbeat ───────────────────────────────────────────────────────────


def test_read_heartbeat_missing_file(runs_dir):
    from services.heartbeat_monitor import read_heartbeat

    status = read_heartbeat(99)
    assert status.exists is False
    assert status.last_activity_ts is None
    assert status.age_seconds is None


def test_read_heartbeat_valid(runs_dir):
    from services.heartbeat_monitor import read_heartbeat

    _write_hb(runs_dir, 1, age_seconds=5)
    status = read_heartbeat(1)
    assert status.exists is True
    assert status.pid == 1234
    assert status.phase == "running"
    assert status.age_seconds is not None and status.age_seconds >= 4


def test_read_heartbeat_malformed(runs_dir):
    from services.heartbeat_monitor import read_heartbeat

    rd = runs_dir / "2"
    rd.mkdir()
    (rd / "heartbeat.json").write_text("{not json", encoding="utf-8")
    status = read_heartbeat(2)
    # Malformed se trata igual que ausente
    assert status.exists is False


# ── is_execution_heartbeat_stale ─────────────────────────────────────────────


def test_stale_grace_period_no_heartbeat(runs_dir):
    from services.heartbeat_monitor import is_execution_heartbeat_stale

    started = datetime.utcnow() - timedelta(seconds=10)  # dentro del grace de 60s
    stale, status = is_execution_heartbeat_stale(50, started_at=started)
    assert stale is False
    assert status.exists is False


def test_stale_no_heartbeat_after_grace(runs_dir):
    from services.heartbeat_monitor import is_execution_heartbeat_stale

    started = datetime.utcnow() - timedelta(seconds=300)  # 5 min, > grace
    stale, status = is_execution_heartbeat_stale(51, started_at=started)
    assert stale is True
    assert status.exists is False


def test_stale_fresh_heartbeat(runs_dir):
    from services.heartbeat_monitor import is_execution_heartbeat_stale

    _write_hb(runs_dir, 52, age_seconds=30)
    started = datetime.utcnow() - timedelta(minutes=2)
    stale, status = is_execution_heartbeat_stale(52, started_at=started)
    assert stale is False
    assert status.exists is True


def test_stale_old_heartbeat(runs_dir):
    from services.heartbeat_monitor import is_execution_heartbeat_stale

    # heartbeat hace 20 min, threshold default 10 min
    _write_hb(runs_dir, 53, age_seconds=20 * 60)
    started = datetime.utcnow() - timedelta(minutes=30)
    stale, status = is_execution_heartbeat_stale(53, started_at=started)
    assert stale is True
    assert status.exists is True


def test_stale_respects_custom_timeout(runs_dir):
    from services.heartbeat_monitor import is_execution_heartbeat_stale

    _write_hb(runs_dir, 54, age_seconds=120)
    stale_strict, _ = is_execution_heartbeat_stale(
        54,
        started_at=datetime.utcnow() - timedelta(minutes=10),
        timeout_minutes=1,
    )
    stale_loose, _ = is_execution_heartbeat_stale(
        54,
        started_at=datetime.utcnow() - timedelta(minutes=10),
        timeout_minutes=10,
    )
    assert stale_strict is True
    assert stale_loose is False


# ── Integración con recover_stale_running_tickets (Caso C) ───────────────────


@pytest.fixture
def client(monkeypatch, runs_dir):
    """App test client con DB en memoria + runs_dir redirigido."""
    # Redirigir default_runs_dir también en ticket_status (importa heartbeat_monitor)
    import services.ticket_status as ts

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
            title=f"dummy-{ado_id}",
            ado_state="To Do",
            stacky_status=stacky_status,
        )
        session.add(t)
        session.flush()
        return t.id


def _mk_running_execution(ticket_id: int, *, started_minutes_ago: int = 5) -> int:
    """Execution en running con started_at fijo en el pasado."""
    from db import session_scope
    from models import AgentExecution

    started = datetime.utcnow() - timedelta(minutes=started_minutes_ago)
    with session_scope() as session:
        exec_ = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status="running",
            input_context_json="[]",
            started_by="test",
            started_at=started,
        )
        session.add(exec_)
        session.flush()
        return exec_.id


def test_reaper_closes_execution_with_stale_heartbeat(client, runs_dir):
    """Execution con heartbeat de hace 20min y status=running se marca error."""
    from services.ticket_status import recover_stale_running_tickets
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(ado_id=12001)
    exec_id = _mk_running_execution(ticket_id, started_minutes_ago=30)
    _write_hb(runs_dir, exec_id, age_seconds=20 * 60)

    details = recover_stale_running_tickets(trigger="hb_test")
    kinds = [d.get("kind") for d in details]
    assert "heartbeat_timeout" in kinds

    with session_scope() as session:
        exec_ = session.get(AgentExecution, exec_id)
        assert exec_.status == "error"
        assert "heartbeat" in (exec_.error_message or "").lower()


def test_reaper_ignores_execution_with_fresh_heartbeat(client, runs_dir):
    """Execution con heartbeat hace 30s no debe ser marcada error."""
    from services.ticket_status import recover_stale_running_tickets
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(ado_id=12002)
    exec_id = _mk_running_execution(ticket_id, started_minutes_ago=5)
    _write_hb(runs_dir, exec_id, age_seconds=30)

    details = recover_stale_running_tickets(trigger="hb_test")
    # Si hubo detalles, ninguno debería ser de esta execution con kind=heartbeat_timeout
    for d in details:
        assert not (d.get("execution_id") == exec_id and d.get("kind") == "heartbeat_timeout")

    with session_scope() as session:
        exec_ = session.get(AgentExecution, exec_id)
        assert exec_.status == "running"


def test_reaper_respects_startup_grace(client, runs_dir):
    """Execution recién creada sin heartbeat no debe ser marcada error por grace period."""
    from services.ticket_status import recover_stale_running_tickets
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(ado_id=12003)
    # Started 10 segundos atrás, sin heartbeat → dentro del grace
    exec_id = _mk_running_execution(ticket_id, started_minutes_ago=0)
    with session_scope() as session:
        e = session.get(AgentExecution, exec_id)
        e.started_at = datetime.utcnow() - timedelta(seconds=10)

    details = recover_stale_running_tickets(trigger="hb_test")
    for d in details:
        assert not (d.get("execution_id") == exec_id and d.get("kind") == "heartbeat_timeout")

    with session_scope() as session:
        exec_ = session.get(AgentExecution, exec_id)
        assert exec_.status == "running"
