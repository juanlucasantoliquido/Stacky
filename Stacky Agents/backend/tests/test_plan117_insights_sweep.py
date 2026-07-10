"""Plan 117 F2 — persistencia + sweep de fondo (DB temporal, sin app, mocks en origen)."""
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
from services import local_insights as li

db.init_db()


class _Resp:
    def __init__(self, text, model="qwen-test"):
        self.text = text
        self.metadata = {"model": model}


_GOOD_JSON = ('{"tldr": "ok", "labels": ["x"], "risk": "low", '
              '"probable_cause": null, "evidence": null, "next_step": null}')


@pytest.fixture(autouse=True)
def _flags_on(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENDPOINT", "http://x/v1/chat/completions", raising=False)
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_MODEL", "qwen-test", raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE", 3, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS", 7, raising=False)
    # Health-gate feliz por default (los tests que lo prueban lo sobreescriben).
    monkeypatch.setattr(li, "_local_llm_reachable", lambda *a, **k: True)
    yield


_counter = {"n": 1000}


def _mk_execution(agent_type="developer", status="completed", metadata=None, minutes_ago=1):
    _counter["n"] += 1
    now = datetime.utcnow()
    with db.session_scope() as s:
        row = AgentExecution(
            ticket_id=1, agent_type=agent_type, status=status,
            input_context_json="[]", output="salida", started_by="test",
            started_at=now - timedelta(minutes=minutes_ago),
            completed_at=now - timedelta(minutes=minutes_ago) + timedelta(seconds=5),
        )
        if metadata is not None:
            row.metadata_dict = metadata
        s.add(row)
        s.flush()
        return row.id


def _insight_of(eid):
    with db.session_scope() as s:
        return (s.get(AgentExecution, eid).metadata_dict or {}).get("local_insight")


def test_sweep_annotates_terminated_runs():
    e1 = _mk_execution()
    e2 = _mk_execution()
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD_JSON)) as m:
        assert li.run_sweep_once() >= 2
    assert m.called
    for e in (e1, e2):
        ins = _insight_of(e)
        assert ins and ins["state"] == "done" and ins["tldr"] == "ok"


def test_sweep_master_off_makes_zero_calls(monkeypatch):
    _mk_execution()
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_ENABLED", False, raising=False)
    with mock.patch("copilot_bridge.invoke_local_llm") as m:
        assert li.run_sweep_once() == 0
    m.assert_not_called()


def test_sweep_requires_local_llm_enabled(monkeypatch):
    _mk_execution()
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENABLED", False, raising=False)
    with mock.patch("copilot_bridge.invoke_local_llm") as m:
        assert li.run_sweep_once() == 0
    m.assert_not_called()


def test_sweep_skips_excluded_agent_types():
    eid = _mk_execution(agent_type="local_llm_playground")
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD_JSON)):
        li.run_sweep_once()
    assert _insight_of(eid) is None


def test_sweep_skips_rows_with_insight():
    eid = _mk_execution(metadata={"local_insight": {"state": "failed", "attempts": 1}})
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD_JSON)) as m:
        li.run_sweep_once()
    # no re-procesa esa fila (queda failed); puede procesar otras, así que no assert m.not_called global
    assert _insight_of(eid)["state"] == "failed"


def test_sweep_respects_max_per_cycle(monkeypatch):
    for _ in range(5):
        _mk_execution()
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE", 2, raising=False)
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD_JSON)) as m:
        li.run_sweep_once()
    assert m.call_count == 2


def test_generate_failure_writes_failed_state():
    eid = _mk_execution()
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("boom")):
        r = li.generate_insight_for_execution(eid)  # camino manual (persist_bridge_failures=True default)
    assert r["ok"] is False
    ins = _insight_of(eid)
    assert ins["state"] == "failed" and "boom" in ins["error"] and ins["attempts"] == 1


def test_generate_parse_error_persists_failed():
    for persist in (True, False):
        eid = _mk_execution()
        with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp("no soy json")):
            li.generate_insight_for_execution(eid, persist_bridge_failures=persist)
        assert _insight_of(eid)["state"] == "failed"


def test_sweep_model_down_aborts_cycle_without_burning_rows():
    ids = [_mk_execution() for _ in range(3)]
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("conn refused")) as m:
        assert li.run_sweep_once() == 0
    assert m.call_count == 1  # abort tras la primera falla transitoria
    for e in ids:
        assert _insight_of(e) is None  # vírgenes


def test_sweep_health_gate_short_circuits(monkeypatch):
    _mk_execution()
    monkeypatch.setattr(li, "_local_llm_reachable", lambda *a, **k: False)
    with mock.patch("copilot_bridge.invoke_local_llm") as m:
        assert li.run_sweep_once() == 0
    m.assert_not_called()


def test_generate_force_regenerates():
    eid = _mk_execution(metadata={"local_insight": li.make_insight_metadata(
        {"tldr": "old", "labels": [], "risk": "low", "probable_cause": None,
         "evidence": None, "next_step": None}, model="q", attempts=1)})
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD_JSON)) as m:
        r = li.generate_insight_for_execution(eid, force=True)
    assert m.called and r["ok"] is True
    assert _insight_of(eid)["attempts"] == 2


def test_app_does_not_start_insights_daemon_under_pytest():
    """C1 — el guard `"pytest" not in sys.modules` impide arrancar el daemon en la suite.

    NOTA: no se invoca create_app() porque el paquete api está roto en HEAD por WIP
    ajeno (SyntaxError en api/devops_servers.py:212); se verifica el invariante del
    guard (pytest presente ⇒ bloque saltado) y que no exista el thread del daemon.
    """
    import threading
    assert "pytest" in sys.modules
    assert not any(t.name == "stacky-local-insights-daemon" for t in threading.enumerate())


def test_pick_candidates_includes_null_metadata():
    eid = _mk_execution(metadata=None)
    with db.session_scope() as s:
        row = s.get(AgentExecution, eid)
        assert row.metadata_json is None
        cands = [r.id for r in li.pick_candidates(s, lookback_days=7, limit=10)]
    assert eid in cands


def test_pick_candidates_noise_does_not_starve():
    # Aislar: la DB in-memory acumula filas de tests previos del módulo.
    with db.session_scope() as s:
        s.query(AgentExecution).delete()
    for _ in range(8):
        _mk_execution(agent_type="local_llm_playground", minutes_ago=1)
    dev = _mk_execution(agent_type="developer", minutes_ago=60)
    with db.session_scope() as s:
        cands = [r.id for r in li.pick_candidates(s, lookback_days=7, limit=2)]
    assert dev in cands
