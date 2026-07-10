"""Plan 114 F3 — POST /api/docs/staleness/fix (encola Documentador ACTUALIZAR sobre 1 nota).

Blueprint montado en aislamiento (importlib) — ver nota en test_plan114_graph_payload.py.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from flask import Flask

import config as cfg
from services import doc_documenter

_BACKEND = Path(__file__).resolve().parents[1]


def _client():
    spec = importlib.util.spec_from_file_location("docs_iso_p114_fix", str(_BACKEND / "api" / "docs.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(m.bp, url_prefix="/api/docs")
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DOCS_STALENESS_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_DOCS_DOCUMENTER_ENABLED", True, raising=False)
    yield


def test_fix_404_when_staleness_off(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DOCS_STALENESS_ENABLED", False, raising=False)
    r = _client().post("/api/docs/staleness/fix", json={"note_path": "docs/n.md"})
    assert r.status_code == 404


def test_fix_404_when_documenter_off(monkeypatch):
    monkeypatch.setattr(cfg.config, "STACKY_DOCS_DOCUMENTER_ENABLED", False, raising=False)
    r = _client().post("/api/docs/staleness/fix", json={"note_path": "docs/n.md"})
    assert r.status_code == 404


def test_fix_enqueues_actualizar_for_single_note(monkeypatch):
    captured = {}

    def fake_start(project_name, runtime, *, only_note=None, forced_modes=None):
        captured.update(project_name=project_name, runtime=runtime,
                        only_note=only_note, forced_modes=forced_modes)
        return "run-xyz"

    monkeypatch.setattr(doc_documenter, "start_documenter_run", fake_start)
    monkeypatch.setattr("project_manager.get_active_project", lambda: "proj")
    r = _client().post("/api/docs/staleness/fix", json={"note_path": "docs/n.md"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["run_id"] == "run-xyz"
    assert captured["only_note"] == "docs/n.md"
    assert captured["forced_modes"] == [doc_documenter.DocumenterMode.ACTUALIZAR]
