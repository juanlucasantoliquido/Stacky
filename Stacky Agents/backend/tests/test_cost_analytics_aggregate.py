"""Plan 142 F1 — Tests del motor de agregación (services/cost_analytics.py).

PURO: construye ExecRecord/CostRow a mano (sin DB) y verifica summarize/burn/
breakdown + los helpers C5 (filters_echo/previous_period/burn_with_comparison).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.cost_analytics import (  # noqa: E402
    CostFilters,
    CostRow,
    ExecRecord,
    breakdown,
    burn,
    burn_with_comparison,
    filters_echo,
    previous_period,
    summarize,
)


def _rec(execution_id, *, runtime=None, model=None, cost_usd=None, cost_kind="unknown",
         tokens_in=None, tokens_out=None, cache_read=None, cache_savings=None,
         ticket_id=1, ado_id=None, project="P", agent_type="developer", status="completed",
         started_at=None):
    row = CostRow(runtime=runtime, model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                  cache_read_tokens=cache_read, cost_usd=cost_usd, cost_kind=cost_kind,
                  cache_savings_usd=cache_savings)
    return ExecRecord(execution_id=execution_id, ticket_id=ticket_id, ado_id=ado_id, project=project,
                       agent_type=agent_type, status=status, started_at=started_at, row=row)


def test_summarize_billable_excludes_nominal():
    records = [
        _rec(1, runtime="claude_code_cli", cost_usd=1.0, cost_kind="reported"),
        _rec(2, runtime="codex_cli", cost_usd=0.5, cost_kind="estimated"),
        _rec(3, runtime="github_copilot", cost_usd=2.0, cost_kind="nominal"),
    ]
    s = summarize(records)
    assert s["reported_usd"] == 1.0
    assert s["estimated_usd"] == 0.5
    assert s["nominal_usd"] == 2.0
    assert s["billable_usd"] == 1.5  # nominal EXCLUIDO


def test_summarize_no_double_count_invariant():
    records = [
        _rec(1, cost_usd=1.111111, cost_kind="reported"),
        _rec(2, cost_usd=2.222222, cost_kind="estimated"),
        _rec(3, cost_usd=3.333333, cost_kind="nominal"),
        _rec(4, cost_usd=None, cost_kind="unknown"),
    ]
    s = summarize(records)
    assert s["billable_usd"] == round(s["reported_usd"] + s["estimated_usd"], 6)
    assert s["runs_total"] == 4
    assert s["runs_with_cost"] == 3
    assert s["runs_without_cost"] == 1


def test_summarize_div0_guards():
    s = summarize([])
    assert s["pct_estimated"] == 0.0
    assert s["avg_cost_per_run_usd"] == 0.0
    assert s["cost_per_completed_task_usd"] == 0.0
    assert s["tokens_out_in_ratio"] == 0.0

    # tokens_out sin tokens_in -> ratio 0 (no ZeroDivisionError/inf)
    records = [_rec(1, tokens_in=None, tokens_out=500, cost_usd=None, cost_kind="unknown")]
    s2 = summarize(records)
    assert s2["tokens_out_in_ratio"] == 0.0


def test_burn_fills_empty_buckets():
    day1 = datetime(2026, 7, 1, 10, 0, 0)
    day3 = datetime(2026, 7, 3, 10, 0, 0)
    records = [
        _rec(1, cost_usd=1.0, cost_kind="reported", started_at=day1),
        _rec(2, cost_usd=2.0, cost_kind="reported", started_at=day3),
    ]
    b = burn(records, bucket="day")
    keys = [pt["bucket"] for pt in b["series"]]
    assert keys == ["2026-07-01", "2026-07-02", "2026-07-03"]
    # día del medio (sin runs) rellenado con ceros, no ausente.
    mid = b["series"][1]
    assert mid["billable_usd"] == 0.0
    assert mid["runs"] == 0


def test_burn_cumulative_monotonic():
    base = datetime(2026, 7, 1, 0, 0, 0)
    records = [
        _rec(1, cost_usd=1.0, cost_kind="reported", started_at=base),
        _rec(2, cost_usd=2.0, cost_kind="reported", started_at=base + timedelta(days=1)),
        _rec(3, cost_usd=3.0, cost_kind="estimated", started_at=base + timedelta(days=2)),
    ]
    b = burn(records, bucket="day")
    cumulative = [pt["cumulative_billable_usd"] for pt in b["series"]]
    assert cumulative == [1.0, 3.0, 6.0]
    # monótono no decreciente
    assert all(cumulative[i] <= cumulative[i + 1] for i in range(len(cumulative) - 1))


def test_burn_period_comparison_delta():
    base = datetime(2026, 7, 10, 0, 0, 0)
    cur = [_rec(1, cost_usd=15.0, cost_kind="reported", started_at=base)]
    prev = [_rec(2, cost_usd=10.0, cost_kind="reported", started_at=base - timedelta(days=7))]
    out = burn_with_comparison(cur, prev, bucket="day")
    pc = out["period_comparison"]
    assert pc["current_billable_usd"] == 15.0
    assert pc["previous_billable_usd"] == 10.0
    assert pc["delta_pct"] == 50.0  # (15-10)/10*100

    # prev==0 -> delta_pct 0.0 (guard div0), no crash.
    out2 = burn_with_comparison(cur, [], bucket="day")
    assert out2["period_comparison"]["previous_billable_usd"] == 0.0
    assert out2["period_comparison"]["delta_pct"] == 0.0


def test_breakdown_sorted_desc_by_billable():
    records = [
        _rec(1, runtime="claude_code_cli", cost_usd=1.0, cost_kind="reported"),
        _rec(2, runtime="codex_cli", cost_usd=5.0, cost_kind="estimated"),
        _rec(3, runtime="github_copilot", cost_usd=100.0, cost_kind="nominal"),
    ]
    out = breakdown(records, "runtime")
    keys = [g["key"] for g in out["groups"]]
    # codex_cli (5.0 billable) antes que claude_code_cli (1.0); copilot (nominal,
    # billable=0.0) al final pese a tener el cost_usd nominal más alto.
    assert keys == ["codex_cli", "claude_code_cli", "github_copilot"]


def test_breakdown_ticket_and_day_keys():
    day = datetime(2026, 7, 5, 12, 0, 0)
    records = [
        _rec(1, ticket_id=42, cost_usd=1.0, cost_kind="reported", started_at=day),
        _rec(2, ticket_id=42, cost_usd=2.0, cost_kind="reported", started_at=day),
    ]
    out_ticket = breakdown(records, "ticket")
    assert out_ticket["groups"][0]["key"] == "42"
    assert out_ticket["groups"][0]["runs"] == 2

    out_day = breakdown(records, "day")
    assert out_day["groups"][0]["key"] == "2026-07-05"


def test_empty_records_no_crash():
    assert summarize([])["runs_total"] == 0
    assert burn([], bucket="day") == {"bucket": "day", "series": []}
    assert breakdown([], "runtime") == {"dimension": "runtime", "groups": []}


def test_previous_period_explicit_range_shifts_by_span():
    d1 = datetime(2026, 7, 10)
    d2 = datetime(2026, 7, 15)  # span = 5 días
    f = CostFilters(date_from=d1, date_to=d2)
    p = previous_period(f)
    assert p.date_to == d1
    assert p.date_from == d1 - timedelta(days=5)


def test_previous_period_days_mode_shifts_by_days():
    f = CostFilters(days=7, date_from=None, date_to=None)
    p = previous_period(f)
    now = datetime.utcnow()
    # tolerancia de unos segundos: previous_period() llama a su propio utcnow().
    assert abs((p.date_to - (now - timedelta(days=7))).total_seconds()) < 5
    assert abs((p.date_from - (now - timedelta(days=14))).total_seconds()) < 5


def test_filters_echo_resolves_effective_range():
    f = CostFilters(days=10)
    echo = filters_echo(f)
    assert echo["days_effective"] == 10
    assert echo["date_from"] is not None
    assert echo["date_to"] is not None
    # from/to explícitas: days_effective refleja el span real, no el default days=30.
    f2 = CostFilters(date_from=datetime(2026, 7, 1), date_to=datetime(2026, 7, 4), days=30)
    echo2 = filters_echo(f2)
    assert echo2["days_effective"] == 3
