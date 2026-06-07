"""Tests de captura post-run de memoria (services/post_run_memory.py) — Fase B.

Cubre:
  - capture_on_completion crea DRAFT cuando score >= umbral
  - score < umbral → no crea draft
  - capture_on_approval promueve el draft a ACTIVE (mismo topic_key, revision++)
  - flag OFF → no captura
  - integración: POST /api/executions/<id>/approve dispara la captura ACTIVE
  - PII del output se redacta en el contenido persistido
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_ADO_SEQ = iter(range(700000, 799999))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


def _seed_execution(
    *,
    project: str,
    agent_type: str = "developer",
    output: str = "Resultado del análisis del ticket con detalle reutilizable.",
    score: int | None = 90,
    status: str = "completed",
):
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        tk = Ticket(
            ado_id=next(_ADO_SEQ),
            project=project,
            title="Ticket de prueba memoria",
            ado_state="Active",
            description="desc",
            work_item_type="Task",
        )
        session.add(tk)
        session.flush()
        ex = AgentExecution(
            ticket_id=tk.id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            output=output,
            started_by="dev@empresa.com",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        if score is not None:
            ex.contract_result = {"score": score, "passed": score >= 70}
        session.add(ex)
        session.flush()
        return ex.id, tk.ado_id


def test_completion_creates_draft_above_threshold(app_ctx, monkeypatch):
    from services import memory_store, post_run_memory

    monkeypatch.setenv("STACKY_MEMORY_CAPTURE_ENABLED", "true")
    exec_id, ado_id = _seed_execution(project="MEM_PRM_1", score=90)

    mid = post_run_memory.capture_on_completion(exec_id)
    assert mid is not None
    row = memory_store.get(mid)
    assert row["status"] == "draft"
    assert row["type"] == "session_summary"
    assert row["topic_key"] == f"session/ado-{ado_id}-developer"
    assert row["source_execution_id"] == exec_id


def test_completion_skipped_below_threshold(app_ctx, monkeypatch):
    from services import post_run_memory

    monkeypatch.setenv("STACKY_MEMORY_CAPTURE_ENABLED", "true")
    exec_id, _ = _seed_execution(project="MEM_PRM_2", score=40)
    assert post_run_memory.capture_on_completion(exec_id) is None


def test_approval_promotes_draft_to_active(app_ctx, monkeypatch):
    from services import memory_store, post_run_memory

    monkeypatch.setenv("STACKY_MEMORY_CAPTURE_ENABLED", "true")
    exec_id, _ = _seed_execution(project="MEM_PRM_3", score=88)

    draft_id = post_run_memory.capture_on_completion(exec_id)
    assert memory_store.get(draft_id)["status"] == "draft"

    active_id = post_run_memory.capture_on_approval(exec_id)
    assert active_id == draft_id  # mismo topic_key → misma fila
    promoted = memory_store.get(active_id)
    assert promoted["status"] == "active"
    assert promoted["revision_count"] == 2


def test_disabled_flag_captures_nothing(app_ctx, monkeypatch):
    from services import post_run_memory

    monkeypatch.delenv("STACKY_MEMORY_CAPTURE_ENABLED", raising=False)
    exec_id, _ = _seed_execution(project="MEM_PRM_4", score=95)
    assert post_run_memory.capture_on_completion(exec_id) is None
    assert post_run_memory.capture_on_approval(exec_id) is None


def test_approve_endpoint_triggers_capture(app_ctx, monkeypatch):
    from services import memory_store

    monkeypatch.setenv("STACKY_MEMORY_CAPTURE_ENABLED", "true")
    exec_id, ado_id = _seed_execution(project="MEM_PRM_5", score=80)

    client = app_ctx.test_client()
    r = client.post(f"/api/executions/{exec_id}/approve")
    assert r.status_code == 200

    actives = memory_store.list_observations(project="MEM_PRM_5", status="active")
    assert any(m["source_execution_id"] == exec_id for m in actives)


def test_pii_is_redacted_in_stored_memory(app_ctx, monkeypatch):
    from services import memory_store, post_run_memory

    monkeypatch.setenv("STACKY_MEMORY_CAPTURE_ENABLED", "true")
    secret_email = "juan.perez@cliente.com"
    exec_id, _ = _seed_execution(
        project="MEM_PRM_6",
        score=90,
        output=f"El usuario reportó el bug desde {secret_email} y adjuntó logs.",
    )
    mid = post_run_memory.capture_on_completion(exec_id)
    content = memory_store.get(mid)["content"]
    assert secret_email not in content  # PII redactada
