"""Plan 142 F2 — Tests de los endpoints /api/metrics/cost-summary|cost-burn|cost-breakdown.

Usa app.test_client() del repo (mismo patrón que test_executions_history.py). Seeding
sigue el patrón de test_executions_history.py/test_metrics_endpoint.py: Ticket NO tiene
columna `status` (sólo `ado_state`/`stacky_status`) — C6 advierte no adivinar.
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


@pytest.fixture(scope="module")
def _app():
    # Default ON en v2 (C1), pero se fuerza explícito por si el env la apaga.
    os.environ["STACKY_COST_CENTER_ENABLED"] = "true"
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def client(_app):
    with _app.test_client() as c:
        yield c


_NEXT_ADO_ID = 190000  # rango reservado para test_cost_center_api (no colisiona)


def _seed_exec(*, runtime="claude_code_cli", model="claude-sonnet-5", agent_type="developer",
                status="completed", started_at=None, ht=None, top=None, project="costcenterproj"):
    global _NEXT_ADO_ID
    _NEXT_ADO_ID += 1
    ado_id = _NEXT_ADO_ID

    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project=project,
            stacky_project_name=project,
            title=f"cost-{ado_id}",
            ado_state="Active",
        )
        session.add(t)
        session.flush()

        when = started_at or datetime.utcnow()
        md: dict = {"runtime": runtime, "model": model}
        if ht is not None:
            md["harness_telemetry"] = ht
        if top is not None:
            md.update(top)

        e = AgentExecution(
            ticket_id=t.id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=when,
            completed_at=when + timedelta(seconds=5),
            metadata_json=json.dumps(md),
        )
        session.add(e)
        session.flush()
        return e.id, t.id


def test_summary_disabled_returns_enabled_false(client, monkeypatch):
    import config as config_module
    monkeypatch.setattr(config_module.config, "STACKY_COST_CENTER_ENABLED", False)
    resp = client.get("/api/metrics/cost-summary")
    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": False}


def test_summary_shape_and_billable_excludes_nominal(client):
    _seed_exec(runtime="claude_code_cli", model="claude-sonnet-5",
               ht={"total_cost_usd": 1.5, "cost_estimated": False,
                   "input_tokens": 1000, "output_tokens": 200})
    _seed_exec(runtime="github_copilot", model="claude-sonnet-5",
               ht={"input_tokens": 500, "output_tokens": 100})
    resp = client.get("/api/metrics/cost-summary")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["enabled"] is True
    assert "filters_echo" in body
    assert "capped" in body
    assert body["billable_usd"] >= 1.5
    assert body["nominal_usd"] >= 0.0
    assert body["billable_usd"] == round(body["reported_usd"] + body["estimated_usd"], 6)
    assert "top_runs" in body and isinstance(body["top_runs"], list)


def test_burn_invalid_bucket_400(client):
    resp = client.get("/api/metrics/cost-burn?bucket=month")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_bucket"


def test_burn_invalid_date_400(client):
    resp = client.get("/api/metrics/cost-burn?from=not-a-date")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_date"


def test_burn_shape_has_series_and_comparison(client):
    _seed_exec(runtime="claude_code_cli", model="claude-sonnet-5",
               ht={"total_cost_usd": 0.2, "cost_estimated": False})
    resp = client.get("/api/metrics/cost-burn?bucket=day")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["bucket"] == "day"
    assert "series" in body and isinstance(body["series"], list)
    assert "period_comparison" in body
    assert {"current_billable_usd", "previous_billable_usd", "delta_pct"} <= set(body["period_comparison"].keys())


def test_breakdown_invalid_dimension_400(client):
    resp = client.get("/api/metrics/cost-breakdown?dimension=bogus")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_dimension"


def test_breakdown_by_runtime_groups(client):
    _seed_exec(runtime="codex_cli", model="gpt-5",
               ht={"input_tokens": 2000, "output_tokens": 500})
    resp = client.get("/api/metrics/cost-breakdown?dimension=runtime")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["dimension"] == "runtime"
    assert "groups" in body
    assert any(g["key"] == "codex_cli" for g in body["groups"])
    for g in body["groups"]:
        assert {"key", "reported_usd", "estimated_usd", "nominal_usd", "billable_usd",
                "tokens_in", "tokens_out", "runs"} <= set(g.keys())


def test_filters_days_clamped(client):
    resp = client.get("/api/metrics/cost-summary?days=9999")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["filters_echo"]["days_effective"] == 365


def test_cost_center_health_always_200_flag_enabled_key(client, monkeypatch):
    """F6 — mismo patrón que /api/migrator/health y /api/db-compare/health: SIEMPRE
    200, con `flag_enabled` reflejando la flag en vivo (la UI la usa para decidir si
    muestra la tab de nav, vía probeFlagHealth())."""
    resp_on = client.get("/api/metrics/cost-center/health")
    assert resp_on.status_code == 200
    assert resp_on.get_json()["flag_enabled"] is True

    import config as config_module
    monkeypatch.setattr(config_module.config, "STACKY_COST_CENTER_ENABLED", False)
    resp_off = client.get("/api/metrics/cost-center/health")
    assert resp_off.status_code == 200
    assert resp_off.get_json()["flag_enabled"] is False


def test_filters_runtime_and_cost_kind_applied(client):
    marker_project = "costcenter-filtertest"
    _seed_exec(runtime="github_copilot", model="claude-sonnet-5",
               ht={"input_tokens": 1_000_000, "output_tokens": 1_000_000}, project=marker_project)
    resp = client.get("/api/metrics/cost-summary?runtime=github_copilot&cost_kind=nominal")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    # Con runtime+cost_kind filtrados a github_copilot/nominal, billable_usd (reported+estimated)
    # debe ser 0 sobre el subconjunto filtrado (nominal SIEMPRE excluido de billable).
    assert body["billable_usd"] == 0.0
    assert body["nominal_usd"] > 0.0
