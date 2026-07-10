"""Plan 116 F2 — endpoints HITL /api/devops/connections/{health,check} + snapshot en memoria.

Blueprint montado en aislamiento (importlib) — el paquete api está roto en HEAD por WIP
ajeno (SyntaxError en api/devops_servers.py). devops_connections solo importa config +
services.connection_doctor, así que carga standalone sin problema.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

import pytest
from flask import Flask

import config as cfg
from services import connection_doctor


def _load_bp():
    spec = importlib.util.spec_from_file_location(
        "devops_connections_iso", str(_BACKEND / "api" / "devops_connections.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def mod():
    m = _load_bp()
    m._SNAPSHOT = None  # reset entre tests
    return m


def _client(mod):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(mod.bp, url_prefix="/api/devops/connections")
    return app.test_client()


_FAKE_SNAP = {"generated_at": datetime.utcnow().isoformat() + "Z", "duration_ms": 10,
              "results": [], "summary": {"ok": 0, "warn": 0, "fail": 0, "skip": 0}}


def test_endpoints_404_when_flag_off(mod, monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", False, raising=False)
    c = _client(mod)
    assert c.get("/api/devops/connections/health").status_code == 404
    assert c.post("/api/devops/connections/check").status_code == 404


def test_health_never_run(mod, monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", True, raising=False)
    data = _client(mod).get("/api/devops/connections/health").get_json()
    assert data["status"] == "never_run" and data["snapshot"] is None


def test_check_stores_and_health_returns_same_snapshot(mod, monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", True, raising=False)
    monkeypatch.setattr(connection_doctor, "run_connection_check", lambda: dict(_FAKE_SNAP))
    c = _client(mod)
    posted = c.post("/api/devops/connections/check").get_json()
    assert posted["status"] == "ready"
    got = c.get("/api/devops/connections/health").get_json()
    assert got["snapshot"] == posted["snapshot"]


def test_health_marks_stale_after_ttl(mod, monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", True, raising=False)
    old = (datetime.utcnow() - timedelta(minutes=10)).isoformat() + "Z"
    mod._SNAPSHOT = {**_FAKE_SNAP, "generated_at": old}
    data = _client(mod).get("/api/devops/connections/health").get_json()
    assert data["stale"] is True


def test_check_never_hits_network_in_tests(mod, monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", True, raising=False)
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return dict(_FAKE_SNAP)

    monkeypatch.setattr(connection_doctor, "run_connection_check", fake)
    _client(mod).post("/api/devops/connections/check")
    assert calls["n"] == 1
