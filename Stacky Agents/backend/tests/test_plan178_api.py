"""Plan 178 F5 — API del radar de ambientes (/api/db-compare/watches|radar|baselines...).

Ver Stacky Agents/docs/178_PLAN_RADAR_DE_AMBIENTES_...md §F5.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import services.dbcompare_watch as dbcompare_watch
import services.dbcompare_baseline as dbcompare_baseline
import services.dbcompare_registry as dbcompare_registry
import services.dbcompare_snapshot as dbcompare_snapshot
import services.dbcompare_runs as dbcompare_runs

_ENVS = [{"alias": "DEV", "engine": "mssql"}, {"alias": "TEST", "engine": "mssql"}]


def _install(tmp_path, monkeypatch, *, master=True, radar=True):
    import config as cfg

    for mod in (dbcompare_watch, dbcompare_baseline, dbcompare_snapshot, dbcompare_runs):
        monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dbcompare_registry, "list_environments", lambda: list(_ENVS))
    monkeypatch.setattr(
        dbcompare_registry, "get_environment",
        lambda a: next((e for e in _ENVS if e["alias"] == a), None),
    )
    monkeypatch.setattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", master, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_DB_COMPARE_RADAR_ENABLED", radar, raising=False)
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _write_run(tmp_path, run_id, **fields):
    d = tmp_path / "db_compare" / "runs"
    d.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": run_id, "source_alias": "DEV", "target_alias": "TEST",
        "engine": "mssql", "status": "done", "initiated_by": "operator",
        "started_at": "2026-07-18T12:00:00Z", "finished_at": "2026-07-18T12:01:00Z",
        "summary": {"by_severity": {"info": 0, "warn": 0, "danger": 1}, "parity_score": 90.0},
    }
    run.update(fields)
    (d / f"{run_id}.json").write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")


def _write_snap(tmp_path, alias, sid, content_hash, tables, taken_at="2026-07-18T10:00:00Z"):
    d = tmp_path / "db_compare" / "snapshots" / alias
    d.mkdir(parents=True, exist_ok=True)
    snap = {
        "version": 1, "id": sid, "alias": alias, "engine": "mssql",
        "taken_at": taken_at, "duration_ms": 0,
        "schemas": {"dbo": {"tables": tables, "views": {}, "sequences": []}},
        "counts": {}, "content_hash": content_hash,
    }
    (d / f"{sid}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")


_ROUTES = [
    ("get", "/api/db-compare/watches"),
    ("get", "/api/db-compare/radar"),
    ("get", "/api/db-compare/baselines"),
    ("get", "/api/db-compare/watch/events"),
]


def test_403_master_off(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch, master=False, radar=True)
    for method, path in _ROUTES:
        assert getattr(c, method)(path).status_code == 403


def test_403_radar_off(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch, master=True, radar=False)
    for method, path in _ROUTES:
        assert getattr(c, method)(path).status_code == 403


def test_watch_crud_por_api(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch)
    r = c.post("/api/db-compare/watches", json={"source_alias": "DEV", "target_alias": "TEST"})
    assert r.status_code == 200 and r.get_json()["watch"]["watch_id"] == "DEV__TEST"
    got = c.get("/api/db-compare/watches").get_json()
    assert len(got["watches"]) == 1
    assert c.delete("/api/db-compare/watches/DEV__TEST").status_code == 200
    assert c.delete("/api/db-compare/watches/DEV__TEST").status_code == 404


def test_watch_post_body_invalido_400(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch)
    assert c.post("/api/db-compare/watches").status_code == 400
    assert c.post("/api/db-compare/watches", json={}).status_code == 400
    r = c.post("/api/db-compare/watches", json={"source_alias": "  ", "target_alias": "TEST"})
    assert r.status_code == 400 and r.get_json()["ok"] is False


def test_watch_post_alias_invalido_400(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch)
    r = c.post("/api/db-compare/watches", json={"source_alias": "NOPE", "target_alias": "TEST"})
    assert r.status_code == 400


def test_events_list_y_mark_read(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch)
    r = c.get("/api/db-compare/watch/events")
    assert r.status_code == 200 and r.get_json()["events"] == []
    assert c.post("/api/db-compare/watch/events/mark-read", json={}).status_code == 400
    assert c.post("/api/db-compare/watch/events/mark-read", json={"all": True}).status_code == 200


def test_baseline_pin_diff_unpin(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch)
    _write_snap(tmp_path, "DEV", "snapB", "hashBASE", {"T1": {}}, taken_at="2026-07-18T09:00:00Z")
    _write_snap(tmp_path, "DEV", "snapF", "hashFRESH", {"T1": {}, "T2": {}}, taken_at="2026-07-18T12:00:00Z")
    assert c.post("/api/db-compare/environments/DEV/baseline", json={}).status_code == 400
    r = c.post("/api/db-compare/environments/DEV/baseline", json={"snapshot_id": "snapB"})
    assert r.status_code == 200
    d = c.get("/api/db-compare/baseline-diff/DEV").get_json()
    assert d["ok"] is True and d["diff"]["version"] == 1 and "summary" in d["diff"]
    assert c.delete("/api/db-compare/environments/DEV/baseline").status_code == 200
    assert c.delete("/api/db-compare/environments/DEV/baseline").status_code == 404


def test_radar_shape(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch)
    _write_run(tmp_path, "run_1")  # danger=1 → red
    dbcompare_watch.upsert_watch("DEV", "TEST", enabled=True)
    payload = c.get("/api/db-compare/radar").get_json()
    assert payload["ok"] is True
    assert {e["alias"] for e in payload["environments"]} == {"DEV", "TEST"}
    assert len(payload["cells"]) == 1
    assert payload["cells"][0]["state"] == "red"
    assert payload["cells"][0]["watched"] is True
    assert "unread_events" in payload


def test_radar_no_abre_conexiones(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("GET /radar no debe abrir conexión")

    monkeypatch.setattr(dbcompare_snapshot, "take_snapshot", _boom)
    c = _install(tmp_path, monkeypatch)
    _write_run(tmp_path, "run_1")
    assert c.get("/api/db-compare/radar").status_code == 200
