"""Plan 148 F6 — Endpoint read-only /integrations/status + reset manual HITL."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from config import config as _cfg  # noqa: E402
from services import integration_breaker as brk  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_breaker(tmp_path, monkeypatch):
    monkeypatch.setattr(brk, "data_dir", lambda: tmp_path)
    yield


def _client():
    from api.integrations import bp as integrations_bp
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(integrations_bp)
    return app.test_client()


def test_status_empty_when_all_healthy():
    resp = _client().get("/integrations/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"enabled": True, "integrations": []}


def test_status_lists_open_breaker():
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED,
                        "El PAT de Azure DevOps expiró. Renovalo en la Caja Fuerte.")

    resp = _client().get("/integrations/status")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["enabled"] is True
    assert len(body["integrations"]) == 1
    item = body["integrations"][0]
    assert item["reason"] == "ado_pat_expired"
    assert item["vault"] is True
    assert item["title"]


def test_status_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr(_cfg, "STACKY_INTEGRATION_DEGRADATION_ENABLED", False)
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")

    resp = _client().get("/integrations/status")

    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": False, "integrations": []}


def test_reset_closes_breaker():
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    assert brk.get_state("ado_sync", "RSPACIFICO").open is True

    resp = _client().post("/integrations/ado_sync/reset?project=RSPACIFICO")

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert brk.get_state("ado_sync", "RSPACIFICO").open is False
