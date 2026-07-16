"""Plan 148 F5 — Degradacion 200-en-vez-de-502 (D6: LLM local + identidad ADO).

`/api/llm/insights/<id>/generate` y `/api/tickets/ado-user` responden 200 con
`available/linked:false` + `reason` cuando la integracion no esta disponible,
en vez de 502 que rompe la UI. Errores genuinos (modelo vivo pero con error,
Exception inesperada) siguen en 502/500 sin cambios. Con la flag OFF, revert
byte-a-byte (502 crudo).

test_ado_user_flag_off_502 es la "prueba de fuego" del hallazgo C1: si
tickets.py leyera la flag por `config` pelado (el modulo) en vez de
`config.config` (la instancia), este test daria 200 en vez de 502.

Monta blueprints AISLADOS (sin create_app()) a proposito: create_app() arranca
threads daemon (output_watcher/manifest_watcher/ticket_status/ado_edit_sweep)
con un crash nativo conocido y preexistente contra el teardown de SQLAlchemy
en Windows (ver memoria del repo) -- no relacionado con este plan.
"""
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

import db  # noqa: E402
from config import config as _cfg  # noqa: E402
from services import integration_breaker as brk  # noqa: E402
from services.ado_client import AdoApiError  # noqa: E402

db.init_db()


@pytest.fixture(autouse=True)
def _isolated_breaker(tmp_path, monkeypatch):
    """Aisla el JSON del breaker; nunca escribe en la data real del operador."""
    monkeypatch.setattr(brk, "data_dir", lambda: tmp_path)
    yield


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setattr(_cfg, "LOCAL_LLM_ENABLED", True, raising=False)
    monkeypatch.setattr(_cfg, "LOCAL_LLM_ENDPOINT", "http://x/v1/chat/completions", raising=False)
    monkeypatch.setattr(_cfg, "STACKY_LOCAL_INSIGHTS_ENABLED", True, raising=False)
    yield


def _llm_client():
    from api.local_llm_analysis import bp as llm_bp
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(llm_bp, url_prefix="/api/llm")
    return app.test_client()


def _tickets_client():
    # bp ya trae url_prefix="/tickets" (services propio); registrar SIN pisarlo
    # con otro url_prefix (Flask reemplaza, no concatena, el prefix del blueprint
    # cuando se pasa uno explicito en app.register_blueprint).
    from api.tickets import bp as tickets_bp
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(tickets_bp)
    return app.test_client()


def _mk_execution():
    from models import AgentExecution, Ticket
    from datetime import datetime

    with db.session_scope() as s:
        if s.get(Ticket, 1) is None:
            s.add(Ticket(id=1, ado_id=999148, project="P", title="t"))
        row = AgentExecution(
            ticket_id=1, agent_type="developer", status="completed",
            input_context_json="[]", output="o", started_by="t",
            started_at=datetime.utcnow(), completed_at=datetime.utcnow(),
        )
        s.add(row)
        s.flush()
        return row.id


# ── /api/llm/insights/<id>/generate ──────────────────────────────────────────

def test_insights_llm_down_returns_200_available_false(monkeypatch):
    eid = _mk_execution()
    monkeypatch.setattr(
        "services.local_insights.generate_insight_for_execution",
        lambda execution_id, force=False: {"ok": False, "error": "generation_failed"},
    )
    monkeypatch.setattr("services.local_insights._local_llm_reachable", lambda: False)

    resp = _llm_client().post(f"/api/llm/insights/{eid}/generate", json={})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["available"] is False
    assert body["reason"] == brk.REASON_LOCAL_LLM_DOWN
    assert brk.get_state("local_llm", None).open is True


def test_insights_genuine_error_still_502(monkeypatch):
    eid = _mk_execution()
    monkeypatch.setattr(
        "services.local_insights.generate_insight_for_execution",
        lambda execution_id, force=False: {"ok": False, "error": "generation_failed"},
    )
    monkeypatch.setattr("services.local_insights._local_llm_reachable", lambda: True)

    resp = _llm_client().post(f"/api/llm/insights/{eid}/generate", json={})

    assert resp.status_code == 502
    assert brk.get_state("local_llm", None).open is False


def test_insights_flag_off_still_502(monkeypatch):
    monkeypatch.setattr(_cfg, "STACKY_INTEGRATION_DEGRADATION_ENABLED", False)
    eid = _mk_execution()
    monkeypatch.setattr(
        "services.local_insights.generate_insight_for_execution",
        lambda execution_id, force=False: {"ok": False, "error": "generation_failed"},
    )
    monkeypatch.setattr("services.local_insights._local_llm_reachable", lambda: False)

    resp = _llm_client().post(f"/api/llm/insights/{eid}/generate", json={})

    assert resp.status_code == 502
    assert brk.get_state("local_llm", None).open is False


# ── /api/tickets/ado-user ─────────────────────────────────────────────────────

def test_ado_user_api_error_returns_200_linked_false(monkeypatch):
    exc = AdoApiError("TF400813: The Personal Access Token used has expired.", status_code=401)

    class _FakeClient:
        def get_authenticated_user(self):
            raise exc

    import api.tickets as tickets_module
    monkeypatch.setattr(tickets_module, "_ado_client_for_ticket", lambda **kw: _FakeClient())

    # bp aislado registrado sin el prefijo /api del arnes completo -> path real
    # servido es /tickets/ado-user (en produccion, montado bajo api_bp, es
    # /api/tickets/ado-user; ver _tickets_client()).
    resp = _tickets_client().get("/tickets/ado-user?project=RSPACIFICO148")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["linked"] is False
    assert body["reason"] == brk.REASON_PAT_EXPIRED
    assert brk.get_state("ado_identity", brk.ado_breaker_project("RSPACIFICO148")).open is True


def test_ado_user_flag_off_502(monkeypatch):
    """Prueba de fuego [C1]: si tickets.py leyera `config` pelado en vez de
    `config.config`, este test daria 200 en vez de 502 (branch OFF inalcanzable)."""
    monkeypatch.setattr(_cfg, "STACKY_INTEGRATION_DEGRADATION_ENABLED", False)
    exc = AdoApiError("TF400813: The Personal Access Token used has expired.", status_code=401)

    class _FakeClient:
        def get_authenticated_user(self):
            raise exc

    import api.tickets as tickets_module
    monkeypatch.setattr(tickets_module, "_ado_client_for_ticket", lambda **kw: _FakeClient())

    # bp aislado registrado sin el prefijo /api del arnes completo -> path real
    # servido es /tickets/ado-user (en produccion, montado bajo api_bp, es
    # /api/tickets/ado-user; ver _tickets_client()).
    resp = _tickets_client().get("/tickets/ado-user?project=RSPACIFICO148")

    assert resp.status_code == 502
    assert brk.get_state("ado_identity", brk.ado_breaker_project("RSPACIFICO148")).open is False


def test_ado_user_unexpected_still_500(monkeypatch):
    class _FakeClient:
        def get_authenticated_user(self):
            raise RuntimeError("boom inesperado")

    import api.tickets as tickets_module
    monkeypatch.setattr(tickets_module, "_ado_client_for_ticket", lambda **kw: _FakeClient())

    # bp aislado registrado sin el prefijo /api del arnes completo -> path real
    # servido es /tickets/ado-user (en produccion, montado bajo api_bp, es
    # /api/tickets/ado-user; ver _tickets_client()).
    resp = _tickets_client().get("/tickets/ado-user?project=RSPACIFICO148")

    assert resp.status_code == 500
