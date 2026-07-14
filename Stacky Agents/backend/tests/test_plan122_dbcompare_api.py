"""Plan 122 F4 — API /api/db-compare (CRUD ambientes + password + test + snapshot).

Ver Stacky Agents/docs/122_PLAN_DB_COMPARE_NUCLEO_AMBIENTES_CONEXION_READONLY_Y_SNAPSHOT.md
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import services.dbcompare_registry as reg
import services.dbcompare_snapshot as snap


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, svc, key, val):
        self.store[(svc, key)] = val

    def get_password(self, svc, key):
        return self.store.get((svc, key))

    def delete_password(self, svc, key):
        self.store.pop((svc, key), None)


@pytest.fixture
def app_on(tmp_path, monkeypatch):
    import config as cfg

    orig = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    cfg.config.STACKY_DB_COMPARE_ENABLED = True
    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
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


def test_flag_off_todos_403_salvo_health(app_off):
    c = _c(app_off)
    assert c.get("/api/db-compare/health").status_code == 200
    assert c.get("/api/db-compare/environments").status_code == 403
    assert c.post("/api/db-compare/environments", json={}).status_code == 403
    assert c.delete("/api/db-compare/environments/x").status_code == 403
    assert c.post("/api/db-compare/environments/x/password", json={"password": "a"}).status_code == 403
    assert c.post("/api/db-compare/environments/x/test").status_code == 403
    assert c.post("/api/db-compare/environments/x/snapshot").status_code == 403
    assert c.get("/api/db-compare/environments/x/snapshots").status_code == 403
    assert c.get("/api/db-compare/snapshots/x").status_code == 403


def test_health_reporta_drivers_y_flag(app_on):
    c = _c(app_on)
    r = c.get("/api/db-compare/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["flag_enabled"] is True
    assert "drivers" in data
    assert "sqlserver" in data["drivers"]
    assert "keyring_available" in data


def test_crud_ambiente_roundtrip(app_on):
    c = _c(app_on)
    r = c.post("/api/db-compare/environments", json={
        "alias": "PACIFICO-DEV", "engine": "sqlserver", "host": "host1",
        "port": 1433, "database": "RSPACIFICO", "username": "ro_user",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "password" not in body.get("environment", body)

    r = c.get("/api/db-compare/environments")
    assert r.status_code == 200
    envs = r.get_json()["environments"]
    assert len(envs) == 1
    assert envs[0]["alias"] == "PACIFICO-DEV"

    r = c.delete("/api/db-compare/environments/PACIFICO-DEV")
    assert r.status_code == 200
    assert c.get("/api/db-compare/environments").get_json()["environments"] == []

    r = c.delete("/api/db-compare/environments/NO-EXISTE")
    assert r.status_code == 404


def test_environments_incluye_latest_snapshot(app_on, tmp_path):
    import services.dbcompare_snapshot as snap

    c = _c(app_on)
    c.post("/api/db-compare/environments", json={
        "alias": "test-snap", "engine": "sqlite", "host": "localhost",
        "port": 0, "database": str(tmp_path / "x.db"), "username": "user",
    })
    c.post("/api/db-compare/environments/test-snap/password", json={"password": "unused"})
    envs = c.get("/api/db-compare/environments").get_json()["environments"]
    assert envs[0]["latest_snapshot_taken_at"] is None
    assert envs[0]["latest_snapshot_hash8"] is None

    r = c.post("/api/db-compare/environments/test-snap/snapshot")
    assert r.status_code == 200

    envs = c.get("/api/db-compare/environments").get_json()["environments"]
    assert envs[0]["latest_snapshot_taken_at"] is not None
    assert envs[0]["latest_snapshot_hash8"] is not None
    assert len(envs[0]["latest_snapshot_hash8"]) == 8


def test_snapshot_endpoint_sqlite(app_on, tmp_path):
    c = _c(app_on)
    c.post("/api/db-compare/environments", json={
        "alias": "test-snap", "engine": "sqlite", "host": "localhost",
        "port": 0, "database": str(tmp_path / "x.db"), "username": "user",
    })
    c.post("/api/db-compare/environments/test-snap/password", json={"password": "unused"})
    r = c.post("/api/db-compare/environments/test-snap/snapshot")
    assert r.status_code == 200
    body = r.get_json()
    assert "id" in body
    assert "content_hash" in body

    r = c.get("/api/db-compare/environments/test-snap/snapshots")
    assert r.status_code == 200
    assert len(r.get_json()["snapshots"]) == 1

    snap_id = body["id"]
    r = c.get(f"/api/db-compare/snapshots/{snap_id}")
    assert r.status_code == 200
    assert r.get_json()["content_hash"] == body["content_hash"]

    assert c.get("/api/db-compare/snapshots/no-existe").status_code == 404


def test_password_endpoint_sin_keyring_503(app_on, monkeypatch):
    c = _c(app_on)
    c.post("/api/db-compare/environments", json={
        "alias": "PACIFICO-DEV", "engine": "sqlserver", "host": "host1",
        "port": 1433, "database": "db", "username": "user",
    })
    monkeypatch.setattr(reg, "keyring", None)
    r = c.post("/api/db-compare/environments/PACIFICO-DEV/password", json={"password": "s3cr3t"})
    assert r.status_code == 503
