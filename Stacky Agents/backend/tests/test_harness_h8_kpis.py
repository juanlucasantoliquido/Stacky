"""H8 — Tests de KPIs de valor agregado del arnés.

Verifica los 5 KPIs nuevos en compute_health:
  1. autocorrection_saves  — runs donde autocorrect fue invocado Y terminó completed
  2. memory_hit_rate       — fracción de runs con memory_blocks_injected >= 1
  3. runaway_stops         — runs marcados needs_review por runaway guard
  4. cost_per_ticket_usd   — suma de costos / tickets únicos (costo total del ticket)
  5. avg_contract_score    — desglosado en by_runtime (ya existía, verificar shape)
  + Sin regresión: shape anterior sigue intacta.
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


@pytest.fixture(autouse=True)
def _db_ready():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()
    yield


def _mk_ticket(ado_id: int) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="RSTest", title=f"t-{ado_id}",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _mk_exec(
    ticket_id: int,
    *,
    status: str,
    runtime: str = "claude_code_cli",
    agent_type: str = "developer",
    autocorrect_attempts: int = 0,
    memory_blocks_injected: int | None = None,
    runaway: dict | None = None,
    cost: float | None = None,
    score: int | None = None,
    days_ago: float = 1,
) -> int:
    from db import session_scope
    from models import AgentExecution

    md: dict = {"runtime": runtime}
    if autocorrect_attempts:
        md["autocorrect"] = {"attempts": autocorrect_attempts, "max_retries": 3,
                             "last_action": "retry", "last_errors": []}
    if memory_blocks_injected is not None:
        md["memory_blocks_injected"] = memory_blocks_injected
    if runaway is not None:
        md["runaway"] = runaway
    if cost is not None:
        md["claude_telemetry"] = {"total_cost_usd": cost}
    cr = (
        json.dumps({"score": score, "passed": score >= 70})
        if score is not None else None
    )

    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow() - timedelta(days=days_ago),
            metadata_json=json.dumps(md),
            contract_result_json=cr,
        )
        session.add(e)
        session.flush()
        return e.id


# ── 1. autocorrection_saves ──────────────────────────────────────────────────

def test_autocorrection_saves_counts_completed_with_autocorrect():
    """autocorrection_saves = runs con autocorrect invocado Y completed."""
    from services.harness_health import compute_health

    t = _mk_ticket(80001)
    # Cuenta: autocorrect invocado + completed
    _mk_exec(t, status="completed", autocorrect_attempts=2)
    # NO cuenta: autocorrect invocado pero no completed
    _mk_exec(t, status="needs_review", autocorrect_attempts=1)
    # NO cuenta: completed pero sin autocorrect
    _mk_exec(t, status="completed", autocorrect_attempts=0)

    h = compute_health(window_days=14).to_dict()
    assert h["autocorrection_saves"] == 1


def test_autocorrection_saves_zero_when_no_autocorrect():
    """Sin ningún run con autocorrect, autocorrection_saves = 0."""
    from services.harness_health import compute_health

    t = _mk_ticket(80002)
    _mk_exec(t, status="completed")
    _mk_exec(t, status="error")

    h = compute_health(window_days=14).to_dict()
    assert h["autocorrection_saves"] == 0


# ── 2. memory_hit_rate ───────────────────────────────────────────────────────

def test_memory_hit_rate_half():
    """2 runs: 1 con memory_blocks_injected=2, 1 con 0 → hit_rate=0.5."""
    from services.harness_health import compute_health

    t = _mk_ticket(80003)
    _mk_exec(t, status="completed", memory_blocks_injected=2)
    _mk_exec(t, status="completed", memory_blocks_injected=0)

    h = compute_health(window_days=14).to_dict()
    assert h["memory_hit_rate"] == 0.5


def test_memory_hit_rate_missing_key_treated_as_zero():
    """Ausencia de memory_blocks_injected en metadata no rompe y cuenta como 0."""
    from services.harness_health import compute_health

    t = _mk_ticket(80004)
    # Ningún run tiene la clave → hit_rate = 0.0
    _mk_exec(t, status="completed")
    _mk_exec(t, status="completed")

    h = compute_health(window_days=14).to_dict()
    assert h["memory_hit_rate"] == 0.0


def test_memory_hit_rate_null_when_no_runs():
    """Sin runs, memory_hit_rate es null (no dividir por cero)."""
    from services.harness_health import compute_health

    h = compute_health(window_days=14).to_dict()
    assert h["memory_hit_rate"] is None


# ── 3. runaway_stops ─────────────────────────────────────────────────────────

def test_runaway_stops_counts_runs_with_runaway_key():
    """runs con metadata["runaway"] presente (no null) → runaway_stops."""
    from services.harness_health import compute_health

    t = _mk_ticket(80005)
    _mk_exec(t, status="needs_review", runaway={"reason": "turns_exceeded", "turns": 50})
    _mk_exec(t, status="needs_review")     # sin runaway → no cuenta
    _mk_exec(t, status="completed")        # sin runaway → no cuenta

    h = compute_health(window_days=14).to_dict()
    assert h["runaway_stops"] == 1


def test_runaway_stops_zero_when_none():
    from services.harness_health import compute_health

    t = _mk_ticket(80006)
    _mk_exec(t, status="completed")

    h = compute_health(window_days=14).to_dict()
    assert h["runaway_stops"] == 0


# ── 4. cost_per_ticket_usd (top-level = suma total / tickets únicos) ─────────

def test_cost_per_ticket_sums_across_same_ticket():
    """2 runs sobre el mismo ticket: cost_per_ticket_usd = suma total (0.05)."""
    from services.harness_health import compute_health

    t = _mk_ticket(80007)
    _mk_exec(t, status="completed", cost=0.03)
    _mk_exec(t, status="completed", cost=0.02)

    h = compute_health(window_days=14).to_dict()
    # Ya existía como top-level en HarnessHealth.to_dict(); verificar valor.
    assert h["cost_per_ticket_usd"] == pytest.approx(0.05, abs=1e-4)


def test_cost_per_ticket_zero_when_no_cost_data():
    """Sin datos de costo en ningún run, cost_per_ticket en by_runtime = 0.0 (acumula 0)."""
    from services.harness_health import compute_health

    t = _mk_ticket(80008)
    _mk_exec(t, status="completed")  # sin cost → total_cost_usd acumula 0.0

    h = compute_health(window_days=14).to_dict()
    # by_runtime[runtime].cost_per_ticket = 0.0 / 1 ticket = 0.0 (no null)
    br = h["by_runtime"].get("claude_code_cli", {})
    assert br.get("cost_per_ticket") == 0.0


# ── 5. KPIs en by_runtime ────────────────────────────────────────────────────

def test_h8_kpis_appear_under_by_runtime():
    """autocorrection_saves, memory_hit_rate, runaway_stops aparecen en by_runtime."""
    from services.harness_health import compute_health

    t = _mk_ticket(80009)
    _mk_exec(t, status="completed", runtime="claude_code_cli",
             autocorrect_attempts=1, memory_blocks_injected=1,
             runaway={"reason": "cost_exceeded"})
    # Segundo runtime sin nada
    _mk_exec(t, status="completed", runtime="codex_cli",
             memory_blocks_injected=0)

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]

    # claude_code_cli: 1 save, hit_rate=1.0, 1 stop
    cl = br["claude_code_cli"]
    assert cl["autocorrection_saves"] == 1
    assert cl["memory_hit_rate"] == 1.0
    assert cl["runaway_stops"] == 1

    # codex_cli: 0 saves, hit_rate=0.0, 0 stops
    cx = br["codex_cli"]
    assert cx["autocorrection_saves"] == 0
    assert cx["memory_hit_rate"] == 0.0
    assert cx["runaway_stops"] == 0


def test_avg_contract_score_in_by_runtime():
    """avg_contract_score ya debe existir en by_runtime (retrocompat H0.2)."""
    from services.harness_health import compute_health

    t = _mk_ticket(80010)
    _mk_exec(t, status="completed", runtime="claude_code_cli", score=80)
    _mk_exec(t, status="completed", runtime="claude_code_cli", score=100)

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]["claude_code_cli"]
    assert br["avg_contract_score"] == pytest.approx(90.0, abs=0.1)


# ── 6. Sin regresión: shape anterior intacta ─────────────────────────────────

def test_no_regression_existing_fields():
    """Todos los campos que existían antes de H8 siguen presentes y con valor correcto."""
    from services.harness_health import compute_health

    t = _mk_ticket(80011)
    _mk_exec(t, status="completed", cost=0.10, score=75,
             autocorrect_attempts=1)
    _mk_exec(t, status="needs_review")
    _mk_exec(t, status="error")

    h = compute_health(window_days=14).to_dict()

    # Campos top-level obligatorios
    for field in (
        "window_days", "total_runs", "terminal_runs", "completed",
        "needs_review", "errored", "completed_without_intervention_rate",
        "autocorrection_rate", "error_rate", "total_cost_usd",
        "cost_per_ticket_usd", "runs_with_cost_telemetry",
        "avg_contract_score_by_agent", "model_distribution",
        "by_runtime", "legacy_claude_only",
    ):
        assert field in h, f"Campo '{field}' ausente en to_dict()"

    # Campos by_runtime (H0.2)
    br = h["by_runtime"]["claude_code_cli"]
    for field in ("runs", "completed_rate", "autocorrection_rate",
                  "cost_per_ticket", "avg_contract_score"):
        assert field in br, f"Campo by_runtime '{field}' ausente"

    assert h["total_runs"] == 3
    assert h["completed"] == 1
    assert h["needs_review"] == 1
    assert h["errored"] == 1
