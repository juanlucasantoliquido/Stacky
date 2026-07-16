"""Plan 117 F3 — API: insight en historial + endpoint generate (blueprints aislados).

El paquete api está roto en HEAD por WIP ajeno (SyntaxError api/devops_servers.py:212),
así que se montan los blueprints necesarios vía importlib con stub del paquete api.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

import pytest
from flask import Flask

import config as cfg
import db
from models import AgentExecution, Ticket

db.init_db()


def _ensure_ticket():
    """El historial hace INNER join con Ticket; garantizamos ticket_id=1 real."""
    with db.session_scope() as s:
        if s.get(Ticket, 1) is None:
            s.add(Ticket(id=1, ado_id=999001, project="P", title="t"))


class _Resp:
    def __init__(self, text, model="qwen-test"):
        self.text = text
        self.metadata = {"model": model}


_GOOD = ('{"tldr": "ok", "labels": ["x"], "risk": "low", '
         '"probable_cause": null, "evidence": null, "next_step": null}')


def _stub_api_pkg():
    if "api" not in sys.modules or not hasattr(sys.modules.get("api"), "__path__"):
        pkg = types.ModuleType("api")
        pkg.__path__ = [str(_BACKEND / "api")]
        sys.modules["api"] = pkg
    helpers = types.ModuleType("api._helpers")
    helpers.current_user = lambda: "op"
    sys.modules["api._helpers"] = helpers


def _load(modname, relpath):
    spec = importlib.util.spec_from_file_location(modname, str(_BACKEND / relpath))
    m = importlib.util.module_from_spec(spec)
    sys.modules[modname] = m
    spec.loader.exec_module(m)
    return m


def _llm_client():
    m = _load("api.local_llm_analysis", "api/local_llm_analysis.py")
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(m.bp, url_prefix="/api/llm")
    return app.test_client()


def _exec_client():
    _stub_api_pkg()
    m = _load("api.executions", "api/executions.py")
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(m.bp, url_prefix="/api/executions")
    return app.test_client()


_counter = {"n": 5000}


def _mk(agent_type="developer", status="completed", metadata=None):
    _counter["n"] += 1
    _ensure_ticket()
    now = datetime.utcnow()
    with db.session_scope() as s:
        row = AgentExecution(ticket_id=1, agent_type=agent_type, status=status,
                             input_context_json="[]", output="o", started_by="t",
                             started_at=now - timedelta(minutes=1), completed_at=now)
        if metadata is not None:
            row.metadata_dict = metadata
        s.add(row)
        s.flush()
        return row.id


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENDPOINT", "http://x/v1/chat/completions", raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_ENABLED", True, raising=False)
    yield


def test_generate_endpoint_master_off_404(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_ENABLED", False, raising=False)
    eid = _mk()
    r = _llm_client().post(f"/api/llm/insights/{eid}/generate", json={})
    assert r.status_code == 404 and r.get_json()["error"] == "local_insights_disabled"


def test_generate_endpoint_local_llm_off_404(monkeypatch):
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENABLED", False, raising=False)
    eid = _mk()
    r = _llm_client().post(f"/api/llm/insights/{eid}/generate", json={})
    assert r.status_code == 404


def test_generate_endpoint_ok():
    eid = _mk()
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=_Resp(_GOOD)):
        r = _llm_client().post(f"/api/llm/insights/{eid}/generate", json={})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["insight"]["tldr"] == "ok"


def test_generate_endpoint_excluded_409():
    eid = _mk(agent_type="local_llm_playground")
    r = _llm_client().post(f"/api/llm/insights/{eid}/generate", json={})
    assert r.status_code == 409 and r.get_json()["reason"] == "agent_type_excluded"


def test_generate_endpoint_not_found_404():
    r = _llm_client().post("/api/llm/insights/999999/generate", json={})
    assert r.status_code == 404 and r.get_json()["error"] == "execution_not_found"


def test_generate_endpoint_model_failure_502():
    """Modelo local VIVO pero la invocación falla (error genuino) -> sigue 502.

    Plan 148 F5(a): distinto de "modelo no disponible" (eso degrada a 200
    available:false). _local_llm_reachable=True fija que el modelo está arriba
    pero la llamada específica falló -- así el fixture (endpoint fake http://x)
    no se confunde con "caído" ahora que la reachability es el discriminador.
    """
    eid = _mk()
    with mock.patch("copilot_bridge.invoke_local_llm", side_effect=RuntimeError("down")), \
         mock.patch("services.local_insights._local_llm_reachable", return_value=True):
        r = _llm_client().post(f"/api/llm/insights/{eid}/generate", json={})
    assert r.status_code == 502
    with db.session_scope() as s:
        assert (s.get(AgentExecution, eid).metadata_dict or {})["local_insight"]["state"] == "failed"


def test_generate_endpoint_no_json_400():
    eid = _mk()
    r = _llm_client().post(f"/api/llm/insights/{eid}/generate")  # sin json=
    assert r.status_code == 400 and r.get_json()["error"] == "body_required_json"


def test_history_includes_local_insight(monkeypatch):
    monkeypatch.setenv("STACKY_EXECUTION_HISTORY_ENABLED", "true")
    ins = {"state": "done", "tldr": "hola", "risk": "low"}
    with_ins = _mk(metadata={"local_insight": ins})
    without = _mk()
    data = _exec_client().get("/api/executions/history").get_json()
    by_id = {it["id"]: it for it in data}
    assert by_id[with_ins]["local_insight"]["tldr"] == "hola"
    assert by_id[without]["local_insight"] is None


def test_history_shape_unchanged_when_flag_off(monkeypatch):
    monkeypatch.setenv("STACKY_EXECUTION_HISTORY_ENABLED", "true")
    monkeypatch.setattr(cfg.config, "STACKY_LOCAL_INSIGHTS_ENABLED", False, raising=False)
    eid = _mk()
    data = _exec_client().get("/api/executions/history").get_json()
    item = next(it for it in data if it["id"] == eid)
    assert item["local_insight"] is None
    for key in ("id", "ticket_id", "agent_type", "status", "started_at", "error_message"):
        assert key in item
