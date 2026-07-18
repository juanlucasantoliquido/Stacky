"""tests/test_plan188_evidence_flag.py — Plan 188 F0.

Wiring vertical slice: FlagSpec STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED
(bool, default ON, requires panel 87), pertenencia a _CURATED_DEFAULTS_ON, y
endpoint POST /api/devops/deployments/evidence guardado por el master del
Centro (STACKY_DEPLOYMENTS_ENABLED) + la flag propia (404 si cualquiera OFF,
400 payload incompleto, 404 run inexistente).
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

FLAG = "STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED"
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


def _make_app(master: bool, evidence: bool):
    import config as cfg
    cfg.config.STACKY_DEPLOYMENTS_ENABLED = master
    cfg.config.STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED = evidence
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def restore_flags():
    import config as cfg
    orig_master = getattr(cfg.config, MASTER, False)
    orig_flag = getattr(cfg.config, FLAG, False)
    yield
    cfg.config.STACKY_DEPLOYMENTS_ENABLED = orig_master
    cfg.config.STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED = orig_flag


def test_endpoint_404_evidence_flag_off(restore_flags):
    app = _make_app(master=True, evidence=False)
    client = app.test_client()
    resp = client.post("/api/devops/deployments/evidence",
                       json={"app_id": "miapp", "target": "__local__", "run_id": "r1"})
    assert resp.status_code == 404


def test_endpoint_404_master_off(restore_flags):
    app = _make_app(master=False, evidence=True)
    client = app.test_client()
    resp = client.post("/api/devops/deployments/evidence",
                       json={"app_id": "miapp", "target": "__local__", "run_id": "r1"})
    assert resp.status_code == 404


def test_endpoint_400_payload_incompleto(restore_flags):
    app = _make_app(master=True, evidence=True)
    client = app.test_client()
    # Falta run_id.
    resp = client.post("/api/devops/deployments/evidence",
                       json={"app_id": "miapp", "target": "__local__"})
    assert resp.status_code == 400


def test_endpoint_404_run_inexistente(restore_flags, monkeypatch):
    app = _make_app(master=True, evidence=True)
    monkeypatch.setattr("services.deploy_store.read_ledger", lambda **kw: [])
    client = app.test_client()
    resp = client.post("/api/devops/deployments/evidence",
                       json={"app_id": "miapp", "target": "__local__", "run_id": "nope"})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "run_not_found"
