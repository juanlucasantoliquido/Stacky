"""Tests for deterministic Stacky memory validation (Phase D)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_validator_finds_checksum_mismatch(app_ctx):
    from db import session_scope
    from services import memory_store, memory_validator

    mid = memory_store.save_observation(
        project="MEM_VAL_CHECKSUM",
        type="bugfix",
        title="Checksum case",
        content="content v1",
    )
    with session_scope() as session:
        row = (
            session.query(memory_store.StackyMemoryObservation)
            .filter(memory_store.StackyMemoryObservation.memory_id == mid)
            .first()
        )
        row.normalized_hash = "bad"

    run_id = memory_validator.run_validation_sync(project="MEM_VAL_CHECKSUM", checks=["checksum"])
    run = memory_validator.get_run(run_id)
    findings = memory_validator.list_findings(project="MEM_VAL_CHECKSUM", run_id=run_id, status=None)

    assert run["status"] == "completed"
    assert any(f["check_name"] == "checksum" and f["memory_id"] == mid for f in findings)


def test_validator_quarantines_secret(app_ctx):
    from services import memory_store, memory_validator

    mid = memory_store.save_observation(
        project="MEM_VAL_SECRET",
        type="client_policy",
        title="Leaky policy",
        content="Never persist ADO_PAT=abc123 in memory",
    )

    run_id = memory_validator.run_validation_sync(project="MEM_VAL_SECRET", checks=["secret"])
    row = memory_store.get(mid)
    findings = memory_validator.list_findings(project="MEM_VAL_SECRET", run_id=run_id, status="open")

    assert row["status"] == "quarantined"
    assert any(f["check_name"] == "secret" and f["severity"] == "critical" for f in findings)


def test_validator_finds_exact_duplicates(app_ctx):
    from services import memory_store, memory_validator

    a = memory_store.save_observation(
        project="MEM_VAL_DUP",
        type="pattern",
        title="Same",
        content="same exact payload",
    )
    b = memory_store.save_observation(
        project="MEM_VAL_DUP",
        type="pattern",
        title="Same",
        content="same exact payload",
    )

    run_id = memory_validator.run_validation_sync(project="MEM_VAL_DUP", checks=["duplicate_exact"])
    findings = memory_validator.list_findings(project="MEM_VAL_DUP", run_id=run_id, status=None)

    dup = next(f for f in findings if f["check_name"] == "duplicate_exact")
    assert set(dup["evidence"]["memory_ids"]) == {a, b}
    assert memory_store.get(a)["duplicate_count"] == 2
    assert memory_store.get(b)["duplicate_count"] == 2


def test_validator_finds_schema_errors(app_ctx):
    from db import session_scope
    from services import memory_store, memory_validator

    mid = memory_store.save_observation(
        project="MEM_VAL_SCHEMA",
        type="pattern",
        title="Schema",
        content="valid content",
    )
    with session_scope() as session:
        row = (
            session.query(memory_store.StackyMemoryObservation)
            .filter(memory_store.StackyMemoryObservation.memory_id == mid)
            .first()
        )
        row.status = "mystery"

    run_id = memory_validator.run_validation_sync(project="MEM_VAL_SCHEMA", checks=["schema"])
    findings = memory_validator.list_findings(project="MEM_VAL_SCHEMA", run_id=run_id, status=None)

    assert any(f["check_name"] == "schema" and "invalid status" in f["detail"] for f in findings)


def test_validation_api_contract(client, monkeypatch):
    from services import memory_validator

    created = {}

    def fake_start_validation_run(*, project=None, requested_by=None, checks=None):
        created["project"] = project
        created["requested_by"] = requested_by
        created["checks"] = checks
        return 4242

    monkeypatch.setattr(memory_validator, "start_validation_run", fake_start_validation_run)
    r = client.post(
        "/api/memory/validation/runs",
        json={"project": "MEM_VAL_API", "checks": ["schema"]},
        headers={"X-User-Email": "validator@example.com"},
    )

    assert r.status_code == 202
    assert r.get_json() == {"run_id": 4242, "status": "queued"}
    assert created == {
        "project": "MEM_VAL_API",
        "requested_by": "validator@example.com",
        "checks": ["schema"],
    }


def test_validator_finds_semantic_duplicates(app_ctx, monkeypatch):
    from services import memory_store, memory_validator

    monkeypatch.setenv("STACKY_MEMORY_VALIDATOR_ADVANCED", "true")
    monkeypatch.setenv("STACKY_MEMORY_SEMANTIC_DUP_THRESHOLD", "0.25")
    a = memory_store.save_observation(
        project="MEM_VAL_SEM_DUP",
        type="bugfix",
        title="Outbox idempotente",
        content="El outbox debe deduplicar eventos por sha y reintentar push pendiente",
    )
    b = memory_store.save_observation(
        project="MEM_VAL_SEM_DUP",
        type="bugfix",
        title="Outbox retry",
        content="La cola outbox deduplica por sha y conserva pushes pendientes para reintento",
    )

    run_id = memory_validator.run_validation_sync(project="MEM_VAL_SEM_DUP", checks=["duplicate_semantic"])
    findings = memory_validator.list_findings(project="MEM_VAL_SEM_DUP", run_id=run_id, status=None)

    finding = next(f for f in findings if f["check_name"] == "duplicate_semantic")
    assert set(finding["evidence"]["memory_ids"]) == {a, b}


def test_conflict_graph_finding_and_not_conflict_action(app_ctx, monkeypatch):
    from services import memory_store, memory_validator

    monkeypatch.setenv("STACKY_MEMORY_VALIDATOR_ADVANCED", "true")
    a = memory_store.save_observation(
        project="MEM_VAL_CONFLICT",
        type="client_policy",
        title="Politica A",
        content="Usar stored procedures para cambios de datos",
    )
    b = memory_store.save_observation(
        project="MEM_VAL_CONFLICT",
        type="client_policy",
        title="Politica B",
        content="Permitir DML directo en scripts operativos",
    )
    memory_store.mark_relation(
        project="MEM_VAL_CONFLICT",
        source_memory_id=a,
        target_memory_id=b,
        relation="conflicts_with",
    )

    run_id = memory_validator.run_validation_sync(project="MEM_VAL_CONFLICT", checks=["conflict_graph"])
    findings = memory_validator.list_findings(project="MEM_VAL_CONFLICT", run_id=run_id, status="open")
    finding = next(f for f in findings if f["check_name"] == "conflict_graph")

    resolved = memory_validator.apply_finding_action(
        finding_id=finding["id"],
        action="mark_not_conflict",
        actor="curator@example.com",
    )
    assert resolved["status"] == "resolved"

    run_id_2 = memory_validator.run_validation_sync(project="MEM_VAL_CONFLICT", checks=["conflict_graph"])
    findings_2 = memory_validator.list_findings(project="MEM_VAL_CONFLICT", run_id=run_id_2, status="open")
    assert not any(f["check_name"] == "conflict_graph" for f in findings_2)


def test_llm_judge_creates_finding_from_model_verdict(app_ctx, monkeypatch):
    from services import memory_store, memory_validator
    from services.pm import pm_llm_client

    monkeypatch.setenv("STACKY_MEMORY_VALIDATOR_ADVANCED", "true")
    mid = memory_store.save_observation(
        project="MEM_VAL_LLM",
        type="client_policy",
        title="Policy needs review",
        content="Usar este criterio solo si el lead lo confirma",
    )

    class FakeResult:
        success = True
        parsed_json = {
            "verdict": "needs_review",
            "reason": "requires human confirmation",
            "confidence": 0.88,
        }
        model = "mock-judge"

    monkeypatch.setattr(pm_llm_client, "call_llm", lambda spec: FakeResult())
    run_id = memory_validator.run_validation_sync(project="MEM_VAL_LLM", checks=["llm_judge"])
    findings = memory_validator.list_findings(project="MEM_VAL_LLM", run_id=run_id, status="open")

    assert any(
        f["check_name"] == "llm_judge"
        and f["memory_id"] == mid
        and f["evidence"]["verdict"] == "needs_review"
        for f in findings
    )


def test_finding_action_quarantines_memory(app_ctx):
    from services import memory_store, memory_validator

    mid = memory_store.save_observation(
        project="MEM_VAL_ACTION",
        type="bugfix",
        title="Manual finding source",
        content="payload",
    )
    run_id = memory_validator.run_validation_sync(project="MEM_VAL_ACTION", checks=["checksum"])
    from db import session_scope

    with session_scope() as session:
        row = memory_validator.StackyMemoryFinding(
            validation_run_id=run_id,
            project="MEM_VAL_ACTION",
            check_name="llm_judge",
            severity="warning",
            status="open",
            memory_id=mid,
            title="Manual review",
            detail="manual",
        )
        row.evidence = {"memory_ids": [mid]}
        session.add(row)
        session.flush()
        finding_id = row.id

    result = memory_validator.apply_finding_action(
        finding_id=finding_id,
        action="quarantine_memory",
        actor="dev@local",
    )

    assert result["status"] == "resolved"
    assert memory_store.get(mid)["status"] == "quarantined"


def test_ticket_badges_group_open_findings_by_source_ticket(app_ctx):
    from services import memory_store, memory_validator
    from db import session_scope

    mid = memory_store.save_observation(
        project="MEM_VAL_BADGE",
        type="bugfix",
        title="Ticket scoped memory",
        content="memory tied to a ticket",
        source_ticket_id=123,
    )
    run_id = memory_validator.run_validation_sync(project="MEM_VAL_BADGE", checks=["schema"])
    with session_scope() as session:
        row = memory_validator.StackyMemoryFinding(
            validation_run_id=run_id,
            project="MEM_VAL_BADGE",
            check_name="llm_judge",
            severity="error",
            status="open",
            memory_id=mid,
            title="Badge finding",
            detail="badge",
        )
        row.evidence = {"memory_ids": [mid]}
        session.add(row)

    badges = memory_validator.ticket_badges(project="MEM_VAL_BADGE")
    assert badges["123"]["open_findings"] == 1
    assert badges["123"]["error"] == 1


def test_default_run_uses_only_cheap_checks(monkeypatch):
    from services import memory_validator

    monkeypatch.delenv("STACKY_MEMORY_VALIDATOR_ADVANCED", raising=False)
    assert set(memory_validator._normalize_checks(None)) == set(
        memory_validator._CHEAP_CHECKS
    )


def test_advanced_check_requires_flag(monkeypatch):
    from services import memory_validator

    monkeypatch.delenv("STACKY_MEMORY_VALIDATOR_ADVANCED", raising=False)
    with pytest.raises(ValueError):
        memory_validator._normalize_checks(["llm_judge"])

    monkeypatch.setenv("STACKY_MEMORY_VALIDATOR_ADVANCED", "true")
    assert memory_validator._normalize_checks(["llm_judge"]) == ["llm_judge"]
    assert set(memory_validator._normalize_checks(None)) == set(memory_validator.CHECKS)
