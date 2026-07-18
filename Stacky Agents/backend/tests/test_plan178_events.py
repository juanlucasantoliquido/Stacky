"""Plan 178 F3 — DriftEvent v1: detección de transiciones y avisos locales.

Ver Stacky Agents/docs/178_PLAN_RADAR_DE_AMBIENTES_...md §F3.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import services.dbcompare_watch as dbcompare_watch
import services.dbcompare_baseline as dbcompare_baseline
import services.dbcompare_runs as dbcompare_runs


class _Clock:
    def __init__(self):
        self.t = datetime(2026, 7, 18, 13, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(dbcompare_watch, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dbcompare_baseline, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dbcompare_watch, "_now", _Clock())
    return tmp_path


_W = {"watch_id": "DEV__TEST", "source_alias": "DEV", "target_alias": "TEST"}


def _sev(info=0, warn=0, danger=0, parity=100.0):
    return {"by_severity": {"info": info, "warn": warn, "danger": danger}, "parity_score": parity}


def test_append_y_list_orden_desc(store):
    dbcompare_watch._append_event("drift_new", watch=_W, run_id="r1", detail=_sev(warn=1))
    dbcompare_watch._append_event("drift_cleared", watch=_W, run_id="r2", detail=_sev())
    events = dbcompare_watch.list_events(10)
    assert len(events) == 2
    assert events[0]["kind"] == "drift_cleared"  # más nuevo primero
    assert events[1]["kind"] == "drift_new"


def test_cap_200(store):
    for i in range(205):
        dbcompare_watch._append_event("watch_error", watch=_W, run_id=f"r{i}", detail={"error": str(i)})
    events = dbcompare_watch.list_events(300)
    assert len(events) == 200
    assert events[0]["detail"]["error"] == "204"  # el más nuevo retenido


def test_kind_desconocido_lanza_valueerror(store):
    with pytest.raises(ValueError):
        dbcompare_watch._append_event("nope", watch=None, run_id=None, detail={})


def test_mark_read_ids_y_all(store):
    e1 = dbcompare_watch._append_event("drift_new", watch=_W, run_id="r1", detail=_sev(warn=1))
    dbcompare_watch._append_event("drift_worse", watch=_W, run_id="r2", detail=_sev(danger=1))
    assert dbcompare_watch.mark_events_read([e1["event_id"]]) == 1
    assert dbcompare_watch.unread_count() == 1
    assert dbcompare_watch.mark_events_read(None) == 1
    assert dbcompare_watch.unread_count() == 0


def test_unread_count(store):
    dbcompare_watch._append_event("drift_new", watch=_W, run_id="r1", detail=_sev(warn=1))
    dbcompare_watch._append_event("drift_new", watch=_W, run_id="r2", detail=_sev(warn=1))
    assert dbcompare_watch.unread_count() == 2


def _seed_watch(tmp_path, **overrides):
    import json

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


def test_dedup_transiciones(store, monkeypatch):
    # KPI-5: una transición sin-diff→con-diff emite EXACTAMENTE 1 drift_new;
    # re-cosechar el MISMO run o un run idéntico → 0 eventos nuevos.
    seed = _seed_watch(store, last_run_id="run1")
    index = {"run1": {"run_id": "run1", "status": "done", "summary": _sev(warn=3),
                      "source_snapshot_id": "s1", "target_snapshot_id": "t1"}}
    monkeypatch.setattr(dbcompare_runs, "get_run", lambda rid: index.get(rid))

    dbcompare_watch._harvest_watch(dict(seed))
    assert [e["kind"] for e in dbcompare_watch.list_events(50)] == ["drift_new"]

    # Segunda cosecha del MISMO run (last_harvested ya == run1) → sin emisión.
    w = dbcompare_watch.list_watches()[0]
    dbcompare_watch._harvest_watch(dict(w))
    assert len(dbcompare_watch.list_events(50)) == 1

    # Tercer run con summary idéntico → sin nueva transición.
    dbcompare_watch._update_watch("DEV__TEST", last_run_id="run2")
    index["run2"] = {"run_id": "run2", "status": "done", "summary": _sev(warn=3),
                     "source_snapshot_id": "s2", "target_snapshot_id": "t2"}
    w = dbcompare_watch.list_watches()[0]
    dbcompare_watch._harvest_watch(dict(w))
    assert len(dbcompare_watch.list_events(50)) == 1


def test_drift_worse_solo_danger_o_warn(store):
    watch = dict(_W, last_summary=_sev(info=1, warn=1, danger=0))
    # solo info sube → 0 eventos
    dbcompare_watch._emit_transition_events(watch, {"run_id": "rA"}, _sev(info=5, warn=1, danger=0))
    assert dbcompare_watch.list_events(50) == []
    # warn+danger suben → 1 drift_worse
    dbcompare_watch._emit_transition_events(watch, {"run_id": "rB"}, _sev(info=1, warn=2, danger=1))
    events = dbcompare_watch.list_events(50)
    assert len(events) == 1 and events[0]["kind"] == "drift_worse"


def test_drift_cleared(store):
    watch = dict(_W, last_summary=_sev(info=0, warn=2, danger=0))
    dbcompare_watch._emit_transition_events(watch, {"run_id": "rC"}, _sev())
    events = dbcompare_watch.list_events(50)
    assert len(events) == 1 and events[0]["kind"] == "drift_cleared"


def test_watch_error_emite_evento(store):
    dbcompare_watch._append_event_watch_error(_W, {"run_id": "rE", "error": "boom"})
    events = dbcompare_watch.list_events(50)
    assert len(events) == 1
    assert events[0]["kind"] == "watch_error"
    assert events[0]["detail"]["error"] == "boom"
