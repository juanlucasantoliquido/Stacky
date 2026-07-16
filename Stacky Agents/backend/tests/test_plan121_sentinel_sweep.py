"""Plan 121 F3 — sweep en background con health-gate (no-burn)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import config as cfg
import db
from models import AgentExecution
from services import egress_sentinel as es

db.init_db()


class _Resp:
    def __init__(self, text, model="qwen-test"):
        self.text = text
        self.metadata = {"model": model}


_GOOD_JSON_WITH_FINDING = (
    '{"findings": [{"data_class": "secrets", "severity": "critical", '
    '"excerpt": "password=hunter22", "rationale": "clave en claro"}]}'
)
_GOOD_JSON_CLEAN = '{"findings": []}'


@pytest.fixture(autouse=True)
def _flags_on(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_EGRESS_SENTINEL_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENDPOINT", "http://x/v1/chat/completions", raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_EGRESS_SENTINEL_MAX_PER_CYCLE", 3, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_EGRESS_SENTINEL_LOOKBACK_DAYS", 7, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_EGRESS_SENTINEL_MAX_CHARS", 24000, raising=False)
    # Health-gate feliz por default (los tests que lo prueban lo sobreescriben).
    monkeypatch.setattr(es, "_local_llm_reachable", lambda *a, **k: True)
    yield


_counter = {"n": 2000}


def _mk_execution(agent_type="developer", status="completed", metadata=None, minutes_ago=1,
                   input_context_json="password=hunter22"):
    _counter["n"] += 1
    now = datetime.utcnow()
    with db.session_scope() as s:
        row = AgentExecution(
            ticket_id=1, agent_type=agent_type, status=status,
            input_context_json=input_context_json, output="salida", started_by="test",
            started_at=now - timedelta(minutes=minutes_ago),
            completed_at=now - timedelta(minutes=minutes_ago) + timedelta(seconds=5),
        )
        if metadata is not None:
            row.metadata_dict = metadata
        s.add(row)
        s.flush()
        return row.id


def _sentinel_of(eid):
    with db.session_scope() as s:
        return (s.get(AgentExecution, eid).metadata_dict or {}).get("egress_sentinel")


def test_sweep_disabled_returns_zero(monkeypatch):
    eid = _mk_execution()
    monkeypatch.setattr(cfg.config, "STACKY_EGRESS_SENTINEL_ENABLED", False, raising=False)
    with mock.patch("copilot_bridge.invoke_local_llm") as m:
        assert es.run_sweep_once() == 0
    m.assert_not_called()
    assert _sentinel_of(eid) is None


def test_sweep_no_burn_when_llm_down(monkeypatch):
    eid = _mk_execution()
    monkeypatch.setattr(es, "_local_llm_reachable", lambda *a, **k: False)
    with mock.patch("copilot_bridge.invoke_local_llm") as m:
        assert es.run_sweep_once() == 0
    m.assert_not_called()
    assert _sentinel_of(eid) is None


def test_scan_execution_annotates_masked_finding():
    eid = _mk_execution()
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD_JSON_WITH_FINDING)):
        assert es.run_sweep_once() >= 1
    meta = _sentinel_of(eid)
    assert meta is not None
    assert meta["status"] == "findings"
    assert "hunter22" not in meta["findings"][0]["excerpt_masked"]


def test_scan_failure_does_not_mark_scanned():
    eid = _mk_execution()
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("boom")):
        assert es.run_sweep_once() == 0
    assert _sentinel_of(eid) is None


def test_pick_candidates_skips_already_scanned():
    eid = _mk_execution(metadata={"egress_sentinel": {"status": "clean", "findings": []}})
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD_JSON_CLEAN)):
        es.run_sweep_once()
    # should_scan() rechaza la fila ya escaneada sin importar otros candidatos del ciclo.
    assert _sentinel_of(eid)["status"] == "clean"
    assert _sentinel_of(eid)["findings"] == []


def test_pick_candidates_excludes_local_llm_agent_types():
    eid = _mk_execution(agent_type="local_llm_playground")
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD_JSON_WITH_FINDING)) as m:
        es.run_sweep_once()
    m.assert_not_called()
    assert _sentinel_of(eid) is None


def test_deterministic_classes_included():
    eid = _mk_execution(input_context_json="password=abc123xyz")
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD_JSON_CLEAN)):
        es.run_sweep_once()
    meta = _sentinel_of(eid)
    assert "secrets" in meta["deterministic_classes"]
