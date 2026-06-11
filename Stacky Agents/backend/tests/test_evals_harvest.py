"""H6.1 — Tests del subcomando `python -m evals harvest`.

Verifica:
1. Execution completed con output válido → golden escrito en evals/agents/<type>/<name>.json
2. Execution no existente → error descriptivo (no traza)
3. Execution no completed (status != completed) → error descriptivo
4. --name se usa como nombre del archivo; si se omite, usa execution_<id>
5. El score del golden es el floor del score actual del contract_validator
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


@pytest.fixture(autouse=True)
def _db_ready():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()
    yield


def _mk_ticket(ado_id: int = 9001) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="TestProject", title="t-test",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _mk_execution(ticket_id: int, *, status: str, agent_type: str, output: str | None) -> int:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
            output=output,
        )
        session.add(e)
        session.flush()
        return e.id


# Output que pasa el contrato de qa (tiene VERDICT + PASS + suficientes palabras)
QA_OUTPUT = (
    "## Verdict\n\nVERDICT: PASS\n\n"
    "Se ejecutó la suite completa. Todos los casos críticos pasaron. "
    "Validados escenarios de borde. La cobertura es completa. "
    "No se detectaron regresiones. Se recomienda promover a UAT. "
    "Resultados de qa confirmados sin issues pendientes."
)


def test_harvest_creates_golden_file(tmp_path):
    """Execution completed → golden JSON escrito con score y formato correcto."""
    from evals import harvest

    tid = _mk_ticket()
    eid = _mk_execution(tid, status="completed", agent_type="qa", output=QA_OUTPUT)

    golden_dir = tmp_path / "evals" / "agents"
    harvest.harvest(execution_id=eid, name="qa_harvest_test", agents_dir=golden_dir)

    out_file = golden_dir / "qa" / "qa_harvest_test.json"
    assert out_file.exists(), "El archivo golden no fue creado"

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["name"] == "qa_harvest_test"
    assert data["agent_type"] == "qa"
    assert "output" in data
    assert "expect" in data
    assert "min_score" in data["expect"]
    assert isinstance(data["expect"]["min_score"], int)
    assert data["expect"]["must_pass"] is True
    # Score debe ser un entero ≥ 0
    assert data["expect"]["min_score"] >= 0


def test_harvest_default_name(tmp_path):
    """Si --name se omite, el nombre del golden es execution_<id>."""
    from evals import harvest

    tid = _mk_ticket(ado_id=9002)
    eid = _mk_execution(tid, status="completed", agent_type="qa", output=QA_OUTPUT)

    golden_dir = tmp_path / "evals" / "agents"
    harvest.harvest(execution_id=eid, name=None, agents_dir=golden_dir)

    expected_name = f"execution_{eid}"
    out_file = golden_dir / "qa" / f"{expected_name}.json"
    assert out_file.exists()

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["name"] == expected_name


def test_harvest_nonexistent_execution_raises(tmp_path):
    """Execution inexistente → HarvestError con mensaje claro."""
    from evals import harvest

    golden_dir = tmp_path / "evals" / "agents"
    with pytest.raises(harvest.HarvestError, match="no encontrada|not found"):
        harvest.harvest(execution_id=99999, name="x", agents_dir=golden_dir)


def test_harvest_not_completed_raises(tmp_path):
    """Execution con status != completed → HarvestError con mensaje claro."""
    from evals import harvest

    tid = _mk_ticket(ado_id=9003)
    eid = _mk_execution(tid, status="running", agent_type="qa", output=QA_OUTPUT)

    golden_dir = tmp_path / "evals" / "agents"
    with pytest.raises(harvest.HarvestError, match="completed"):
        harvest.harvest(execution_id=eid, name="x", agents_dir=golden_dir)


def test_harvest_applies_pii_mask(tmp_path):
    """El output con PII debe quedar enmascarado en el golden."""
    from evals import harvest

    output_with_pii = (
        "## Verdict\n\nVERDICT: PASS\n\n"
        "El cliente con DNI 12345678 y email test@example.com superó la validación. "
        "Todos los casos pasaron sin errores. La cobertura es total. "
        "No se detectaron regresiones. Se recomienda promover a UAT. "
        "PASS verificado por QA automatizado."
    )

    tid = _mk_ticket(ado_id=9004)
    eid = _mk_execution(tid, status="completed", agent_type="qa", output=output_with_pii)

    golden_dir = tmp_path / "evals" / "agents"
    harvest.harvest(execution_id=eid, name="qa_pii_test", agents_dir=golden_dir)

    data = json.loads((golden_dir / "qa" / "qa_pii_test.json").read_text(encoding="utf-8"))
    # PII original no debe aparecer en el golden
    assert "12345678" not in data["output"]
    assert "test@example.com" not in data["output"]


def test_harvest_output_is_none_raises(tmp_path):
    """Execution sin output (output=None) → HarvestError."""
    from evals import harvest

    tid = _mk_ticket(ado_id=9005)
    eid = _mk_execution(tid, status="completed", agent_type="qa", output=None)

    golden_dir = tmp_path / "evals" / "agents"
    with pytest.raises(harvest.HarvestError, match="output"):
        harvest.harvest(execution_id=eid, name="x", agents_dir=golden_dir)
