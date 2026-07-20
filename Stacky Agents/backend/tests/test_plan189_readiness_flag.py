"""tests/test_plan189_readiness_flag.py — Plan 189 F0.

Wiring vertical slice: FlagSpec STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED
(bool, default ON, requires panel 87), pertenencia a _CURATED_DEFAULTS_ON, y
endpoint POST /api/devops/deployments/rollback/preview guardado por el master
del Centro (STACKY_DEPLOYMENTS_ENABLED) + la flag propia. El preview NO exige
_execute_on(): acá no se ejecuta NADA (solo lecturas locales).

Modos: single {app_id, target[, to_version]} | batch {pairs: [...]} (C3).
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

FLAG = "STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED"
MASTER = "STACKY_DEPLOYMENTS_ENABLED"


def _spec():
    from services.harness_flags import FLAG_REGISTRY

    return next((s for s in FLAG_REGISTRY if s.key == FLAG), None)


def test_flag_declarada_bool_default_on():
    spec = _spec()
    assert spec is not None, f"FlagSpec {FLAG} no está en el registry"
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_flag_en_curated_defaults_on():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert FLAG in _CURATED_DEFAULTS_ON


def _make_app(master: bool, readiness: bool, execute: bool = True):
    import config as cfg

    cfg.config.STACKY_DEPLOYMENTS_ENABLED = master
    cfg.config.STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED = readiness
    cfg.config.STACKY_DEPLOYMENTS_EXECUTE_ENABLED = execute
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def restore_flags():
    import config as cfg

    orig_master = getattr(cfg.config, MASTER, False)
    orig_flag = getattr(cfg.config, FLAG, False)
    orig_exec = getattr(cfg.config, "STACKY_DEPLOYMENTS_EXECUTE_ENABLED", False)
    yield
    cfg.config.STACKY_DEPLOYMENTS_ENABLED = orig_master
    cfg.config.STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED = orig_flag
    cfg.config.STACKY_DEPLOYMENTS_EXECUTE_ENABLED = orig_exec


_FAKE_APP = {
    "id": "miapp",
    "artifact": {"kind": "folder", "path": "C:/build"},
    "targets": {"__local__": {"install_path": "D:/apps/miapp"}},
}


def test_preview_404_readiness_off(restore_flags):
    app = _make_app(master=True, readiness=False)
    client = app.test_client()
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"app_id": "miapp", "target": "__local__"})
    assert resp.status_code == 404


def test_preview_404_master_off(restore_flags):
    app = _make_app(master=False, readiness=True)
    client = app.test_client()
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"app_id": "miapp", "target": "__local__"})
    assert resp.status_code == 404


def test_preview_400_payload_incompleto(restore_flags):
    app = _make_app(master=True, readiness=True)
    client = app.test_client()
    # Falta target.
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"app_id": "miapp"})
    assert resp.status_code == 400


def test_preview_404_app_inexistente(restore_flags, monkeypatch):
    app = _make_app(master=True, readiness=True)
    monkeypatch.setattr("services.deploy_store.get_app", lambda _aid: None)
    client = app.test_client()
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"app_id": "nope", "target": "__local__"})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "app_not_found"


def test_preview_200_execute_off(restore_flags, monkeypatch):
    # KPI-2 parcial: el preview NO depende de la flag de ejecución.
    app = _make_app(master=True, readiness=True, execute=False)
    monkeypatch.setattr("services.deploy_store.get_app", lambda _aid: dict(_FAKE_APP))
    monkeypatch.setattr("services.deploy_store.last_success_version", lambda *a, **k: None)
    monkeypatch.setattr("services.deploy_store.retained_versions", lambda *a, **k: [])
    monkeypatch.setattr("services.deploy_store.is_locked", lambda *a, **k: False)
    client = app.test_client()
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"app_id": "miapp", "target": "__local__"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert "readiness" in body
    assert body["plan"] is None


def test_preview_batch_shape(restore_flags, monkeypatch):
    app = _make_app(master=True, readiness=True)
    monkeypatch.setattr("services.deploy_store.get_app", lambda _aid: dict(_FAKE_APP))
    monkeypatch.setattr("services.deploy_store.last_success_version", lambda *a, **k: None)
    monkeypatch.setattr("services.deploy_store.retained_versions", lambda *a, **k: [])
    monkeypatch.setattr("services.deploy_store.is_locked", lambda *a, **k: False)
    client = app.test_client()
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"pairs": [{"app_id": "a", "target": "t"},
                                       {"app_id": "b"}]})  # segundo malformado → se omite
    assert resp.status_code == 200
    body = resp.get_json()
    assert "readiness_map" in body
    assert "a|t" in body["readiness_map"]
    assert "b|" not in body["readiness_map"]  # el malformado no entra


def test_preview_batch_limite(restore_flags):
    app = _make_app(master=True, readiness=True)
    client = app.test_client()
    pairs = [{"app_id": f"a{i}", "target": "t"} for i in range(101)]
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"pairs": pairs})
    assert resp.status_code == 400
    assert "100" in resp.get_json()["error"]


def test_logger_llamado(restore_flags, monkeypatch):
    app = _make_app(master=True, readiness=True)
    monkeypatch.setattr("services.deploy_store.get_app", lambda _aid: dict(_FAKE_APP))
    monkeypatch.setattr("services.deploy_store.last_success_version", lambda *a, **k: None)
    monkeypatch.setattr("services.deploy_store.retained_versions", lambda *a, **k: [])
    monkeypatch.setattr("services.deploy_store.is_locked", lambda *a, **k: False)

    calls = []
    from services import stacky_logger

    monkeypatch.setattr(stacky_logger.logger, "info",
                        lambda *a, **k: calls.append((a, k)))
    client = app.test_client()
    resp = client.post("/api/devops/deployments/rollback/preview",
                       json={"app_id": "miapp", "target": "__local__"})
    assert resp.status_code == 200
    assert any(a[:2] == ("rollback_readiness", "preview_built") for a, _k in calls)
