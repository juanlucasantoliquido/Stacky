"""Plan 121 F4 — endpoints: escaneo on-demand + hallazgos recientes."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from flask import Flask

import config as cfg
import db
from models import AgentExecution

db.init_db()


class _Resp:
    def __init__(self, text, model="qwen-test"):
        self.text = text
        self.metadata = {"model": model}


_FINDING_JSON = (
    '{"findings": [{"data_class": "secrets", "severity": "critical", '
    '"excerpt": "password=hunter22", "rationale": "clave en claro"}]}'
)
_CLEAN_JSON = '{"findings": []}'


@pytest.fixture()
def client():
    from api.local_llm_analysis import bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(bp, url_prefix="/api/llm")
    return app.test_client()


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_EGRESS_SENTINEL_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_EGRESS_SENTINEL_MAX_CHARS", 24000, raising=False)
    yield


def test_scan_404_when_flag_off(client, monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_EGRESS_SENTINEL_ENABLED", False, raising=False)
    resp = client.post("/api/llm/egress-sentinel/scan", json={"text": "algo"})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "egress_sentinel_disabled"


def test_scan_400_without_text(client):
    resp = client.post("/api/llm/egress-sentinel/scan", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "text_required"


def test_scan_returns_masked_findings(client):
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_FINDING_JSON)):
        resp = client.post("/api/llm/egress-sentinel/scan", json={"text": "password=hunter22"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "findings"
    assert "hunter22" not in body["findings"][0]["excerpt_masked"]
    assert "secrets" in body["deterministic_classes"]


def test_scan_502_when_local_llm_down(client):
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("modelo caído")):
        resp = client.post("/api/llm/egress-sentinel/scan", json={"text": "algo cualquiera"})
    assert resp.status_code == 502


def _mk_execution(metadata=None, minutes_ago=1):
    now = datetime.utcnow()
    with db.session_scope() as s:
        row = AgentExecution(
            ticket_id=1, agent_type="developer", status="completed",
            input_context_json="[]", output="salida", started_by="test",
            started_at=now - timedelta(minutes=minutes_ago),
            completed_at=now - timedelta(minutes=minutes_ago) + timedelta(seconds=5),
        )
        if metadata is not None:
            row.metadata_dict = metadata
        s.add(row)
        s.flush()
        return row.id


def test_findings_404_when_flag_off(client, monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_EGRESS_SENTINEL_ENABLED", False, raising=False)
    resp = client.get("/api/llm/egress-sentinel/findings")
    assert resp.status_code == 404


def test_findings_lists_only_flagged_executions(client):
    clean_id = _mk_execution(metadata={"egress_sentinel": {
        "status": "clean", "findings": [], "deterministic_classes": [], "model": "m", "scanned_chars": 1, "version": 1,
    }})
    flagged_id = _mk_execution(metadata={"egress_sentinel": {
        "status": "findings",
        "findings": [{"data_class": "secrets", "severity": "critical", "excerpt_masked": "pass…***", "rationale": "x"}],
        "deterministic_classes": ["secrets"], "model": "m", "scanned_chars": 1, "version": 1,
    }})
    resp = client.get("/api/llm/egress-sentinel/findings")
    assert resp.status_code == 200
    body = resp.get_json()
    ids = [item["execution_id"] for item in body["items"]]
    assert flagged_id in ids
    assert clean_id not in ids


def test_findings_summary_counts(client):
    _mk_execution(metadata={"egress_sentinel": {
        "status": "clean", "findings": [], "deterministic_classes": [], "model": "m", "scanned_chars": 1, "version": 1,
    }})
    _mk_execution(metadata={"egress_sentinel": {
        "status": "clean", "findings": [], "deterministic_classes": [], "model": "m", "scanned_chars": 1, "version": 1,
    }})
    _mk_execution(metadata={"egress_sentinel": {
        "status": "findings",
        "findings": [{"data_class": "secrets", "severity": "critical", "excerpt_masked": "pass…***", "rationale": "x"}],
        "deterministic_classes": ["secrets"], "model": "m", "scanned_chars": 1, "version": 1,
    }})
    resp = client.get("/api/llm/egress-sentinel/findings")
    assert resp.status_code == 200
    summary = resp.get_json()["summary"]
    # >= porque la DB sqlite en memoria es compartida entre tests del módulo (sin
    # rollback por test); solo importa que el conteo refleje TODAS las escaneadas.
    assert summary["scanned_total"] >= 3
    assert summary["flagged_total"] >= 1
