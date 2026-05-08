"""Tests de Fase 5: FA-08, FA-10, FA-18, FA-32, FA-36, FA-39, FA-40, FA-47."""
import os, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


# ── FA-32 delta_prompt ───────────────────────────────────────

def test_fa32_compute_diff_no_change():
    from services.delta_prompt import compute_diff
    blocks = [{"id": "a", "kind": "auto", "title": "x", "content": "hola"}]
    r = compute_diff(blocks, blocks)
    assert r.change_ratio == 0.0
    assert not r.is_delta_eligible


def test_fa32_compute_diff_detects_modification():
    from services.delta_prompt import compute_diff
    old = [{"id": "a", "kind": "auto", "title": "t", "content": "descripcion corta"}]
    new = [{"id": "a", "kind": "auto", "title": "t", "content": "descripcion completamente diferente ahora"}]
    r = compute_diff(old, new)
    assert r.change_ratio > 0
    assert len(r.changed_blocks) == 1
    assert r.changed_blocks[0].kind == "modified"


def test_fa32_build_delta_prompt_format():
    from services.delta_prompt import DiffResult, BlockDiff, build_delta_prompt
    diff = DiffResult(
        change_ratio=0.15,
        changed_blocks=[BlockDiff(
            block_id="notes", title="Notas", kind="modified",
            old_content="viejo", new_content="nuevo y diferente",
        )],
        is_delta_eligible=True,
    )
    prompt = build_delta_prompt("# Output anterior\n\nContenido previo.", diff)
    assert "Output anterior" in prompt
    assert "Notas" in prompt
    assert "Actualizá SOLO" in prompt


# ── FA-39 audit chain ────────────────────────────────────────

def test_fa39_seal_and_verify_clean_chain(client):
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=55551, project="RSPacifico", title="audit test", ado_state="Done")
        session.add(t); session.flush()
        e = AgentExecution(
            ticket_id=t.id, agent_type="qa", status="completed",
            verdict="approved", started_by="dev@local",
            input_context_json="[]", output="# Verdict: PASS",
        )
        session.add(e); session.flush()
        exec_id = e.id; ticket_id = t.id

    from services import audit_chain
    nhash = audit_chain.seal(exec_id)
    assert nhash and len(nhash) == 64

    result = audit_chain.verify_chain(ticket_id)
    assert result.valid
    assert result.length == 1


def test_fa39_verify_detects_tamper():
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import audit_chain

    with session_scope() as session:
        t = Ticket(ado_id=55552, project="RSPacifico", title="tamper test", ado_state="Done")
        session.add(t); session.flush()
        e = AgentExecution(
            ticket_id=t.id, agent_type="qa", status="completed",
            started_by="dev@local", input_context_json="[]",
            output="# original output",
        )
        session.add(e); session.flush()
        exec_id = e.id; ticket_id = t.id

    audit_chain.seal(exec_id)

    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        row.output = "# TAMPERED output"

    result = audit_chain.verify_chain(ticket_id)
    assert not result.valid
    assert result.first_tampered_exec_id == exec_id


def test_fa39_api_verify(client):
    r = client.get("/api/audit/9999/chain")
    assert r.status_code == 200
    d = r.get_json()
    assert "valid" in d and "length" in d


# ── FA-08 constraints ────────────────────────────────────────

def test_fa08_constraint_create_and_list(client):
    r = client.post("/api/constraints", json={
        "trigger_keywords": ["cobranza", "pago"],
        "constraint_text": "Toda modificación en cobranza requiere auditoría",
        "agent_types": ["developer"],
    })
    assert r.status_code == 201

    r2 = client.get("/api/constraints")
    assert any("auditoría" in c["constraint_text"] for c in r2.get_json())


def test_fa08_constraint_relevant_match():
    from services import constraints
    constraints.create(
        project=None,
        trigger_keywords=["cobranza"],
        constraint_text="Requiere log de auditoría en cobranza",
        agent_types=["developer"],
    )
    matched = constraints.relevant(
        agent_type="developer",
        project=None,
        context_text="Flujo de cobranza con SMS",
    )
    assert any("auditoría" in m.constraint_text for m in matched)


# ── FA-10 style memory ───────────────────────────────────────

def test_fa10_compute_no_data():
    from services import style_memory
    r = style_memory.compute_profile("nobody@x.com", "qa")
    assert r is None


def test_fa10_compute_with_data():
    from datetime import datetime
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import style_memory

    with session_scope() as session:
        t = Ticket(ado_id=77701, project="RSPacifico", title="style test", ado_state="Done")
        session.add(t); session.flush()
        # 5 outputs aprobados de longitud media
        for i in range(5):
            e = AgentExecution(
                ticket_id=t.id, agent_type="qa", status="completed",
                verdict="approved", started_by="style-user@local",
                started_at=datetime.utcnow(),
                input_context_json="[]",
                output="# Verdict: PASS\n\n" + "palabra " * 200,
            )
            session.add(e)

    profile = style_memory.compute_profile("style-user@local", "qa")
    assert profile is not None
    assert profile["sample_size"] == 5
    assert profile["length_pref"] in {"concise", "balanced", "thorough"}


# ── FA-36 speculative ────────────────────────────────────────

def test_fa36_speculate_endpoint(client):
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = Ticket(ado_id=88801, project="RSPacifico", title="spec test", ado_state="To Do")
        session.add(t); session.flush()
        tid = t.id
    r = client.post("/api/agents/speculate", json={
        "agent_type": "qa",
        "ticket_id": tid,
        "context_blocks": [{"id": "b1", "kind": "auto", "title": "x", "content": "test"}],
    })
    assert r.status_code == 200
    d = r.get_json()
    assert "spec_id" in d


# ── FA-47 critique ───────────────────────────────────────────

def test_fa47_critique_endpoint(client):
    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as session:
        t = Ticket(ado_id=99901, project="RSPacifico", title="critic test", ado_state="Done")
        session.add(t); session.flush()
        e = AgentExecution(
            ticket_id=t.id, agent_type="technical", status="completed",
            started_by="dev@local", input_context_json="[]",
            output="# Análisis\n\n## 1. Sección\nContenido del análisis técnico.",
        )
        session.add(e); session.flush()
        eid = e.id
    r = client.post(f"/api/executions/{eid}/critique")
    assert r.status_code == 200
    d = r.get_json()
    assert "critique" in d and d["execution_id"] == eid


# ── FA-18 auto-execute SELECTs ───────────────────────────────

def test_fa18_run_selects_mock(client):
    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as session:
        t = Ticket(ado_id=11101, project="RSPacifico", title="sql test", ado_state="Done")
        session.add(t); session.flush()
        e = AgentExecution(
            ticket_id=t.id, agent_type="technical", status="completed",
            started_by="dev@local", input_context_json="[]",
            output="## Verificación\n```sql\nSELECT * FROM clientes LIMIT 5;\n```",
        )
        session.add(e); session.flush()
        eid = e.id
    r = client.post(f"/api/executions/{eid}/run-selects")
    assert r.status_code == 200
    d = r.get_json()
    assert d["total_found"] >= 1
    assert d["queries"][0]["row_count"] >= 1


def test_fa18_blocks_non_select():
    import re
    sql_blocks = ["DROP TABLE clientes;", "INSERT INTO x VALUES (1);", "SELECT 1"]
    for sql in sql_blocks:
        is_select = bool(re.match(r"^\s*(SELECT|WITH)\s", sql, re.IGNORECASE))
        if "SELECT" in sql:
            assert is_select
        else:
            assert not is_select


# ── FA-40 GDPR erase ─────────────────────────────────────────

def test_fa40_erase_endpoint(client):
    r = client.post("/api/admin/erase", json={"user_email": "nobody@example.com"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"]
    assert "executions_redacted" in d
