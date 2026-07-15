"""Plan 137 F4 — Endpoint GET /api/docs/documenter/runs (historial persistente).

Tests corridos por archivo con el venv real del repo (backend/.venv, py3.13).
Calca el patrón de fixture app+flag de tests/test_plan113_endpoints.py:18.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from services import doc_documenter


def _make_app(master_on: bool, v2_on: bool):
    import config as cfg
    cfg.config.STACKY_DOCS_DOCUMENTER_ENABLED = master_on
    cfg.config.STACKY_DOCS_DOCUMENTER_V2_ENABLED = v2_on
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


def _flags(master_on: bool, v2_on: bool):
    import config as cfg
    orig_master = getattr(cfg.config, "STACKY_DOCS_DOCUMENTER_ENABLED", False)
    orig_v2 = getattr(cfg.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", False)
    app = _make_app(master_on, v2_on)
    return app, orig_master, orig_v2


@pytest.fixture
def app_master_off():
    import config as cfg
    app, orig_master, orig_v2 = _flags(False, False)
    yield app
    cfg.config.STACKY_DOCS_DOCUMENTER_ENABLED = orig_master
    cfg.config.STACKY_DOCS_DOCUMENTER_V2_ENABLED = orig_v2


@pytest.fixture
def app_master_on_v2_off():
    import config as cfg
    app, orig_master, orig_v2 = _flags(True, False)
    yield app
    cfg.config.STACKY_DOCS_DOCUMENTER_ENABLED = orig_master
    cfg.config.STACKY_DOCS_DOCUMENTER_V2_ENABLED = orig_v2


@pytest.fixture
def app_both_on():
    import config as cfg
    app, orig_master, orig_v2 = _flags(True, True)
    yield app
    cfg.config.STACKY_DOCS_DOCUMENTER_ENABLED = orig_master
    cfg.config.STACKY_DOCS_DOCUMENTER_V2_ENABLED = orig_v2


def test_runs_404_si_master_off(app_master_off):
    r = app_master_off.test_client().get("/api/docs/documenter/runs")
    assert r.status_code == 404


def test_runs_lista_vacia_v2_off(app_master_on_v2_off):
    r = app_master_on_v2_off.test_client().get("/api/docs/documenter/runs")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "runs": []}


def test_runs_devuelve_historial(app_both_on, monkeypatch, tmp_path):
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    doc_documenter._persist_run_report("rr1", {
        "state": "completed", "written": ["a.md"], "skipped": [], "modes": ["ENRIQUECER"],
        "branch": "stacky/doc-x", "degraded": False,
    })
    r = app_both_on.test_client().get("/api/docs/documenter/runs")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert len(data["runs"]) == 1
    assert data["runs"][0]["run_id"] == "rr1"


def test_status_expone_files_y_modes_skipped(app_both_on):
    # C9 — anti test-order pollution: no dejar "r7" en el registry compartido.
    with doc_documenter._registry_lock:
        snapshot = dict(doc_documenter._run_registry)
    try:
        rec = doc_documenter._new_run_record("P", "claude_code_cli")
        rec.update({
            "state": "completed",
            "files": [{"path": "a.md", "action": "create", "citations": {"total": 1, "ok": 1, "bad": []}}],
            "modes_skipped": [{"mode": "NORMALIZAR", "reason": "sin_notas_para_normalizar"}],
        })
        with doc_documenter._registry_lock:
            doc_documenter._run_registry["r7"] = rec
        r = app_both_on.test_client().get("/api/docs/documenter/status?run=r7")
        data = r.get_json()
        assert r.status_code == 200
        assert data["files"] == [{"path": "a.md", "action": "create",
                                  "citations": {"total": 1, "ok": 1, "bad": []}}]
        assert data["modes_skipped"] == [{"mode": "NORMALIZAR", "reason": "sin_notas_para_normalizar"}]
    finally:
        with doc_documenter._registry_lock:
            doc_documenter._run_registry.clear()
            doc_documenter._run_registry.update(snapshot)


def test_status_v2_off_files_y_modes_skipped_vacios(app_master_on_v2_off):
    # KPI-6 (DoD) — con V2 OFF, GET /documenter/status sigue trayendo los
    # campos de hoy MÁS files:[] y modes_skipped:[] (backward-compatible).
    with doc_documenter._registry_lock:
        snapshot = dict(doc_documenter._run_registry)
    try:
        rec = doc_documenter._new_run_record("P", "claude_code_cli")
        rec.update({"state": "completed"})
        with doc_documenter._registry_lock:
            doc_documenter._run_registry["r8"] = rec
        r = app_master_on_v2_off.test_client().get("/api/docs/documenter/status?run=r8")
        data = r.get_json()
        assert r.status_code == 200
        assert data["files"] == []
        assert data["modes_skipped"] == []
    finally:
        with doc_documenter._registry_lock:
            doc_documenter._run_registry.clear()
            doc_documenter._run_registry.update(snapshot)
