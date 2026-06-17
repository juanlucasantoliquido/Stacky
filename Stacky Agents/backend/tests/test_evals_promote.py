"""V2.3 — Endpoint promote-to-golden + historia de evals."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_promote_requires_execution_id(client):
    r = client.post("/api/evals/promote", json={})
    assert r.status_code == 400


def test_promote_calls_harvest_and_returns_path(client, monkeypatch):
    import evals.harvest as harvest_mod

    captured = {}

    def _fake_harvest(*, execution_id, name=None, agents_dir=None):
        captured["execution_id"] = execution_id
        return Path("/tmp/golden_42.json")

    monkeypatch.setattr(harvest_mod, "harvest", _fake_harvest)

    r = client.post("/api/evals/promote", json={"execution_id": 42})
    assert r.status_code == 201
    body = r.get_json()
    assert body["ok"] is True
    assert "golden_42.json" in body["golden_path"]
    assert captured["execution_id"] == 42


def test_promote_harvest_error_returns_409(client, monkeypatch):
    import evals.harvest as harvest_mod

    def _boom(*, execution_id, name=None, agents_dir=None):
        raise harvest_mod.HarvestError("ejecución no completada")

    monkeypatch.setattr(harvest_mod, "harvest", _boom)

    r = client.post("/api/evals/promote", json={"execution_id": 99})
    assert r.status_code == 409
    assert r.get_json()["error"] == "harvest_failed"


def test_eval_history_lists_recorded_runs(client):
    from db import init_db
    from services import eval_history

    init_db()

    class _R:
        def __init__(self, name, score, ok):
            self.case = type("C", (), {"name": name})()
            self.score = score
            self.ok = ok

    eval_history.record_run("developer", [_R("c1", 90, True), _R("c2", 40, False)])

    r = client.get("/api/evals/eval-history?agent_type=developer")
    assert r.status_code == 200
    runs = r.get_json()["runs"]
    assert len(runs) >= 1
    assert runs[0]["agent_type"] == "developer"
    assert runs[0]["passed"] == 1 and runs[0]["failed"] == 1
