"""Plan 46 F0 — Agregador puro de salud operativa."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.operational_health import (  # noqa: E402
    _age_minutes,
    _coerce_cost,
    aggregate_operational_health,
)

NOW = "2026-06-19T12:00:00"


def _run(**kw):
    base = {"id": 1, "ticket_id": 1, "agent_type": "business", "status": "completed",
            "started_at": NOW, "metadata": {}, "error_message": None}
    base.update(kw)
    return base


def test_empty_runs_returns_empty_buckets():
    r = aggregate_operational_health([], NOW)
    assert r["summary"]["scanned"] == 0
    for b in ("needs_review", "failed", "expensive", "zombie"):
        assert r[b] == []


def test_needs_review_bucket_and_stale_flag():
    runs = [
        _run(id=1, status="needs_review", started_at="2026-06-19T11:00:00"),  # fresca
        _run(id=2, status="needs_review", started_at="2026-06-10T12:00:00"),  # 9 días
    ]
    r = aggregate_operational_health(runs, NOW)
    assert r["summary"]["needs_review_pending"] == 2
    assert r["summary"]["needs_review_stale"] == 1
    # la más vieja primero
    assert r["needs_review"][0]["id"] == 2
    assert r["needs_review"][0]["stale"] is True


def test_failed_bucket_uses_failure_kind_and_defaults_unknown():
    runs = [
        _run(id=1, status="failed", metadata={"failure_kind": "timeout"}),
        _run(id=2, status="error", metadata={}),
    ]
    r = aggregate_operational_health(runs, NOW)
    kinds = {row["id"]: row["failure_kind"] for row in r["failed"]}
    assert kinds[1] == "timeout"
    assert kinds[2] == "unknown"


def test_expensive_bucket_respects_threshold():
    runs = [
        _run(id=1, metadata={"cost": 2.5, "model": "opus"}),
        _run(id=2, metadata={"cost": 0.2}),
    ]
    r = aggregate_operational_health(runs, NOW, {"cost_usd": 1.0})
    ids = [row["id"] for row in r["expensive"]]
    assert ids == [1]


def test_coerce_cost_handles_float_and_dict_and_missing():
    assert _coerce_cost({"cost": 1.5}) == 1.5
    assert _coerce_cost({"cost": {"total": 3.0, "reported": 1.0}}) == 3.0
    assert _coerce_cost({"cost": {"reported": 1.0}}) == 1.0
    assert _coerce_cost({}) is None
    assert _coerce_cost({"cost": "abc"}) is None


def test_zombie_bucket_detects_old_running():
    runs = [
        _run(id=1, status="running", started_at="2026-06-19T08:00:00"),  # 240 min
        _run(id=2, status="running", started_at="2026-06-19T11:50:00"),  # 10 min
    ]
    r = aggregate_operational_health(runs, NOW, {"zombie_minutes": 120})
    ids = [row["id"] for row in r["zombie"]]
    assert ids == [1]
    assert r["zombie"][0]["age_minutes"] == 240.0


def test_status_is_case_insensitive():
    runs = [_run(id=1, status="Needs_Review", started_at=NOW)]
    r = aggregate_operational_health(runs, NOW)
    assert r["summary"]["needs_review_pending"] == 1


def test_bucket_caps_at_max_rows_per_bucket():
    runs = [_run(id=i, status="failed") for i in range(30)]
    r = aggregate_operational_health(runs, NOW, {"max_rows_per_bucket": 20})
    assert len(r["failed"]) == 20
    assert r["summary"]["failed"] == 30


def test_expensive_cost_by_model_and_runtime():
    runs = [
        _run(id=1, metadata={"cost": 2.0, "model": "opus", "runtime": "claude_code_cli"}),
        _run(id=2, metadata={"cost": 3.0, "model": "opus", "runtime": "claude_code_cli"}),
    ]
    r = aggregate_operational_health(runs, NOW, {"cost_usd": 1.0})
    assert r["expensive_cost_by_model"]["opus"] == 5.0
    assert r["expensive_cost_by_runtime"]["claude_code_cli"] == 5.0


def test_age_minutes_handles_none_and_unparseable():
    assert _age_minutes(NOW, None) is None
    assert _age_minutes(NOW, "not-a-date") is None
    assert _age_minutes(NOW, "2026-06-19T11:00:00") == 60.0
