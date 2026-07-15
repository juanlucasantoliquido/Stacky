"""Plan 142 F8 (OPCIONAL) — Tests de /api/metrics/cost-reconciliation-audit.

Read-only: cuantifica la divergencia R3 (legacy `_execution_costs` vs extractor
canónico F0), incluyendo `codex_invisible_usd`. NO toca /ticket-costs ni /project-costs.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_legacy_mirror_matches_current_execution_costs_bug():
    """legacy_cost_mirror() es un espejo puro EXACTO de api.metrics._execution_costs:
    lee sólo claude_telemetry.total_cost_usd (reportado) + trata cost_estimated (bool
    en harness_telemetry, pero acá cualquier valor truthy) como si fuera un MONTO — el
    bug real R3. Se verifica reproduciendo el número contra la función legacy real."""
    from api.metrics import _execution_costs
    from models import AgentExecution
    from services.cost_analytics import legacy_cost_mirror

    md = {"claude_telemetry": {"total_cost_usd": 2.5}, "cost_estimated": 0.75}
    ex = AgentExecution(metadata_json=json.dumps(md))
    reported, estimated, _has_estimated = _execution_costs(ex)
    legacy_total = round(reported + estimated, 6)

    assert legacy_cost_mirror(md) == legacy_total
    assert legacy_cost_mirror(md) == 3.25  # 2.5 (reportado) + 0.75 tratado como monto (bug)

    # Sin claude_telemetry ni cost_estimated -> 0.0 (no crashea, no inventa).
    assert legacy_cost_mirror({}) == 0.0
    assert legacy_cost_mirror(None) == 0.0


@pytest.fixture(scope="module")
def _app():
    os.environ["STACKY_COST_CENTER_ENABLED"] = "true"
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def client(_app):
    with _app.test_client() as c:
        yield c


_NEXT_ADO_ID = 191000  # rango reservado para test_cost_reconciliation_audit (no colisiona)


def _seed_exec(*, runtime="claude_code_cli", model="claude-sonnet-5",
                ht=None, claude_telemetry=None, cost_estimated_toplevel=None,
                project="cost-audit-proj"):
    global _NEXT_ADO_ID
    _NEXT_ADO_ID += 1
    ado_id = _NEXT_ADO_ID

    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project=project, stacky_project_name=project,
                    title=f"cost-audit-{ado_id}", ado_state="Active")
        session.add(t)
        session.flush()

        when = datetime.utcnow()
        md: dict = {"runtime": runtime, "model": model}
        if ht is not None:
            md["harness_telemetry"] = ht
        if claude_telemetry is not None:
            md["claude_telemetry"] = claude_telemetry
        if cost_estimated_toplevel is not None:
            md["cost_estimated"] = cost_estimated_toplevel

        e = AgentExecution(
            ticket_id=t.id, agent_type="developer", status="completed",
            input_context_json="[]", started_by="test",
            started_at=when, completed_at=when + timedelta(seconds=5),
            metadata_json=json.dumps(md),
        )
        session.add(e)
        session.flush()
        return e.id


def test_audit_disabled_returns_enabled_false(client, monkeypatch):
    import config as config_module
    monkeypatch.setattr(config_module.config, "STACKY_COST_CENTER_ENABLED", False)
    resp = client.get("/api/metrics/cost-reconciliation-audit")
    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": False}


def test_codex_invisible_usd_is_positive_when_codex_has_cost(client):
    _seed_exec(runtime="codex_cli", model="gpt-5",
               ht={"input_tokens": 2_000_000, "output_tokens": 500_000})
    resp = client.get("/api/metrics/cost-reconciliation-audit")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["codex_invisible_usd"] > 0.0
    # El legacy (_execution_costs) NUNCA ve costo de codex_cli (sólo lee claude_telemetry).
    assert body["canonical_billable_usd"] >= body["codex_invisible_usd"]


def test_delta_zero_when_only_claude_reported(client):
    # Ventana de filtro propia (proyecto dedicado) para no arrastrar los runs de los
    # otros tests del módulo: sólo un run claude reportado vía claude_telemetry legacy,
    # exactamente lo que el legacy SÍ sabe leer -> canónico == legacy -> delta 0.
    project = "cost-audit-delta-zero"
    _seed_exec(runtime="claude_code_cli", model="claude-sonnet-5",
               claude_telemetry={"total_cost_usd": 4.0}, project=project)
    resp = client.get(f"/api/metrics/cost-reconciliation-audit?project={project}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["canonical_billable_usd"] == 4.0
    assert body["legacy_reported_usd"] == 4.0
    assert body["delta_usd"] == 0.0
