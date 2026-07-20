"""tests/test_plan189_simulacro.py — Plan 189 F2 (KPI-2 + KPI-3).

El simulacro construye los pasos EXACTOS del rollback real sin ejecutar nada.
- KPI-3: paridad `==` con deploy_planner.build_rollback_plan (+ espía de argumentos
  que valida la FORMA del call-site real deploy_executor.py:312).
- KPI-2: con los transportes de ejecución monkeypatcheados a `raise`, el endpoint
  responde 200 igual (CERO ejecución).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_CFG = {"install_path": "D:\\apps\\miapp"}
_APP = {"id": "miapp", "artifact": {"kind": "folder", "path": "C:\\build"},
        "targets": {"__local__": _CFG}}


def _patch_store(monkeypatch, *, app=_APP, retained=("v2", "v1"), current="v3", locked=False):
    monkeypatch.setattr("services.deploy_store.get_app", lambda _aid: app)
    monkeypatch.setattr("services.deploy_store.retained_versions", lambda *a, **k: list(retained))
    monkeypatch.setattr("services.deploy_store.last_success_version", lambda *a, **k: current)
    monkeypatch.setattr("services.deploy_store.is_locked", lambda *a, **k: locked)


def test_kpi3_paridad_steps(monkeypatch):
    from services import deploy_planner as planner
    from services.rollback_readiness import simulate_rollback_plan

    _patch_store(monkeypatch)
    plan = simulate_rollback_plan("miapp", "__local__", "v2", 30)
    esperado = planner.build_rollback_plan(_APP, "__local__", _CFG, "v2", 30)
    assert plan["steps"] == esperado


def test_kpi3_espia_argumentos(monkeypatch):
    """C2 — el simulacro llama build_rollback_plan con la MISMA forma de
    argumentos que el executor real (deploy_executor.py:312, positional)."""
    from services.rollback_readiness import simulate_rollback_plan

    captured = {}

    def _spy(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return [{"name": "switch", "command": "x", "read_only": False, "housekeeping": False}]

    _patch_store(monkeypatch)
    monkeypatch.setattr("services.rollback_readiness.planner.build_rollback_plan", _spy)
    simulate_rollback_plan("miapp", "__local__", "v2", 30)
    assert captured["kwargs"] == {}
    assert captured["args"] == (_APP, "__local__", _CFG, "v2", 30)


def test_none_version_no_retenida(monkeypatch):
    from services.rollback_readiness import simulate_rollback_plan

    _patch_store(monkeypatch, retained=("v2", "v1"))
    # v9 no está retenida → None (el endpoint lo traduce a 404 version_not_retained).
    assert simulate_rollback_plan("miapp", "__local__", "v9", 30) is None


def _make_client(monkeypatch):
    import config as cfg

    cfg.config.STACKY_DEPLOYMENTS_ENABLED = True
    cfg.config.STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED = True
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_endpoint_404_version_no_retenida(monkeypatch):
    _patch_store(monkeypatch, retained=("v2",))
    client = _make_client(monkeypatch)
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"app_id": "miapp", "target": "__local__", "to_version": "v9"})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "version_not_retained"


def test_kpi2_cero_ejecucion(monkeypatch):
    """Con los transportes de ejecución armados para EXPLOTAR, el preview con
    simulacro responde 200: prueba que NADA se ejecuta."""
    _patch_store(monkeypatch, retained=("v2", "v1"), current="v3")

    def _boom(*a, **k):
        raise AssertionError("ejecución prohibida en el simulacro")

    monkeypatch.setattr("services.deploy_executor.LocalTransport.run", _boom)
    import services.remote_exec as remote_exec
    monkeypatch.setattr(remote_exec, "run_deploy_step", _boom, raising=False)

    client = _make_client(monkeypatch)
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"app_id": "miapp", "target": "__local__", "to_version": "v2"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["plan"]["simulated"] is True
    assert body["plan"]["to_version"] == "v2"


def test_simulated_true_siempre(monkeypatch):
    from services.rollback_readiness import simulate_rollback_plan

    _patch_store(monkeypatch)
    plan = simulate_rollback_plan("miapp", "__local__", "v2", 30)
    assert plan["simulated"] is True
    assert plan["schema_version"] == "189.1"


def test_steps_shape(monkeypatch):
    from services import deploy_planner as planner
    from services.rollback_readiness import simulate_rollback_plan

    _patch_store(monkeypatch)
    plan = simulate_rollback_plan("miapp", "__local__", "v2", 30)
    expected_keys = set(planner._step("x", "cmd").keys())  # {name, command, read_only, housekeeping}
    assert len(plan["steps"]) >= 1
    for s in plan["steps"]:
        assert set(s.keys()) == expected_keys
