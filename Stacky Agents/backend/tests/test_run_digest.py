"""Tests del servicio run_digest (U1.5 — doc 23).

Cubre: agregación de totales/costos, filtro por proyecto, empty-state,
degradación sin claves nuevas de metadata, renderers estables y daemon off
por default. Llama compose_digest directo (no necesita el cliente Flask).
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


@pytest.fixture(autouse=True)
def _db():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    yield
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()


def _seed(*, ado_id: int, project: str, execs: list[dict], when: datetime | None = None) -> int:
    """Crea un Ticket con N ejecuciones.

    Cada spec admite: agent_type, status, runtime, reported, estimated,
    failure_kind, error_message, started_at.
    """
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project=project,
            stacky_project_name=project,
            title=f"ticket-{ado_id}",
            ado_state="Active",
        )
        session.add(t)
        session.flush()

        default_when = when or datetime.utcnow()
        for spec in execs:
            md: dict = {}
            if spec.get("runtime"):
                md["runtime"] = spec["runtime"]
            if "reported" in spec:
                md["claude_telemetry"] = {"total_cost_usd": spec["reported"]}
            if "estimated" in spec:
                md["cost_estimated"] = spec["estimated"]
            if spec.get("failure_kind"):
                md["failure_kind"] = spec["failure_kind"]
            e = AgentExecution(
                ticket_id=t.id,
                agent_type=spec.get("agent_type", "developer"),
                status=spec.get("status", "completed"),
                input_context_json="[]",
                started_by="test",
                started_at=spec.get("started_at", default_when),
                error_message=spec.get("error_message"),
            )
            e.metadata_dict = md
            session.add(e)
        session.flush()
        return t.id


def test_compose_digest_aggregates_totals_and_costs():
    from services.run_digest import compose_digest

    _seed(
        ado_id=70001,
        project="PRJ-A",
        execs=[
            {"agent_type": "functional", "status": "completed", "runtime": "claude", "reported": 0.10},
            {"agent_type": "functional", "status": "completed", "runtime": "claude", "reported": 0.20},
            {"agent_type": "developer", "status": "needs_review", "runtime": "codex", "failure_kind": "contract_failed"},
            {"agent_type": "developer", "status": "error", "runtime": "codex", "estimated": 0.05, "error_message": "boom"},
        ],
    )

    digest = compose_digest(days=7)
    totals = digest["totals"]

    assert totals["runs"] == 4
    assert totals["completed"] == 2
    assert totals["needs_review"] == 1
    assert totals["error"] == 1
    assert totals["success_rate"] == pytest.approx(0.5)
    assert totals["tickets_touched"] == 1
    assert totals["cost_usd"]["reported"] == pytest.approx(0.30)
    assert totals["cost_usd"]["estimated"] == pytest.approx(0.05)
    assert totals["cost_usd"]["total"] == pytest.approx(0.35)
    assert digest["partial"] is True  # hubo costo estimado

    agents = {row["name"]: row for row in digest["by_agent_type"]}
    assert agents["functional"]["runs"] == 2
    assert agents["functional"]["completed"] == 2
    assert agents["developer"]["runs"] == 2

    runtimes = {row["name"]: row for row in digest["by_runtime"]}
    assert runtimes["claude"]["runs"] == 2
    assert runtimes["codex"]["runs"] == 2

    failures = {f["kind"]: f["count"] for f in digest["top_failures"]}
    assert failures.get("contract_failed") == 1
    assert "boom" in failures  # error sin failure_kind cae al error_message


def test_compose_digest_empty_period_has_no_activity():
    from services.run_digest import compose_digest

    digest = compose_digest(days=7)

    assert digest["totals"]["runs"] == 0
    assert digest["partial"] is False
    assert digest["highlights"] == ["sin actividad en el período"]
    assert digest["top_failures"] == []


def test_compose_digest_filters_by_project():
    from services.run_digest import compose_digest

    _seed(ado_id=71001, project="PRJ-A", execs=[{"status": "completed", "reported": 0.1}])
    _seed(ado_id=71002, project="PRJ-B", execs=[{"status": "completed", "reported": 0.9}])

    digest = compose_digest(days=7, project="PRJ-A")

    assert digest["totals"]["runs"] == 1
    assert digest["totals"]["cost_usd"]["reported"] == pytest.approx(0.1)


def test_compose_digest_degrades_without_new_metadata_keys():
    from services.run_digest import compose_digest

    # Sin runtime, sin telemetría, sin failure_kind; el error tampoco trae error_message.
    _seed(
        ado_id=72001,
        project="PRJ-A",
        execs=[
            {"status": "completed"},
            {"status": "error"},
        ],
    )

    digest = compose_digest(days=7)

    assert digest["totals"]["runs"] == 2
    assert digest["totals"]["cost_usd"]["total"] == pytest.approx(0.0)
    assert digest["partial"] is False
    runtimes = {row["name"]: row for row in digest["by_runtime"]}
    assert "unknown" in runtimes  # runtime ausente → "unknown"
    failures = {f["kind"]: f["count"] for f in digest["top_failures"]}
    assert failures.get("error") == 1  # fallback determinista a "error"


def test_renderers_contain_key_figures():
    from services.run_digest import compose_digest, to_html, to_markdown

    _seed(
        ado_id=73001,
        project="PRJ-A",
        execs=[
            {"status": "completed", "reported": 1.0},
            {"status": "error", "error_message": "x"},
        ],
    )
    digest = compose_digest(days=7)

    md = to_markdown(digest)
    assert md.startswith("# Stacky Digest")
    assert "Runs: 2" in md
    assert "50.0%" in md  # success_rate 0.5 formateado

    html = to_html(digest)
    assert "<h1>Stacky Digest</h1>" in html
    assert "Runs: <b>2</b>" in html


def test_digest_daemon_disabled_by_default():
    # app.py lee el flag sobre la instancia (from config import config), no el módulo.
    from config import config

    assert int(config.STACKY_DIGEST_INTERVAL_HOURS) == 0
