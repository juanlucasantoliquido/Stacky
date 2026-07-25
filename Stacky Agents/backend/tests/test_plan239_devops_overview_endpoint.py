"""Plan 239 F1.5 — GET /api/devops/overview: 404 con el cockpit OFF, SIEMPRE 200 con ON.

KPI-7 (inocuidad) se prueba con monkeypatches que REVIENTAN si alguien abre red,
ejecuta algo remoto o invoca al LLM: si el endpoint responde 200, no los llamó.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def app_cockpit_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_COCKPIT_ENABLED", False)
    cfg.config.STACKY_DEVOPS_COCKPIT_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_COCKPIT_ENABLED = original


@pytest.fixture
def app_cockpit_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_COCKPIT_ENABLED", False)
    cfg.config.STACKY_DEVOPS_COCKPIT_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_COCKPIT_ENABLED = original


def test_overview_404_si_cockpit_off(app_cockpit_off):
    resp = app_cockpit_off.test_client().get("/api/devops/overview")
    assert resp.status_code == 404


def test_overview_200_con_todo_apagado(app_cockpit_on, monkeypatch):
    import config as cfg
    for flag in ("STACKY_DEPLOYMENTS_ENABLED", "STACKY_CI_RUN_LEDGER_ENABLED",
                 "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", "STACKY_DEVOPS_SERVERS_ENABLED"):
        monkeypatch.setattr(cfg.config, flag, False, raising=False)
    resp = app_cockpit_on.test_client().get("/api/devops/overview")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "unknown", "sin ninguna fuente NO se puede decir que todo está bien"
    assert len(data["blocks"]) == 4
    assert all(b["available"] is False and b["reason"] == "flag_off" for b in data["blocks"].values())


def test_overview_contrato_de_claves(app_cockpit_on):
    data = app_cockpit_on.test_client().get("/api/devops/overview").get_json()
    for clave in ("generated_at", "status", "filters", "options", "kpis", "series",
                  "alerts", "recent", "blocks"):
        assert clave in data, f"falta la clave de primer nivel {clave}"


def test_overview_no_ejecuta_remoto(app_cockpit_on, monkeypatch):
    """KPI-7: ni un comando remoto ni el doctor de conexiones (HITL del plan 116)."""
    from services import remote_exec, connection_doctor

    def _boom(*a, **k):
        raise AssertionError("el overview NO puede ejecutar nada remoto")

    for nombre in ("run_deploy_step", "run_remote_command", "run_ps"):
        if hasattr(remote_exec, nombre):
            monkeypatch.setattr(remote_exec, nombre, _boom)
    monkeypatch.setattr(connection_doctor, "run_connection_check", _boom)

    resp = app_cockpit_on.test_client().get("/api/devops/overview")
    assert resp.status_code == 200


def test_overview_no_abre_red(app_cockpit_on, monkeypatch):
    import requests

    def _boom(*a, **k):
        raise AssertionError("el overview NO puede abrir red")

    monkeypatch.setattr(requests, "request", _boom)
    monkeypatch.setattr(requests, "get", _boom)
    monkeypatch.setattr(requests, "post", _boom)
    resp = app_cockpit_on.test_client().get("/api/devops/overview")
    assert resp.status_code == 200


def test_overview_no_invoca_llm(app_cockpit_on, monkeypatch):
    """El invocador local vive en copilot_bridge.invoke_local_llm (services/local_insights.py:319)."""
    import copilot_bridge
    from services import llm_router

    def _boom(*a, **k):
        raise AssertionError("el overview NO puede invocar al LLM")

    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", _boom, raising=False)
    monkeypatch.setattr(llm_router, "decide", _boom, raising=False)
    resp = app_cockpit_on.test_client().get("/api/devops/overview")
    assert resp.status_code == 200


def test_overview_acepta_filtros(app_cockpit_on):
    resp = app_cockpit_on.test_client().get(
        "/api/devops/overview?app_id=x&project=y&window_days=30")
    assert resp.status_code == 200
    assert resp.get_json()["filters"]["window_days"] == 30


def test_overview_window_days_basura_no_es_400(app_cockpit_on):
    resp = app_cockpit_on.test_client().get("/api/devops/overview?window_days=abc")
    assert resp.status_code == 200
    assert resp.get_json()["filters"]["window_days"] == 14


def test_overview_app_id_inexistente_no_es_400(app_cockpit_on):
    resp = app_cockpit_on.test_client().get("/api/devops/overview?app_id=zzz-no-existe")
    assert resp.status_code == 200
    assert resp.get_json()["filters"]["app_id"] is None
