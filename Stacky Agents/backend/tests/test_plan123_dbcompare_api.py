"""Plan 123 F3 — API de comparación en api/db_compare.py (POST /compare, GET /runs, ...).

Ver Stacky Agents/docs/123_PLAN_DB_COMPARE_MOTOR_DIFF_SEVERIDADES_Y_CORRIDAS.md §F3.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest
from sqlalchemy import create_engine, text


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, svc, key, val):
        self.store[(svc, key)] = val

    def get_password(self, svc, key):
        return self.store.get((svc, key))

    def delete_password(self, svc, key):
        self.store.pop((svc, key), None)


def _seed_db(path, with_index=True):
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE padre (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL)"))
        c.execute(text(
            "CREATE TABLE hija (id INTEGER PRIMARY KEY, "
            "padre_id INTEGER REFERENCES padre(id), valor REAL DEFAULT 0)"
        ))
        if with_index:
            c.execute(text("CREATE INDEX ix_hija_padre ON hija(padre_id)"))
        c.commit()


@pytest.fixture
def app_on(tmp_path, monkeypatch):
    import config as cfg
    import services.dbcompare_registry as reg
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap

    orig = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    cfg.config.STACKY_DB_COMPARE_ENABLED = True
    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(runs, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(reg, "keyring", _FakeKeyring())

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DB_COMPARE_ENABLED = orig


@pytest.fixture
def app_off():
    import config as cfg

    orig = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    cfg.config.STACKY_DB_COMPARE_ENABLED = False
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DB_COMPARE_ENABLED = orig


def _c(app):
    return app.test_client()


def _register_pair(c, tmp_path):
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _seed_db(db_a, with_index=True)
    _seed_db(db_b, with_index=False)
    c.post("/api/db-compare/environments", json={
        "alias": "test-a", "engine": "sqlite", "host": "localhost",
        "port": 0, "database": str(db_a), "username": "user",
    })
    c.post("/api/db-compare/environments", json={
        "alias": "test-b", "engine": "sqlite", "host": "localhost",
        "port": 0, "database": str(db_b), "username": "user",
    })
    c.post("/api/db-compare/environments/test-a/password", json={"password": "unused"})
    c.post("/api/db-compare/environments/test-b/password", json={"password": "unused"})


def _poll_done(c, run_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    final = None
    while time.monotonic() < deadline:
        r = c.get(f"/api/db-compare/runs/{run_id}")
        final = r.get_json()
        if final and final.get("status") in ("done", "error"):
            return final
        time.sleep(0.05)
    return final


def test_compare_202_y_polling_done(app_on, tmp_path):
    c = _c(app_on)
    _register_pair(c, tmp_path)

    r = c.post("/api/db-compare/compare", json={
        "source_alias": "test-a", "target_alias": "test-b", "mode": "fresh",
    })
    assert r.status_code == 202
    body = r.get_json()
    assert body["ok"] is True
    run_id = body["run"]["run_id"]

    final = _poll_done(c, run_id)
    assert final["status"] == "done", final
    assert "diff" in final
    assert final["diff"]["summary"]["objects_total"] == 2


def test_compare_par_activo_409(app_on, tmp_path):
    c = _c(app_on)
    _register_pair(c, tmp_path)

    import services.dbcompare_runs as runs
    pair = frozenset({"test-a", "test-b"})
    with runs._ACTIVE_LOCK:
        runs._ACTIVE_PAIRS.add(pair)
    try:
        r = c.post("/api/db-compare/compare", json={
            "source_alias": "test-a", "target_alias": "test-b",
        })
        assert r.status_code == 409
    finally:
        with runs._ACTIVE_LOCK:
            runs._ACTIVE_PAIRS.discard(pair)


def test_compare_engines_distintos_400(app_on, tmp_path):
    c = _c(app_on)
    db_sqlite = tmp_path / "s.db"
    _seed_db(db_sqlite, with_index=True)
    c.post("/api/db-compare/environments", json={
        "alias": "test-sqlite", "engine": "sqlite", "host": "localhost",
        "port": 0, "database": str(db_sqlite), "username": "user",
    })
    c.post("/api/db-compare/environments", json={
        "alias": "PACIFICO-PROD", "engine": "sqlserver", "host": "host1",
        "port": 1433, "database": "RSPACIFICO", "username": "ro_user",
    })
    c.post("/api/db-compare/environments/test-sqlite/password", json={"password": "unused"})
    c.post("/api/db-compare/environments/PACIFICO-PROD/password", json={"password": "unused"})

    r = c.post("/api/db-compare/compare", json={
        "source_alias": "test-sqlite", "target_alias": "PACIFICO-PROD",
    })
    assert r.status_code == 400


def test_runs_lista_sin_diff(app_on, tmp_path):
    c = _c(app_on)
    _register_pair(c, tmp_path)

    r = c.post("/api/db-compare/compare", json={
        "source_alias": "test-a", "target_alias": "test-b", "mode": "fresh",
    })
    run_id = r.get_json()["run"]["run_id"]
    _poll_done(c, run_id)

    r = c.get("/api/db-compare/runs")
    assert r.status_code == 200
    runs_list = r.get_json()["runs"]
    assert len(runs_list) == 1
    assert "diff" not in runs_list[0]
    assert runs_list[0]["run_id"] == run_id

    # [FIX C7] limit invalido -> 400; limit > 200 se clampea (no error)
    assert c.get("/api/db-compare/runs?limit=abc").status_code == 400
    assert c.get("/api/db-compare/runs?limit=-1").status_code == 400
    r = c.get("/api/db-compare/runs?limit=9999")
    assert r.status_code == 200


def test_export_md_headers_y_404_409(app_on, tmp_path):
    c = _c(app_on)
    _register_pair(c, tmp_path)

    assert c.get("/api/db-compare/runs/no-existe/export.md").status_code == 404

    import services.dbcompare_runs as runs
    running_run = {
        "run_id": "run_still_running", "source_alias": "test-a", "target_alias": "test-b",
        "engine": "sqlite", "mode": "fresh", "status": "running", "phase": "diff",
        "started_at": runs._iso(runs._now()), "finished_at": None, "duration_ms": 0,
        "source_snapshot_id": None, "target_snapshot_id": None,
        "summary": None, "diff": None, "error": None,
    }
    runs._write_run(running_run)
    assert c.get("/api/db-compare/runs/run_still_running/export.md").status_code == 409

    r = c.post("/api/db-compare/compare", json={
        "source_alias": "test-a", "target_alias": "test-b", "mode": "fresh",
    })
    run_id = r.get_json()["run"]["run_id"]
    _poll_done(c, run_id)

    r = c.get(f"/api/db-compare/runs/{run_id}/export.md")
    assert r.status_code == 200
    assert r.mimetype == "text/markdown"
    assert f'filename="{run_id}.md"' in r.headers.get("Content-Disposition", "")


def test_flag_off_403(app_off):
    c = _c(app_off)
    assert c.post("/api/db-compare/compare", json={}).status_code == 403
    assert c.get("/api/db-compare/runs").status_code == 403
    assert c.get("/api/db-compare/runs/x").status_code == 403
    assert c.get("/api/db-compare/runs/x/export.md").status_code == 403
