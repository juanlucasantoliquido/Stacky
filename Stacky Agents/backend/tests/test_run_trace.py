"""Plan 171 F3 — Traza estructurada por corrida.

La traza NUNCA inventa: lo que no está en la telemetría se declara en `sin_dato`.
Cubre los 3 runtimes con su degradación real (§4.1 del plan).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import db  # noqa: E402

db.init_db()

from services.run_trace import _telemetry_source, build_run_trace  # noqa: E402

_NEXT_ADO_ID = 171500  # rango propio (no colisiona con otros tests)


def _seed(*, runtime="codex_cli", status="completed", md_extra=None,
          started_at=None, completed=True, duration_s=5):
    global _NEXT_ADO_ID
    _NEXT_ADO_ID += 1
    ado_id = _NEXT_ADO_ID

    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="opsproj", stacky_project_name="opsproj",
                   title=f"trace-{ado_id}", ado_state="Active")
        session.add(t)
        session.flush()

        when = started_at or datetime.utcnow()
        md: dict = {"runtime": runtime}
        md.update(md_extra or {})

        e = AgentExecution(
            ticket_id=t.id, agent_type="developer", status=status,
            input_context_json="[]", started_by="test", started_at=when,
            completed_at=(when + timedelta(seconds=duration_s)) if completed else None,
            metadata_json=json.dumps(md),
        )
        session.add(e)
        session.flush()
        return e.id, ado_id


def test_trace_codex_completo():
    exec_id, ado_id = _seed(
        runtime="codex_cli",
        md_extra={"model": "claude-sonnet-5",
                  "harness_telemetry": {"input_tokens": 1000, "output_tokens": 500,
                                        "session_id": "s-1", "num_turns": 3}},
    )
    trace = build_run_trace(exec_id)

    assert trace is not None
    assert trace["execution_id"] == exec_id
    assert trace["runtime"] == "codex_cli"
    assert trace["status"] == "completed"
    assert trace["telemetry_source"] == "harness_telemetry"
    assert trace["duration_seconds"] == 5.0
    assert trace["cost"]["cost_kind"] == "estimated"
    assert [p["name"] for p in trace["phases"]] == ["started", "completed"]
    assert trace["ticket"]["ado_id"] == ado_id
    assert trace["session_id"] == "s-1"
    assert trace["num_turns"] == 3
    assert trace["stalled"] is False
    assert "model" not in trace["sin_dato"]


def test_trace_claude_sin_modelo_declara_sin_dato():
    exec_id, _ = _seed(
        runtime="claude_code_cli",
        md_extra={"claude_telemetry": {"usage": {"input_tokens": 800, "output_tokens": 200}}},
    )
    trace = build_run_trace(exec_id)

    assert trace["model"] is None, "sin modelo NO se inventa uno"
    assert "model" in trace["sin_dato"]
    assert trace["telemetry_source"] == "claude_telemetry"
    assert trace["cost"]["cost_kind"] == "unknown", "sin modelo no hay estimación (gap del 158)"


def test_trace_copilot_nominal():
    exec_id, _ = _seed(
        runtime="github_copilot",
        md_extra={"model": "gpt-4o", "tokens_in": 300, "tokens_out": 100},
    )
    trace = build_run_trace(exec_id)

    assert trace["telemetry_source"] == "bridge_metadata"
    assert trace["cost"]["cost_kind"] == "nominal", "la suscripción NUNCA es facturable"
    assert trace["cost"]["tokens_in"] == 300


def test_trace_running_stalled():
    exec_id, _ = _seed(runtime="codex_cli", status="running", completed=False,
                       started_at=datetime.utcnow() - timedelta(hours=2))
    trace = build_run_trace(exec_id)

    assert trace["stalled"] is True
    assert [p["name"] for p in trace["phases"]] == ["started"]
    assert trace["duration_seconds"] is None


def test_trace_running_reciente_no_stalled():
    exec_id, _ = _seed(runtime="codex_cli", status="running", completed=False,
                       started_at=datetime.utcnow() - timedelta(minutes=1))

    assert build_run_trace(exec_id)["stalled"] is False


def test_trace_inexistente_none():
    assert build_run_trace(999999) is None


def test_trace_incidente_enlazado(monkeypatch):
    from services import incident_store

    exec_id, _ = _seed()
    monkeypatch.setattr(
        incident_store, "find_by_execution",
        lambda eid: {"id": "inc-1", "title": "t", "status": "abierta", "otra": 1},
        raising=True,
    )
    assert build_run_trace(exec_id)["incident"] == {"id": "inc-1", "title": "t",
                                                    "status": "abierta"}

    def _boom(eid):
        raise RuntimeError("store roto")

    monkeypatch.setattr(incident_store, "find_by_execution", _boom, raising=True)
    assert build_run_trace(exec_id)["incident"] is None, "un store roto NUNCA rompe la traza"


def test_telemetry_source_determinista():
    assert _telemetry_source({"harness_telemetry": {"a": 1}}) == "harness_telemetry"
    assert _telemetry_source({"claude_telemetry": {"a": 1}}) == "claude_telemetry"
    assert _telemetry_source({"tokens_in": 1}) == "bridge_metadata"
    assert _telemetry_source({"model": "m"}) == "bridge_metadata"
    assert _telemetry_source({}) == "ninguna"
    assert _telemetry_source({"harness_telemetry": {}}) == "ninguna", "dict vacío no cuenta"
    assert _telemetry_source(None) == "ninguna"


def test_trace_no_expone_prompt_text():
    exec_id, _ = _seed(md_extra={"model": "m", "prompt_text": "SECRETO",
                                 "prompt_sha": "abc123", "agent_name": "dev.agent.md"})
    trace = build_run_trace(exec_id)

    assert "SECRETO" not in json.dumps(trace), "prompt_text NUNCA sale (privacidad)"
    assert trace["prompt_sha"] == "abc123"
    assert trace["agent_name"] == "dev.agent.md"
    assert "prompt_sha" not in trace["sin_dato"]
