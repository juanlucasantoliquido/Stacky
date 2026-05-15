"""Tests del ManifestWatcher.

Cubre:
  - Detección de manifest terminal cierra ejecuciones huérfanas en DB.
  - Idempotencia: si la ejecución ya está cerrada, el watcher no actúa.
  - Manifest malformado no rompe el ciclo del watcher.
  - Helper write_manifest produce un archivo válido y atómico.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def client():
    """Inicializa la app para que la DB tenga las tablas creadas."""
    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    # Apagar los daemons globales para que los tests usen sus propios watchers
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


def _mk_execution(ticket_id: int, status: str = "running") -> int:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        exec_ = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(exec_)
        session.flush()
        return exec_.id


# ── Detección de manifest terminal ────────────────────────────────────────────


def test_watcher_closes_orphan_completed_execution(client, tmp_path):
    from services.manifest_watcher import ManifestWatcher, write_manifest
    from services.ticket_status import get_current_status
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(ado_id=10001)
    exec_id = _mk_execution(ticket_id, status="running")

    run_dir = tmp_path / str(exec_id)
    write_manifest(
        run_dir,
        run_id=exec_id,
        agent_type="developer",
        status="completed",
        exit_code=0,
        signals={"work_completed": True},
    )

    watcher = ManifestWatcher(tmp_path, poll_interval=0.1)
    processed = watcher.scan_once()
    assert processed == 1

    # Execution cerrada en DB
    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        assert row.status == "completed"
        assert row.completed_at is not None

    # stacky_status del ticket también queda en completed via on_execution_end
    assert get_current_status(ticket_id) == "completed"


def test_watcher_propagates_error_manifest(client, tmp_path):
    from services.manifest_watcher import ManifestWatcher, write_manifest
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(ado_id=10002)
    exec_id = _mk_execution(ticket_id, status="running")

    run_dir = tmp_path / str(exec_id)
    write_manifest(
        run_dir,
        run_id=exec_id,
        agent_type="developer",
        status="error",
        exit_code=1,
        error_message="codex exited with code 1",
    )

    watcher = ManifestWatcher(tmp_path, poll_interval=0.1)
    assert watcher.scan_once() == 1

    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        assert row.status == "error"
        assert row.error_message == "codex exited with code 1"


# ── Idempotencia ──────────────────────────────────────────────────────────────


def test_watcher_skips_already_terminal_execution(client, tmp_path):
    """Si la execution ya está completed, el watcher no la toca ni dispara hooks."""
    from services.manifest_watcher import ManifestWatcher, write_manifest

    ticket_id = _mk_ticket(ado_id=10003, stacky_status="completed")
    exec_id = _mk_execution(ticket_id, status="completed")

    run_dir = tmp_path / str(exec_id)
    write_manifest(
        run_dir,
        run_id=exec_id,
        agent_type="developer",
        status="completed",
        exit_code=0,
    )

    watcher = ManifestWatcher(tmp_path, poll_interval=0.1)
    # Primera pasada: el manifest fue procesado (DB ya terminal → no actúa)
    # processed=0 porque no hubo cambio aplicado
    assert watcher.scan_once() == 0
    # Segunda pasada: en cache, no se re-parsea (también 0)
    assert watcher.scan_once() == 0


def test_watcher_double_scan_does_not_double_fire(client, tmp_path):
    """Después de cerrar la execution, una segunda scan no produce más eventos."""
    from services.manifest_watcher import ManifestWatcher, write_manifest
    from services.ticket_status import get_history

    ticket_id = _mk_ticket(ado_id=10004)
    exec_id = _mk_execution(ticket_id, status="running")

    run_dir = tmp_path / str(exec_id)
    write_manifest(run_dir, run_id=exec_id, agent_type="developer", status="completed")

    watcher = ManifestWatcher(tmp_path, poll_interval=0.1)
    assert watcher.scan_once() == 1
    history_after_first = len(get_history(ticket_id))
    assert watcher.scan_once() == 0
    assert len(get_history(ticket_id)) == history_after_first


# ── Robustez frente a manifests inválidos ────────────────────────────────────


def test_watcher_tolerates_malformed_manifest(client, tmp_path):
    from services.manifest_watcher import ManifestWatcher, MANIFEST_FILENAME

    ticket_id = _mk_ticket(ado_id=10005)
    exec_id = _mk_execution(ticket_id, status="running")

    run_dir = tmp_path / str(exec_id)
    run_dir.mkdir(parents=True)
    (run_dir / MANIFEST_FILENAME).write_text("{ this is not json ", encoding="utf-8")

    watcher = ManifestWatcher(tmp_path, poll_interval=0.1)
    # No debe lanzar
    assert watcher.scan_once() == 0


def test_watcher_ignores_non_terminal_status(client, tmp_path):
    """Manifest con status=running (intermedio) no debe disparar cierre."""
    from services.manifest_watcher import ManifestWatcher, write_manifest
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(ado_id=10006)
    exec_id = _mk_execution(ticket_id, status="running")

    run_dir = tmp_path / str(exec_id)
    write_manifest(run_dir, run_id=exec_id, agent_type="developer", status="running")

    watcher = ManifestWatcher(tmp_path, poll_interval=0.1)
    assert watcher.scan_once() == 0

    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        assert row.status == "running"  # sin cambios


# ── Helper write_manifest ────────────────────────────────────────────────────


def test_write_manifest_produces_valid_payload(tmp_path):
    from services.manifest_watcher import (
        MANIFEST_FILENAME,
        MANIFEST_SCHEMA_VERSION,
        write_manifest,
    )

    run_dir = tmp_path / "42"
    path = write_manifest(
        run_dir,
        run_id=42,
        agent_type="developer",
        status="completed",
        exit_code=0,
        artifacts=[{"path": "x.md", "kind": "output_md"}],
        signals={"work_completed": True},
    )

    assert path == run_dir / MANIFEST_FILENAME
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert data["run_id"] == 42
    assert data["status"] == "completed"
    assert data["exit_code"] == 0
    assert data["signals"]["work_completed"] is True
    assert data["artifacts"][0]["path"] == "x.md"
    # Escritura atómica: no quedó .tmp residual
    assert not (run_dir / "MANIFEST.json.tmp").exists()
