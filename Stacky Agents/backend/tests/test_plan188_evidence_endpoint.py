"""tests/test_plan188_evidence_endpoint.py — Plan 188 F2.

Congela el contrato HTTP de POST /api/devops/deployments/evidence: shape exacto
del 200, 404 con ledger real vacío, 400 por campos faltantes y logueo
estructurado del evento (target EXACTO del monkeypatch, C7).
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

MASTER = "STACKY_DEPLOYMENTS_ENABLED"
FLAG = "STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED"


def _golden():
    return {
        "run_id": "dr-golden-1", "app_id": "miapp", "target": "__local__",
        "action": "deploy", "version_id": "1.4.2", "status": "failed_smoke",
        "started_at": "2026-07-18T10:00:00+00:00", "duration_ms": 60000,
        "steps": [
            {"name": "activate", "ok": False, "ms": 200, "detail": "boom",
             "stdout": "line a\nline b", "stderr": "trace"},
        ],
        "smoke": {"kind": "http", "ok": False, "detail": "status=500"},
    }


@pytest.fixture
def app_on():
    import config as cfg
    orig_m = getattr(cfg.config, MASTER, False)
    orig_f = getattr(cfg.config, FLAG, False)
    cfg.config.STACKY_DEPLOYMENTS_ENABLED = True
    cfg.config.STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEPLOYMENTS_ENABLED = orig_m
    cfg.config.STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED = orig_f


def _install(monkeypatch, ledger):
    from services import deploy_store

    def _rl(app_id=None, target=None, limit=100):
        rows = list(ledger)
        if app_id is not None:
            rows = [r for r in rows if r.get("app_id") == app_id]
        if target is not None:
            rows = [r for r in rows if r.get("target") == target]
        return rows[:limit]

    monkeypatch.setattr(deploy_store, "read_ledger", _rl)
    monkeypatch.setattr(deploy_store, "get_app",
                        lambda aid: {"id": "miapp", "name": "MiApp"} if aid == "miapp" else None)


def test_200_shape_completo(app_on, monkeypatch):
    _install(monkeypatch, [_golden()])
    client = app_on.test_client()
    resp = client.post("/api/devops/deployments/evidence",
                       json={"app_id": "miapp", "target": "__local__", "run_id": "dr-golden-1"})
    assert resp.status_code == 200
    ev = resp.get_json()["evidence"]
    assert set(ev.keys()) == {"summary", "modal_text", "markdown", "json_payload"}
    assert ev["json_payload"]["schema_version"] == "188.1"
    assert ev["json_payload"]["kind"] == "deploy_failure"


def test_404_run_not_found_con_ledger_real_vacio(app_on, monkeypatch):
    _install(monkeypatch, [])
    client = app_on.test_client()
    resp = client.post("/api/devops/deployments/evidence",
                       json={"app_id": "miapp", "target": "__local__", "run_id": "dr-golden-1"})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "run_not_found"


def test_400_faltan_campos(app_on, monkeypatch):
    _install(monkeypatch, [_golden()])
    client = app_on.test_client()
    base = {"app_id": "miapp", "target": "__local__", "run_id": "dr-golden-1"}
    for missing in ("app_id", "target", "run_id"):
        payload = {k: v for k, v in base.items() if k != missing}
        resp = client.post("/api/devops/deployments/evidence", json=payload)
        assert resp.status_code == 400, f"faltando {missing} debería dar 400"


def test_logger_llamado(app_on, monkeypatch):
    _install(monkeypatch, [_golden()])
    calls = []

    def _rec(source, action, **kwargs):
        calls.append((source, action, kwargs))

    # C7 — target EXACTO: el import de la ruta es intra-función, hay que
    # parchear el método del logger fuente, no el namespace de la ruta.
    monkeypatch.setattr("services.stacky_logger.logger.info", _rec)
    client = app_on.test_client()
    resp = client.post("/api/devops/deployments/evidence",
                       json={"app_id": "miapp", "target": "__local__", "run_id": "dr-golden-1"})
    assert resp.status_code == 200
    assert any(a == "evidence_built" and kw.get("run_id") == "dr-golden-1"
               for _s, a, kw in calls), calls
