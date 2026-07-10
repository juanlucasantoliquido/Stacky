"""Plan 117 F5 — digest narrado opt-in (?narrate=1). Blueprint reports aislado."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

import pytest
from flask import Flask

import config as cfg

_DIGEST = {"totals": {"runs": 3}, "by_agent_type": {}, "by_runtime": {},
           "top_failures": [], "highlights": []}


class _Resp:
    def __init__(self, text):
        self.text = text
        self.metadata = {}


def _client(monkeypatch):
    spec = importlib.util.spec_from_file_location("reports_iso_p117", str(_BACKEND / "api" / "reports.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "compose_digest", lambda **kw: dict(_DIGEST))
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(m.bp, url_prefix="/api/reports")
    return app.test_client()


@pytest.fixture
def all_flags_on(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENDPOINT", "http://x/v1/chat/completions", raising=False)
    yield


def test_digest_without_narrate_param_unchanged(monkeypatch):
    with mock.patch("copilot_bridge.invoke_local_llm") as m:
        data = _client(monkeypatch).get("/api/reports/digest").get_json()
    assert "narrative" not in data and "narrative_error" not in data
    m.assert_not_called()


def test_digest_narrate_flags_off_returns_disabled(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_ENABLED", False, raising=False)
    with mock.patch("copilot_bridge.invoke_local_llm") as m:
        data = _client(monkeypatch).get("/api/reports/digest?narrate=1").get_json()
    assert data["narrative"] is None and data["narrative_error"] == "narrative_disabled"
    m.assert_not_called()


def test_digest_narrate_ok(monkeypatch, all_flags_on):
    long_text = "n" * 2000
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(long_text)):
        data = _client(monkeypatch).get("/api/reports/digest?narrate=1").get_json()
    assert data["narrative"] is not None and len(data["narrative"]) <= 1200
    assert data["narrative_error"] is None
    assert data["totals"] == {"runs": 3}


def test_digest_narrate_model_failure_degrades(monkeypatch, all_flags_on):
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("down")):
        data = _client(monkeypatch).get("/api/reports/digest?narrate=1").get_json()
    assert data["narrative"] is None and data["narrative_error"]
    assert data["totals"] == {"runs": 3}
