"""Tests para el guardian de recovery de tickets stuck en stacky_status='running'.

Cubre:
  - Recovery cuando la última ejecución terminó (completed/error/cancelled).
  - Recovery cuando no existe ninguna ejecución (→ idle).
  - Detección de timeout: ejecución en 'running' por > EXECUTION_TIMEOUT_MINUTES.
  - Idempotencia: invocar dos veces no produce cambios extra.
  - Endpoint POST /api/tickets/recover-stale-status devuelve detalles.
  - schedule_stale_recovery() levanta un daemon que llama al recovery.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
# Timeout corto para que los tests de timeout sean rápidos
os.environ.setdefault("STACKY_EXECUTION_TIMEOUT_MINUTES", "30")


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    # create_app() arranca el guardian con intervalo default (120s). Para que
    # cada test arranque desde un estado limpio del scheduler, lo detenemos.
    from services.ticket_status import stop_stale_recovery
    stop_stale_recovery()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()


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


def _mk_execution(
    ticket_id: int,
    status: str,
    *,
    started_minutes_ago: int = 1,
    agent_type: str = "developer",
) -> int:
    """Crea una AgentExecution con started_at en el pasado controlado."""
    from db import session_scope
    from models import AgentExecution

    started_at = datetime.utcnow() - timedelta(minutes=started_minutes_ago)
    completed_at = (
        datetime.utcnow() if status in ("completed", "error", "cancelled") else None
    )
    with session_scope() as session:
        exec_ = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=started_at,
            completed_at=completed_at,
        )
        session.add(exec_)
        session.flush()
        return exec_.id


# ── Casos de recovery por estado de ejecución ──────────────────────────────────


def test_recovery_sync_running_to_completed(client):
    from services.ticket_status import (
        recover_stale_running_tickets,
        get_current_status,
    )

    ticket_id = _mk_ticket(ado_id=9001)
    _mk_execution(ticket_id, status="completed", started_minutes_ago=2)

    details = recover_stale_running_tickets(trigger="manual")

    assert len(details) == 1
    d = details[0]
    assert d["ticket_id"] == ticket_id
    assert d["ado_id"] == 9001
    assert d["old_status"] == "running"
    assert d["new_status"] == "completed"
    assert d["kind"] == "execution_ended"
    assert d["trigger"] == "manual"
    assert get_current_status(ticket_id) == "completed"


def test_recovery_running_without_execution_to_idle(client):
    from services.ticket_status import (
        recover_stale_running_tickets,
        get_current_status,
    )

    ticket_id = _mk_ticket(ado_id=9002)

    details = recover_stale_running_tickets(trigger="manual")
    assert len(details) == 1
    assert details[0]["new_status"] == "idle"
    assert details[0]["kind"] == "no_execution"
    assert get_current_status(ticket_id) == "idle"


def test_recovery_timeout_running_exec_to_error(client):
    """Ejecución en 'running' por más del timeout debe forzarse a 'error'."""
    from services.ticket_status import (
        recover_stale_running_tickets,
        get_current_status,
        EXECUTION_TIMEOUT_MINUTES,
    )
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(ado_id=9003)
    exec_id = _mk_execution(
        ticket_id,
        status="running",
        started_minutes_ago=EXECUTION_TIMEOUT_MINUTES + 10,
    )

    details = recover_stale_running_tickets(trigger="timeout_guardian")
    assert len(details) == 1
    d = details[0]
    assert d["kind"] == "execution_timeout"
    assert d["new_status"] == "error"
    assert d["trigger"] == "timeout_guardian"
    assert get_current_status(ticket_id) == "error"

    # La ejecución también queda cerrada como 'error'
    with session_scope() as session:
        exec_ = session.get(AgentExecution, exec_id)
        assert exec_.status == "error"
        assert exec_.completed_at is not None
        assert "timeout" in (exec_.error_message or "").lower()


def test_recovery_timeout_covers_open_chat_flow(client):
    """Fase P5: el reaper cubre el flujo open-chat (no sólo CLI).

    Una ejecución open-chat (agent_type='functional') no escribe MANIFEST ni
    heartbeat; igual debe cerrarse por timeout duro como red de seguridad cuando
    el output_watcher no llegó a cerrarla (artifacts incompletos)."""
    from services.ticket_status import (
        recover_stale_running_tickets,
        get_current_status,
        EXECUTION_TIMEOUT_MINUTES,
    )

    ticket_id = _mk_ticket(ado_id=9009)
    _mk_execution(
        ticket_id,
        status="running",
        started_minutes_ago=EXECUTION_TIMEOUT_MINUTES + 5,
        agent_type="functional",  # open-chat analyst — sin heartbeat/manifest
    )

    details = recover_stale_running_tickets(trigger="timeout_guardian")
    assert len(details) == 1
    assert details[0]["kind"] == "execution_timeout"
    assert details[0]["agent_type"] == "functional"
    assert get_current_status(ticket_id) == "error"


def test_recovery_running_exec_within_timeout_is_left_alone(client):
    """Ejecución en 'running' pero dentro del timeout NO se debe tocar."""
    from services.ticket_status import (
        recover_stale_running_tickets,
        get_current_status,
    )

    ticket_id = _mk_ticket(ado_id=9004)
    _mk_execution(ticket_id, status="running", started_minutes_ago=2)

    details = recover_stale_running_tickets(trigger="manual")
    assert details == []
    assert get_current_status(ticket_id) == "running"


# ── Idempotencia ──────────────────────────────────────────────────────────────


def test_recovery_is_idempotent(client):
    """Ejecutar recovery dos veces seguidas no produce cambios el segundo run."""
    from services.ticket_status import recover_stale_running_tickets

    ticket_id = _mk_ticket(ado_id=9005)
    _mk_execution(ticket_id, status="completed")

    first = recover_stale_running_tickets(trigger="manual")
    second = recover_stale_running_tickets(trigger="manual")
    assert len(first) == 1
    assert second == []


# ── Endpoint HTTP ─────────────────────────────────────────────────────────────


def test_endpoint_recover_stale_status_returns_details(client):
    ticket_id = _mk_ticket(ado_id=9006)
    _mk_execution(ticket_id, status="error")

    r = client.post("/api/tickets/recover-stale-status")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["count"] == 1
    assert body["fixed"] == 1  # alias para compat
    assert body["trigger"] == "manual"
    assert len(body["details"]) == 1
    d = body["details"][0]
    assert d["ticket_id"] == ticket_id
    assert d["ado_id"] == 9006
    assert d["new_status"] == "error"


# ── Guardian periódico ───────────────────────────────────────────────────────


def test_schedule_stale_recovery_runs_periodically(client):
    """El guardian debe llamar a recovery automáticamente cada interval."""
    from services.ticket_status import (
        schedule_stale_recovery,
        stop_stale_recovery,
        get_current_status,
    )

    ticket_id = _mk_ticket(ado_id=9007)
    _mk_execution(ticket_id, status="completed")

    # Intervalo agresivo (1 segundo) para que el test no espere
    thread = schedule_stale_recovery(interval_seconds=1)
    try:
        assert thread.is_alive()
        # Esperar a 2 ciclos del guardian
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if get_current_status(ticket_id) == "completed":
                break
            time.sleep(0.2)
        assert get_current_status(ticket_id) == "completed"
    finally:
        stop_stale_recovery()


def test_schedule_stale_recovery_is_idempotent(client):
    """Llamar schedule_stale_recovery dos veces no crea threads duplicados."""
    from services.ticket_status import (
        schedule_stale_recovery,
        stop_stale_recovery,
    )

    t1 = schedule_stale_recovery(interval_seconds=2)
    t2 = schedule_stale_recovery(interval_seconds=2)
    try:
        assert t1 is t2
    finally:
        stop_stale_recovery()
