"""Plan 125 F5 — API del bundle de scripts en api/db_compare.py (mismo blueprint,
mismo _require_enabled que Plan 122/123).

Ver Stacky Agents/docs/125_PLAN_DB_COMPARE_SCRIPTS_PARIDAD_Y_BACKUPS_PAREADOS.md §F5.
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


def _seed_db(path, with_extra_table=True):
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE padre (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL)"))
        if with_extra_table:
            c.execute(text("CREATE TABLE nueva (id INTEGER PRIMARY KEY)"))
        c.commit()


@pytest.fixture
def app_on(tmp_path, monkeypatch):
    import config as cfg
    import services.dbcompare_registry as reg
    import services.dbcompare_runs as runs
    import services.dbcompare_scripts as scripts
    import services.dbcompare_snapshot as snap

    orig = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    cfg.config.STACKY_DB_COMPARE_ENABLED = True
    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(runs, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(scripts, "data_dir", lambda: tmp_path)
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
    _seed_db(db_a, with_extra_table=True)
    _seed_db(db_b, with_extra_table=False)
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


def _create_done_run(c, tmp_path):
    _register_pair(c, tmp_path)
    r = c.post("/api/db-compare/compare", json={
        "source_alias": "test-a", "target_alias": "test-b", "mode": "fresh",
    })
    run_id = r.get_json()["run"]["run_id"]
    final = _poll_done(c, run_id)
    assert final["status"] == "done", final
    return run_id


def test_generar_y_leer_manifest(app_on, tmp_path):
    c = _c(app_on)
    run_id = _create_done_run(c, tmp_path)

    r = c.post(f"/api/db-compare/runs/{run_id}/scripts")
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["ok"] is True
    assert body["manifest"]["run_id"] == run_id
    assert len(body["manifest"]["entries"]) >= 1

    r2 = c.get(f"/api/db-compare/runs/{run_id}/scripts")
    assert r2.status_code == 200
    assert r2.get_json()["manifest"]["run_id"] == run_id


def test_get_scripts_404_si_no_generado(app_on, tmp_path):
    c = _c(app_on)
    run_id = _create_done_run(c, tmp_path)
    r = c.get(f"/api/db-compare/runs/{run_id}/scripts")
    assert r.status_code == 404


def test_post_scripts_run_inexistente_404(app_on):
    c = _c(app_on)
    r = c.post("/api/db-compare/runs/run_no_existe/scripts")
    assert r.status_code == 404


def test_run_no_done_409(app_on, tmp_path):
    import services.dbcompare_runs as runs

    c = _c(app_on)
    _register_pair(c, tmp_path)
    fake_run = {
        "run_id": "run_fake_running", "source_alias": "test-a", "target_alias": "test-b",
        "engine": "sqlite", "mode": "fresh", "status": "running", "phase": "diff",
        "started_at": "2026-07-14T00:00:00Z", "finished_at": None, "duration_ms": 0,
        "source_snapshot_id": None, "target_snapshot_id": None,
        "summary": None, "diff": None, "error": None,
    }
    runs._write_run(fake_run)

    r = c.post("/api/db-compare/runs/run_fake_running/scripts")
    assert r.status_code == 409


def test_file_allowlist_y_traversal_400(app_on, tmp_path):
    c = _c(app_on)
    run_id = _create_done_run(c, tmp_path)
    c.post(f"/api/db-compare/runs/{run_id}/scripts")

    r_traversal = c.get(f"/api/db-compare/runs/{run_id}/scripts/file?path=../../etc/passwd")
    assert r_traversal.status_code == 400

    r_no_allow = c.get(f"/api/db-compare/runs/{run_id}/scripts/file?path=02_paridad/no_existe.sql")
    assert r_no_allow.status_code == 400

    r_manifest = c.get(f"/api/db-compare/runs/{run_id}/scripts/file?path=MANIFEST.json")
    assert r_manifest.status_code == 200
    assert r_manifest.mimetype == "text/plain"

    manifest = c.get(f"/api/db-compare/runs/{run_id}/scripts").get_json()["manifest"]
    real_file = manifest["entries"][0]["file"]
    r_real = c.get(f"/api/db-compare/runs/{run_id}/scripts/file?path={real_file}")
    assert r_real.status_code == 200


def test_zip_headers(app_on, tmp_path):
    c = _c(app_on)
    run_id = _create_done_run(c, tmp_path)
    c.post(f"/api/db-compare/runs/{run_id}/scripts")

    r = c.get(f"/api/db-compare/runs/{run_id}/scripts.zip")
    assert r.status_code == 200
    assert r.mimetype == "application/zip"
    assert f'dbcompare_{run_id}.zip' in r.headers["Content-Disposition"]


def test_flag_off_403(app_off):
    c = _c(app_off)
    assert c.post("/api/db-compare/runs/x/scripts").status_code == 403
    assert c.get("/api/db-compare/runs/x/scripts").status_code == 403
    assert c.get("/api/db-compare/runs/x/scripts/file?path=README.md").status_code == 403
    assert c.get("/api/db-compare/runs/x/scripts.zip").status_code == 403
