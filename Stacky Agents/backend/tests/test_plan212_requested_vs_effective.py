"""Plan 212 F7 — La degradación deja rastro: solicitado vs efectivo.

El bug original era invisible: el operador elegía Opus, corría Sonnet, y nada en
la ejecución lo decía. Acá se verifica que el par quede persistido y legible.
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

from services.claude_code_cli_runner import (  # noqa: E402
    _persist_model_effort_trace,
    build_model_effort_trace,
)


def test_metadata_records_no_downgrade_when_honored():
    """Post-F1: elegir Opus y correr Opus no es una degradación."""
    trace = build_model_effort_trace(
        requested_model="claude-opus-4-8", effective_model="claude-opus-4-8",
        requested_effort="xhigh", effective_effort="xhigh", reason="user-override",
    )

    assert trace["downgraded"] is False
    assert trace["effective_model"] == "claude-opus-4-8"


def test_metadata_records_downgrade_for_effort():
    trace = build_model_effort_trace(
        requested_model="claude-sonnet-5", effective_model="claude-sonnet-5",
        requested_effort="xhigh", effective_effort="high", reason="user-override",
    )

    assert trace["downgraded"] is True
    assert trace["effective_effort"] == "high"


def test_metadata_records_downgrade_for_model():
    trace = build_model_effort_trace(
        requested_model="claude-opus-4-7", effective_model="claude-sonnet-5",
        requested_effort="", effective_effort="high",
        reason="user-override claude-opus-4-7 -> clamp §5.2 (claude-sonnet-5)",
    )

    assert trace["downgraded"] is True
    assert "clamp" in trace["reason"]


def test_router_choice_without_request_is_not_a_downgrade():
    """Si el operador no eligió modelo, que el router elija es su trabajo."""
    trace = build_model_effort_trace(
        requested_model=None, effective_model="claude-sonnet-5",
        requested_effort=None, effective_effort="medium", reason="heuristica",
    )

    assert trace["downgraded"] is False


@pytest.fixture
def execution_id():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        t = Ticket(ado_id=21270, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        ex = AgentExecution(
            ticket_id=t.id, agent_type="developer", status="running",
            input_context_json="{}", started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(ex)
        session.flush()
        return ex.id


def test_metadata_is_valid_json_string(execution_id):
    """metadata_json es una columna Text: un dict crudo sería feature muerta."""
    from db import session_scope
    from models import AgentExecution

    trace = build_model_effort_trace(
        requested_model="claude-opus-4-8", effective_model="claude-sonnet-5",
        requested_effort="max", effective_effort="max", reason="clamp",
    )
    _persist_model_effort_trace(execution_id, trace)

    with session_scope() as session:
        ex = session.query(AgentExecution).filter_by(id=execution_id).first()
        crudo = ex.metadata_json

    assert isinstance(crudo, str), "se guardó un objeto, no JSON serializado"
    assert json.loads(crudo)["model_effort"]["downgraded"] is True


def test_persist_preserves_other_metadata_keys(execution_id):
    """Otros escritores de metadata no pueden perder su contenido."""
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        ex = session.query(AgentExecution).filter_by(id=execution_id).first()
        ex.metadata_json = json.dumps({"completion_gateway": {"reason": "ok"}})

    _persist_model_effort_trace(execution_id, build_model_effort_trace(
        requested_model=None, effective_model="claude-sonnet-5",
        requested_effort=None, effective_effort=None,
    ))

    with session_scope() as session:
        ex = session.query(AgentExecution).filter_by(id=execution_id).first()
        meta = json.loads(ex.metadata_json)

    assert meta["completion_gateway"]["reason"] == "ok"
    assert "model_effort" in meta


def test_persist_never_raises_for_unknown_execution():
    """Es informativo: no puede tumbar un run por una fila que no está."""
    _persist_model_effort_trace(999_999, build_model_effort_trace(
        requested_model=None, effective_model=None,
        requested_effort=None, effective_effort=None,
    ))
