"""F3.3 — Tests del score de salud del arnés.

Verifica que compute_health agrega correctamente datos ya persistidos por
Fases 1-2 (status, autocorrect, telemetría de costo, contract score, modelo)
y que solo cuenta runs del runtime claude_code_cli.
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
    return _mk_ticket_project(ado_id, project="RSPacifico")


def _mk_ticket_project(ado_id: int, *, project: str = "RSPacifico") -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project=project, title=f"t-{ado_id}",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _mk_cli_exec(ticket_id: int, *, status: str, agent_type: str = "developer",
                 attempts: int = 0, cost: float | None = None,
                 score: int | None = None, model: str = "claude-sonnet-4-6",
                 runtime: str = "claude_code_cli", days_ago: float = 1,
                 memory_blocks: int | None = None, runaway: dict | None = None,
                 codex_cost: float | None = None) -> int:
    from db import session_scope
    from models import AgentExecution

    md: dict = {"runtime": runtime, "claude_code_model": model}
    if attempts:
        md["autocorrect"] = {"attempts": attempts}
    if cost is not None:
        md["claude_telemetry"] = {"total_cost_usd": cost}
    if codex_cost is not None:
        md["harness_telemetry"] = {"total_cost_usd": codex_cost}
    if memory_blocks is not None:
        md["memory_blocks_injected"] = memory_blocks
    if runaway is not None:
        md["runaway"] = runaway
    cr = json.dumps({"score": score, "passed": score is not None and score >= 70}) if score is not None else None

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


def test_completed_without_intervention_and_autocorrection_rates():
    from services.harness_health import compute_health

    t = _mk_ticket(70001)
    _mk_cli_exec(t, status="completed", attempts=0, cost=0.10)
    _mk_cli_exec(t, status="completed", attempts=2, cost=0.20)  # autocorregido
    _mk_cli_exec(t, status="needs_review", attempts=0)
    _mk_cli_exec(t, status="error", attempts=0)

    h = compute_health(window_days=14).to_dict()
    assert h["terminal_runs"] == 4
    assert h["completed"] == 2
    assert h["needs_review"] == 1
    assert h["errored"] == 1
    # 1 de 4 terminales cerró completed sin intervención
    assert h["completed_without_intervention_rate"] == 0.25
    # 1 de 4 terminales usó autocorrección
    assert h["autocorrection_rate"] == 0.25


def test_cost_and_model_distribution():
    from services.harness_health import compute_health

    t = _mk_ticket(70002)
    _mk_cli_exec(t, status="completed", cost=0.30, model="claude-haiku-4-5")
    _mk_cli_exec(t, status="completed", cost=0.70, model="claude-sonnet-4-6")

    h = compute_health(window_days=14).to_dict()
    assert h["total_cost_usd"] == 1.0
    assert h["cost_per_ticket_usd"] == 1.0  # 1 ticket
    assert h["model_distribution"]["claude-haiku-4-5"] == 1
    assert h["model_distribution"]["claude-sonnet-4-6"] == 1


def test_avg_contract_score_by_agent():
    from services.harness_health import compute_health

    t = _mk_ticket(70003)
    _mk_cli_exec(t, status="completed", agent_type="qa", score=80)
    _mk_cli_exec(t, status="completed", agent_type="qa", score=100)
    _mk_cli_exec(t, status="completed", agent_type="developer", score=60)

    h = compute_health(window_days=14).to_dict()
    assert h["avg_contract_score_by_agent"]["qa"] == 90.0
    assert h["avg_contract_score_by_agent"]["developer"] == 60.0


def test_legacy_claude_only_ignores_other_runtimes():
    """H0.2 retro-compat: legacy_claude_only solo agrega claude_code_cli."""
    from services.harness_health import compute_health

    t = _mk_ticket(70004)
    _mk_cli_exec(t, status="completed", runtime="github_copilot", cost=5.0)
    _mk_cli_exec(t, status="completed", runtime="claude_code_cli", cost=0.10)

    h = compute_health(window_days=14).to_dict()
    # Top-level ahora es el agregado global (H0.2)
    assert h["total_runs"] == 2
    assert round(h["total_cost_usd"], 2) == 5.10
    # legacy_claude_only preserva el comportamiento anterior
    lco = h["legacy_claude_only"]
    assert lco["total_runs"] == 1
    assert lco["total_cost_usd"] == 0.10


def test_window_excludes_old_runs():
    from services.harness_health import compute_health

    t = _mk_ticket(70005)
    _mk_cli_exec(t, status="completed", days_ago=30, cost=1.0)
    _mk_cli_exec(t, status="completed", days_ago=2, cost=0.10)

    h = compute_health(window_days=14).to_dict()
    assert h["total_runs"] == 1
    assert h["total_cost_usd"] == 0.10


# ── H0.2 — multi-runtime ────────────────────────────────────────────────────

def test_by_runtime_contains_all_runtimes():
    """H0.2: compute_health con runtimes=None agrega los 3 runtimes en by_runtime."""
    from services.harness_health import compute_health

    t = _mk_ticket(70010)
    _mk_cli_exec(t, status="completed", runtime="codex_cli", cost=0.05)
    _mk_cli_exec(t, status="needs_review", runtime="claude_code_cli", cost=0.10)

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]
    assert "codex_cli" in br
    assert "claude_code_cli" in br
    assert br["codex_cli"]["runs"] == 1
    assert br["claude_code_cli"]["runs"] == 1


def test_by_runtime_completed_rate():
    """H0.2: completed_rate por runtime se calcula independientemente."""
    from services.harness_health import compute_health

    t = _mk_ticket(70011)
    _mk_cli_exec(t, status="completed", runtime="codex_cli")
    _mk_cli_exec(t, status="error", runtime="codex_cli")
    _mk_cli_exec(t, status="completed", runtime="claude_code_cli")

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]
    # codex: 1 completed de 2 terminales = 0.5
    assert br["codex_cli"]["completed_rate"] == 0.5
    # claude: 1 completed de 1 terminal = 1.0
    assert br["claude_code_cli"]["completed_rate"] == 1.0


def test_by_runtime_cost_per_ticket():
    """H0.2: cost_per_ticket por runtime."""
    from services.harness_health import compute_health

    t = _mk_ticket(70012)
    _mk_cli_exec(t, status="completed", runtime="codex_cli", cost=0.20)
    _mk_cli_exec(t, status="completed", runtime="codex_cli", cost=0.30)

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]
    assert br["codex_cli"]["cost_per_ticket"] == 0.5


def test_by_runtime_filter():
    """H0.2: compute_health(runtimes=["codex_cli"]) solo agrega ese runtime."""
    from services.harness_health import compute_health

    t = _mk_ticket(70013)
    _mk_cli_exec(t, status="completed", runtime="codex_cli")
    _mk_cli_exec(t, status="completed", runtime="claude_code_cli")
    _mk_cli_exec(t, status="completed", runtime="github_copilot")

    h = compute_health(window_days=14, runtimes=["codex_cli"]).to_dict()
    br = h["by_runtime"]
    assert list(br.keys()) == ["codex_cli"]


def test_top_level_fields_are_global_aggregate():
    """H0.2: los campos top-level total_runs/total_cost_usd agregan todos los runtimes."""
    from services.harness_health import compute_health

    t = _mk_ticket(70014)
    _mk_cli_exec(t, status="completed", runtime="codex_cli", cost=0.10)
    _mk_cli_exec(t, status="completed", runtime="claude_code_cli", cost=0.20)
    _mk_cli_exec(t, status="completed", runtime="github_copilot", cost=0.50)

    h = compute_health(window_days=14).to_dict()
    assert h["total_runs"] == 3
    assert round(h["total_cost_usd"], 2) == 0.80


def test_legacy_claude_only_field_preserved():
    """H0.2: campo legacy_claude_only mantiene retrocompat con consumidores que asumen solo-claude."""
    from services.harness_health import compute_health

    t = _mk_ticket(70015)
    _mk_cli_exec(t, status="completed", runtime="claude_code_cli", cost=0.10)
    _mk_cli_exec(t, status="completed", runtime="codex_cli", cost=0.50)

    h = compute_health(window_days=14).to_dict()
    lco = h["legacy_claude_only"]
    assert lco["total_runs"] == 1
    assert lco["total_cost_usd"] == 0.10


# ── H8 — KPIs de valor agregado ─────────────────────────────────────────────

def test_h8_autocorrection_saves_global():
    """H8: autocorrection_saves top-level = runs donde autocorrect invocado Y completó."""
    from services.harness_health import compute_health

    t = _mk_ticket(80001)
    _mk_cli_exec(t, status="completed", attempts=2)   # save
    _mk_cli_exec(t, status="completed", attempts=0)   # sin autocorrect → no es save
    _mk_cli_exec(t, status="needs_review", attempts=1)  # autocorrect pero no completed → no es save
    _mk_cli_exec(t, status="error", attempts=3)        # error → no es save

    h = compute_health(window_days=14).to_dict()
    assert h["autocorrection_saves"] == 1


def test_h8_autocorrection_saves_by_runtime():
    """H8: autocorrection_saves se desglosa por runtime en by_runtime."""
    from services.harness_health import compute_health

    t = _mk_ticket(80002)
    _mk_cli_exec(t, status="completed", attempts=1, runtime="claude_code_cli")
    _mk_cli_exec(t, status="completed", attempts=2, runtime="codex_cli")
    _mk_cli_exec(t, status="needs_review", attempts=1, runtime="claude_code_cli")

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]
    assert br["claude_code_cli"]["autocorrection_saves"] == 1
    assert br["codex_cli"]["autocorrection_saves"] == 1


def test_h8_memory_hit_rate_global():
    """H8: memory_hit_rate = fracción de runs con memory_blocks_injected >= 1."""
    from services.harness_health import compute_health

    t = _mk_ticket(80003)
    _mk_cli_exec(t, status="completed", memory_blocks=3)
    _mk_cli_exec(t, status="completed", memory_blocks=0)   # 0 → no cuenta
    _mk_cli_exec(t, status="completed", memory_blocks=None)  # ausente → no cuenta
    _mk_cli_exec(t, status="completed", memory_blocks=1)

    h = compute_health(window_days=14).to_dict()
    # 2 de 4 runs tienen memoria inyectada
    assert h["memory_hit_rate"] == 0.5


def test_h8_memory_hit_rate_by_runtime():
    """H8: memory_hit_rate se desglosa por runtime en by_runtime."""
    from services.harness_health import compute_health

    t = _mk_ticket(80004)
    _mk_cli_exec(t, status="completed", memory_blocks=2, runtime="claude_code_cli")
    _mk_cli_exec(t, status="completed", memory_blocks=0, runtime="claude_code_cli")
    _mk_cli_exec(t, status="completed", memory_blocks=1, runtime="codex_cli")

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]
    assert br["claude_code_cli"]["memory_hit_rate"] == 0.5
    assert br["codex_cli"]["memory_hit_rate"] == 1.0


def test_h8_runaway_stops_global():
    """H8: runaway_stops = runs con metadata['runaway'] presente y no nulo."""
    from services.harness_health import compute_health

    t = _mk_ticket(80005)
    _mk_cli_exec(t, status="needs_review", runaway={"reason": "cost_exceeded", "cost_usd": 2.5})
    _mk_cli_exec(t, status="completed")            # sin runaway
    _mk_cli_exec(t, status="needs_review", runaway={"reason": "turns_exceeded"})

    h = compute_health(window_days=14).to_dict()
    assert h["runaway_stops"] == 2


def test_h8_runaway_stops_by_runtime():
    """H8: runaway_stops se desglosa por runtime en by_runtime."""
    from services.harness_health import compute_health

    t = _mk_ticket(80006)
    _mk_cli_exec(t, status="needs_review", runaway={"reason": "cost"}, runtime="claude_code_cli")
    _mk_cli_exec(t, status="needs_review", runaway={"reason": "turns"}, runtime="codex_cli")
    _mk_cli_exec(t, status="completed", runtime="claude_code_cli")

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]
    assert br["claude_code_cli"]["runaway_stops"] == 1
    assert br["codex_cli"]["runaway_stops"] == 1


def test_h8_no_runaway_field_absent():
    """H8: si ningún run tiene runaway, runaway_stops es 0 (no error)."""
    from services.harness_health import compute_health

    t = _mk_ticket(80007)
    _mk_cli_exec(t, status="completed")
    _mk_cli_exec(t, status="error")

    h = compute_health(window_days=14).to_dict()
    assert h["runaway_stops"] == 0
    assert "runaway_stops" in h  # campo siempre presente


def test_h8_cost_per_ticket_null_when_no_cost():
    """H8: cost_per_ticket es null en by_runtime cuando no hay telemetría de costo (codex sin H2.2)."""
    from services.harness_health import compute_health

    t = _mk_ticket(80008)
    _mk_cli_exec(t, status="completed", runtime="codex_cli")  # sin cost

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]
    assert br["codex_cli"]["cost_per_ticket"] is None


def test_h8_cost_per_ticket_codex_harness_telemetry():
    """H8: cost_per_ticket en codex se toma de harness_telemetry (H2.2)."""
    from services.harness_health import compute_health

    t = _mk_ticket(80009)
    _mk_cli_exec(t, status="completed", runtime="codex_cli", codex_cost=0.15)

    h = compute_health(window_days=14).to_dict()
    br = h["by_runtime"]
    assert br["codex_cli"]["cost_per_ticket"] == 0.15


def test_h8_by_project_groups_runs():
    """H8: by_project agrupa runs por proyecto del ticket."""
    from services.harness_health import compute_health

    t1 = _mk_ticket_project(90001, project="ProjectA")
    t2 = _mk_ticket_project(90002, project="ProjectB")
    _mk_cli_exec(t1, status="completed")
    _mk_cli_exec(t1, status="error")
    _mk_cli_exec(t2, status="completed")

    h = compute_health(window_days=14).to_dict()
    bp = h["by_project"]
    assert "ProjectA" in bp
    assert "ProjectB" in bp
    assert bp["ProjectA"]["runs"] == 2
    assert bp["ProjectB"]["runs"] == 1


def test_h8_by_project_completed_rate():
    """H8: by_project.completed_rate se calcula por proyecto."""
    from services.harness_health import compute_health

    t = _mk_ticket_project(90003, project="ProjectC")
    _mk_cli_exec(t, status="completed")
    _mk_cli_exec(t, status="error")

    h = compute_health(window_days=14).to_dict()
    bp = h["by_project"]
    assert bp["ProjectC"]["completed_rate"] == 0.5


def test_h8_by_project_field_always_present():
    """H8: by_project siempre está en la respuesta (puede ser vacío si no hay runs)."""
    from services.harness_health import compute_health

    h = compute_health(window_days=14).to_dict()
    assert "by_project" in h
    assert isinstance(h["by_project"], dict)
