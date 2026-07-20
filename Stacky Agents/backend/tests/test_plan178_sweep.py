"""Plan 178 F2/F6 — Vigía: sweep determinista (due, jitter, backoff, presupuesto,
busy-skip, cosecha idempotente) + guard del loop de background.

Ver Stacky Agents/docs/178_PLAN_RADAR_DE_AMBIENTES_...md §F2/§F6.
Reloj inyectado; cero red; create_run/list_runs/get_run monkeypatcheados.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import services.dbcompare_watch as dbcompare_watch
import services.dbcompare_baseline as dbcompare_baseline
import services.dbcompare_registry as dbcompare_registry
import services.dbcompare_snapshot as dbcompare_snapshot
import services.dbcompare_runs as dbcompare_runs

_NOW = datetime(2026, 7, 18, 13, 0, 0, tzinfo=timezone.utc)


class _RunsStub:
    def __init__(self):
        self.create_calls = []
        self.index = {}
        self.today_runs = []
        self.n = 0
        self.raise_on_create = None

    def create_run(self, source, target, *, mode="fresh", initiated_by="operator"):
        self.create_calls.append((source, target, mode, initiated_by))
        if self.raise_on_create is not None:
            raise self.raise_on_create
        self.n += 1
        return {"run_id": f"run_test_{self.n}"}

    def list_runs(self, limit=50):
        return list(self.today_runs)

    def get_run(self, run_id):
        return self.index.get(run_id)


@pytest.fixture
def env(tmp_path, monkeypatch):
    import config as _config

    monkeypatch.setattr(dbcompare_watch, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dbcompare_baseline, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(_config.config, "STACKY_DB_COMPARE_ENABLED", True, raising=False)
    monkeypatch.setattr(_config.config, "STACKY_DB_COMPARE_RADAR_ENABLED", True, raising=False)

    runs = _RunsStub()
    monkeypatch.setattr(dbcompare_runs, "create_run", runs.create_run)
    monkeypatch.setattr(dbcompare_runs, "list_runs", runs.list_runs)
    monkeypatch.setattr(dbcompare_runs, "get_run", runs.get_run)
    return {"tmp_path": tmp_path, "runs": runs, "monkeypatch": monkeypatch, "config": _config}


def _seed_watch(tmp_path, **overrides):
    base = {
        "watch_id": "DEV__TEST", "source_alias": "DEV", "target_alias": "TEST",
        "enabled": True, "created_at": "2026-07-18T10:00:00Z",
        "last_attempt_at": None, "last_run_id": None, "last_done_run_id": None,
        "last_harvested_run_id": None, "last_summary": None, "consecutive_errors": 0,
    }
    base.update(overrides)
    watch_dir = tmp_path / "db_compare" / "watch"
    watch_dir.mkdir(parents=True, exist_ok=True)
    (watch_dir / "watches.json").write_text(
        json.dumps({"version": 1, "watches": [base]}, ensure_ascii=False), encoding="utf-8"
    )
    return base


def _the_watch(tmp_path):
    return dbcompare_watch.list_watches()[0]


# ── no-op ────────────────────────────────────────────────────────────────

def test_sweep_noop_flag_off(env):
    env["monkeypatch"].setattr(env["config"].config, "STACKY_DB_COMPARE_RADAR_ENABLED", False, raising=False)
    _seed_watch(env["tmp_path"])
    assert dbcompare_watch.run_watch_sweep_once(now=_NOW) == 0
    assert env["runs"].create_calls == []


def test_sweep_noop_sin_watches(env):
    def _boom(*a, **k):
        raise AssertionError("no debe conectar sin watches")

    env["monkeypatch"].setattr(dbcompare_snapshot, "take_snapshot", _boom)
    env["monkeypatch"].setattr(dbcompare_registry, "get_credential", _boom)
    assert dbcompare_watch.run_watch_sweep_once(now=_NOW) == 0
    assert env["runs"].create_calls == []


# ── due / launch ───────────────────────────────────────────────────────────

def test_due_lanza_create_run_fresh(env):
    _seed_watch(env["tmp_path"])  # last_attempt_at None → due
    launched = dbcompare_watch.run_watch_sweep_once(now=_NOW)
    assert launched == 1
    assert env["runs"].create_calls == [("DEV", "TEST", "fresh", "watch")]
    w = _the_watch(env["tmp_path"])
    assert w["last_run_id"] == "run_test_1"
    assert w["last_attempt_at"] == "2026-07-18T13:00:00Z"


def test_no_due_no_lanza(env):
    last = (_NOW - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _seed_watch(env["tmp_path"], last_attempt_at=last)
    assert dbcompare_watch.run_watch_sweep_once(now=_NOW) == 0
    assert env["runs"].create_calls == []


def test_jitter_determinista(env):
    a = dbcompare_watch._jitter_seconds("DEV__TEST", 60)
    b = dbcompare_watch._jitter_seconds("DEV__TEST", 60)
    assert a == b
    assert 0 <= a < 720


def test_backoff_exponencial(env):
    # consecutive_errors=2 → effective = 60 * 2^2 = 240 min.
    w3 = {"watch_id": "DEV__TEST", "consecutive_errors": 2,
          "last_attempt_at": (_NOW - timedelta(minutes=180)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert dbcompare_watch._is_due(w3, _NOW, 60) is False
    w5 = {"watch_id": "DEV__TEST", "consecutive_errors": 2,
          "last_attempt_at": (_NOW - timedelta(minutes=300)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert dbcompare_watch._is_due(w5, _NOW, 60) is True


def test_budget_diario(env):
    env["monkeypatch"].setattr(env["config"].config, "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY", 1, raising=False)
    env["runs"].today_runs = [
        {"initiated_by": "watch", "started_at": "2026-07-18T09:00:00Z"}
    ]
    _seed_watch(env["tmp_path"])  # due
    assert dbcompare_watch.run_watch_sweep_once(now=_NOW) == 0
    assert env["runs"].create_calls == []


def test_clamps_de_flags(env):
    mp, cfg = env["monkeypatch"], env["config"].config
    mp.setattr(cfg, "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN", 100000, raising=False)
    assert dbcompare_watch._interval_minutes() == 1440
    mp.setattr(cfg, "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN", 2, raising=False)
    assert dbcompare_watch._interval_minutes() == 5
    mp.setattr(cfg, "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY", 500, raising=False)
    assert dbcompare_watch._max_runs_per_day() == 100
    mp.setattr(cfg, "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY", 0, raising=False)
    assert dbcompare_watch._max_runs_per_day() == 1
    mp.setattr(cfg, "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN", "abc", raising=False)
    mp.setattr(cfg, "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY", "abc", raising=False)
    assert dbcompare_watch._interval_minutes() == 60
    assert dbcompare_watch._max_runs_per_day() == 48


def test_busy_skip_sin_error(env):
    _seed_watch(env["tmp_path"])
    env["runs"].raise_on_create = dbcompare_runs.DbCompareBusyError("ocupado")
    assert dbcompare_watch.run_watch_sweep_once(now=_NOW) == 0
    w = _the_watch(env["tmp_path"])
    assert w["consecutive_errors"] == 0
    assert w["last_run_id"] is None


def test_alias_borrado_deshabilita_watch(env):
    _seed_watch(env["tmp_path"])
    env["runs"].raise_on_create = dbcompare_runs.DbCompareRunError("ambiente desconocido")
    dbcompare_watch.run_watch_sweep_once(now=_NOW)
    w = _the_watch(env["tmp_path"])
    assert w["enabled"] is False


def test_run_activo_no_encima(env):
    _seed_watch(env["tmp_path"], last_run_id="run_running", last_harvested_run_id=None)
    env["runs"].index["run_running"] = {"run_id": "run_running", "status": "running"}
    assert dbcompare_watch.run_watch_sweep_once(now=_NOW) == 0
    assert env["runs"].create_calls == []


# ── cosecha (harvest) ──────────────────────────────────────────────────────

def test_harvest_done_resetea_backoff(env):
    _seed_watch(
        env["tmp_path"], consecutive_errors=3, last_run_id="run_done",
        last_attempt_at="2026-07-18T13:00:00Z",  # no due → aislar cosecha
    )
    env["runs"].index["run_done"] = {
        "run_id": "run_done", "status": "done",
        "summary": {"by_severity": {"info": 0, "warn": 2, "danger": 0}, "parity_score": 98.5},
        "source_snapshot_id": "s1", "target_snapshot_id": "t1",
    }
    dbcompare_watch.run_watch_sweep_once(now=_NOW)
    w = _the_watch(env["tmp_path"])
    assert w["consecutive_errors"] == 0
    assert w["last_done_run_id"] == "run_done"
    assert w["last_harvested_run_id"] == "run_done"
    assert w["last_summary"]["by_severity"]["warn"] == 2


def test_harvest_error_incrementa_backoff(env):
    _seed_watch(
        env["tmp_path"], last_run_id="run_err", last_attempt_at="2026-07-18T13:00:00Z",
    )
    env["runs"].index["run_err"] = {"run_id": "run_err", "status": "error", "error": "boom"}
    dbcompare_watch.run_watch_sweep_once(now=_NOW)
    w = _the_watch(env["tmp_path"])
    assert w["consecutive_errors"] == 1
    assert w["last_harvested_run_id"] == "run_err"


def test_harvest_error_es_idempotente(env):
    _seed_watch(
        env["tmp_path"], last_run_id="run_err", last_attempt_at="2026-07-18T13:00:00Z",
    )
    env["runs"].index["run_err"] = {"run_id": "run_err", "status": "error", "error": "boom"}
    calls = {"n": 0}
    orig = dbcompare_watch._append_event_watch_error

    def _counting(watch, run):
        calls["n"] += 1
        return orig(watch, run)

    env["monkeypatch"].setattr(dbcompare_watch, "_append_event_watch_error", _counting)
    dbcompare_watch.run_watch_sweep_once(now=_NOW)
    dbcompare_watch.run_watch_sweep_once(now=_NOW)
    w = _the_watch(env["tmp_path"])
    assert w["consecutive_errors"] == 1
    assert calls["n"] == 1


def test_harvest_stale_es_idempotente(env):
    _seed_watch(
        env["tmp_path"], last_run_id="run_stale", last_attempt_at="2026-07-18T13:00:00Z",
    )
    env["runs"].index["run_stale"] = {"run_id": "run_stale", "status": "running", "stale": True}
    calls = {"n": 0}
    orig = dbcompare_watch._append_event_watch_error

    def _counting(watch, run):
        calls["n"] += 1
        return orig(watch, run)

    env["monkeypatch"].setattr(dbcompare_watch, "_append_event_watch_error", _counting)
    dbcompare_watch.run_watch_sweep_once(now=_NOW)
    dbcompare_watch.run_watch_sweep_once(now=_NOW)
    w = _the_watch(env["tmp_path"])
    assert w["consecutive_errors"] == 1
    assert calls["n"] == 1


# ── F6: loop de background ─────────────────────────────────────────────────

def test_loop_no_arranca_bajo_pytest():
    from app import create_app

    create_app()
    names = [t.name for t in threading.enumerate()]
    assert "stacky-dbcompare-watch-daemon" not in names


def test_sweep_seguro_ante_excepcion(env):
    def _boom():
        raise RuntimeError("disco lleno")

    env["monkeypatch"].setattr(dbcompare_watch, "list_watches", _boom)
    with pytest.raises(RuntimeError):
        dbcompare_watch.run_watch_sweep_once(now=_NOW)
