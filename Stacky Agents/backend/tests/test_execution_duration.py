"""Plan 39 A0 — duration_ms en to_dict() de AgentExecution.

Confirma que el campo ya existe (implementado previamente en models.py).
No usa create_app() para evitar la migración startup_sync que puede
causar colisiones de UNIQUE constraint en tests con DB compartida.

1. test_duration_computed_when_finished — started + 5s después completed → duration_ms ≈ 5000
2. test_duration_none_when_running — sin completed_at → duration_ms is None
3. test_existing_fields_unchanged — to_dict() sigue teniendo status, agent_type, metadata
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Inicializar la DB antes de importar modelos
from db import init_db  # noqa: E402
init_db()


_DUR_ADO_BASE = 997_000  # rango reservado para este módulo
_dur_counter = 0


def _seed_exec(*, started_at: datetime, completed_at: datetime | None, status: str = "running") -> dict:
    """Crea y persiste un AgentExecution con fechas dadas. Retorna el dict."""
    global _dur_counter
    _dur_counter += 1
    ado_id = _DUR_ADO_BASE + _dur_counter

    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="durtest",
            stacky_project_name="durtest",
            title=f"dur-ticket-{ado_id}",
            ado_state="Active",
        )
        session.add(t)
        session.flush()

        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=started_at,
            completed_at=completed_at,
        )
        session.add(e)
        session.flush()
        return e.to_dict()


# ---------------------------------------------------------------------------
# 1. duration_ms cuando hay completed_at
# ---------------------------------------------------------------------------

def test_duration_computed_when_finished():
    started = datetime(2026, 1, 1, 12, 0, 0)
    finished = started + timedelta(seconds=5)
    d = _seed_exec(started_at=started, completed_at=finished, status="completed")

    assert d["duration_ms"] is not None
    assert abs(d["duration_ms"] - 5000) < 10  # tolerancia 10ms


# ---------------------------------------------------------------------------
# 2. duration_ms None cuando sigue corriendo
# ---------------------------------------------------------------------------

def test_duration_none_when_running():
    started = datetime(2026, 1, 1, 13, 0, 0)
    d = _seed_exec(started_at=started, completed_at=None, status="running")

    assert d["duration_ms"] is None


# ---------------------------------------------------------------------------
# 3. to_dict() sigue teniendo campos clave
# ---------------------------------------------------------------------------

def test_existing_fields_unchanged():
    started = datetime(2026, 1, 1, 14, 0, 0)
    d = _seed_exec(started_at=started, completed_at=None, status="running")

    assert "status" in d
    assert "agent_type" in d
    assert "metadata" in d
    assert d["agent_type"] == "developer"
