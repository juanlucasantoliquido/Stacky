"""Plan 113 F5 — Endpoints run/status/decide + lock + diff_stat + selección de modos."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from services import doc_documenter


def _make_app(flag_on: bool):
    import config as cfg
    cfg.config.STACKY_DOCS_DOCUMENTER_ENABLED = flag_on
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def app_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_DOCS_DOCUMENTER_ENABLED", False)
    app = _make_app(False)
    yield app
    cfg.config.STACKY_DOCS_DOCUMENTER_ENABLED = orig


@pytest.fixture
def app_on():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_DOCS_DOCUMENTER_ENABLED", False)
    app = _make_app(True)
    yield app
    cfg.config.STACKY_DOCS_DOCUMENTER_ENABLED = orig


@pytest.fixture(autouse=True)
def _clean_registry():
    with doc_documenter._registry_lock:
        doc_documenter._run_registry.clear()
    yield
    with doc_documenter._registry_lock:
        doc_documenter._run_registry.clear()


def test_run_404_when_flag_off(app_off):
    r = app_off.test_client().post("/api/docs/documenter/run", json={})
    assert r.status_code == 404


def test_status_404_when_flag_off(app_off):
    r = app_off.test_client().get("/api/docs/documenter/status?run=x")
    assert r.status_code == 404


def test_decide_404_when_flag_off(app_off):
    r = app_off.test_client().post("/api/docs/documenter/decide", json={"run": "x", "action": "keep"})
    assert r.status_code == 404


def test_run_returns_run_id_when_flag_on(app_on, monkeypatch):
    monkeypatch.setattr(doc_documenter, "start_documenter_run", lambda proj, rt: "abc123")
    r = app_on.test_client().post("/api/docs/documenter/run", json={"project": "P"})
    assert r.status_code == 200
    assert r.get_json()["run_id"] == "abc123"


def test_run_busy_returns_409(app_on, monkeypatch):
    def _busy(proj, rt):
        raise doc_documenter.DocumenterBusy()
    monkeypatch.setattr(doc_documenter, "start_documenter_run", _busy)
    r = app_on.test_client().post("/api/docs/documenter/run", json={"project": "P"})
    assert r.status_code == 409
    assert r.get_json()["error"] == "documenter_busy"


def _seed_run(run_id="r1", **fields):
    rec = doc_documenter._new_run_record("P", "claude_code_cli")
    rec.update(fields)
    with doc_documenter._registry_lock:
        doc_documenter._run_registry[run_id] = rec
    return run_id


def test_decide_keep_calls_keep_branch(app_on, monkeypatch):
    called = {}
    monkeypatch.setattr(doc_documenter, "keep_doc_branch",
                        lambda tr, br: called.update(tr=tr, br=br))
    _seed_run("r1", state="completed", branch="stacky/doc-x", target_root="/repo")
    r = app_on.test_client().post("/api/docs/documenter/decide",
                                  json={"run": "r1", "action": "keep"})
    assert r.status_code == 200 and called == {"tr": "/repo", "br": "stacky/doc-x"}


def test_decide_discard_calls_discard_branch(app_on, monkeypatch):
    called = {}
    monkeypatch.setattr(doc_documenter, "discard_doc_branch",
                        lambda tr, br: called.update(tr=tr, br=br))
    _seed_run("r2", state="completed", branch="stacky/doc-y", target_root="/repo")
    r = app_on.test_client().post("/api/docs/documenter/decide",
                                  json={"run": "r2", "action": "discard"})
    assert r.status_code == 200 and called == {"tr": "/repo", "br": "stacky/doc-y"}


def test_run_selects_modes_from_health(monkeypatch):
    # Integra selector + orquestador: mock de build_graph (health) + invoke_documenter.
    import services.doc_graph as dg
    monkeypatch.setattr(dg, "build_graph",
                        lambda project_name=None, **k: {"doc_health": {"status": "SIN_DOCS"},
                                                        "nodes": [], "orphans": []})
    monkeypatch.setattr(doc_documenter, "_resolve_target_paths",
                        lambda p: (None, None, None))  # → degradado, sin git
    seen_modes = []
    monkeypatch.setattr(
        doc_documenter, "invoke_documenter",
        lambda mode, ctx, proj, rt, on_execution_started=None:
            seen_modes.append(str(mode.value)) or [])
    report = doc_documenter.run_documenter("P", "claude_code_cli")
    assert report["modes"] == ["RECONSTRUIR", "ENRIQUECER"]
    assert seen_modes == ["RECONSTRUIR", "ENRIQUECER"]


def test_status_includes_diff_stat(app_on):
    _seed_run("r3", state="completed", branch="stacky/doc-z", target_root="/repo",
              diff_stat=" docs/a.md | 3 +++")
    r = app_on.test_client().get("/api/docs/documenter/status?run=r3")
    data = r.get_json()
    assert r.status_code == 200
    assert data["diff_stat"] == " docs/a.md | 3 +++"


def test_status_includes_current_execution_id(app_on):
    """Fix "no me hizo nada" — Tarea 2: el frontend necesita el execution_id en
    curso para enganchar la consola en vivo (CodexConsoleDock)."""
    _seed_run("r4", state="running", current_execution_id=123)
    r = app_on.test_client().get("/api/docs/documenter/status?run=r4")
    data = r.get_json()
    assert r.status_code == 200
    assert data["current_execution_id"] == 123


def test_status_current_execution_id_defaults_to_none(app_on):
    _seed_run("r5", state="running")
    r = app_on.test_client().get("/api/docs/documenter/status?run=r5")
    assert r.get_json()["current_execution_id"] is None


def test_run_documenter_exposes_current_execution_id_while_running(monkeypatch, tmp_path):
    """Fix "no me hizo nada" — Tarea 2: run_documenter debe llamar
    on_execution_started y reflejarlo en el run record ANTES de que el modo
    termine (para que el polling del frontend lo vea mientras corre)."""
    import services.doc_graph as dg
    monkeypatch.setattr(dg, "build_graph",
                        lambda project_name=None, **k: {"doc_health": {"status": "SANA"},
                                                        "nodes": [], "orphans": []})
    monkeypatch.setattr(doc_documenter, "_resolve_target_paths",
                        lambda p: (None, None, str(tmp_path)))
    monkeypatch.chdir(tmp_path)  # evita crear .stacky-docs-proposed en el repo

    seen_during_run = []

    def _fake_invoke(mode, ctx, proj, rt, on_execution_started=None):
        if on_execution_started:
            on_execution_started(555)
        with doc_documenter._registry_lock:
            seen_during_run.append(doc_documenter._run_registry["r6"]["current_execution_id"])
        return []

    monkeypatch.setattr(doc_documenter, "invoke_documenter", _fake_invoke)
    with doc_documenter._registry_lock:
        doc_documenter._run_registry["r6"] = doc_documenter._new_run_record("P", "claude_code_cli")
    doc_documenter.run_documenter("P", "claude_code_cli", run_id="r6")
    assert seen_during_run == [555]


def test_run_documenter_surfaces_error_when_all_modes_empty(monkeypatch, tmp_path):
    """Fix "no me hizo nada" — Tarea 1: si TODOS los modos devuelven 0
    propuestas, el reporte final debe traer un "error" visible (antes quedaba
    100% silencioso: written=[] y skipped=[] sin ninguna pista)."""
    import services.doc_graph as dg
    monkeypatch.setattr(dg, "build_graph",
                        lambda project_name=None, **k: {"doc_health": {"status": "SANA"},
                                                        "nodes": [], "orphans": []})
    monkeypatch.setattr(doc_documenter, "_resolve_target_paths",
                        lambda p: (None, None, str(tmp_path)))
    monkeypatch.chdir(tmp_path)  # evita crear .stacky-docs-proposed en el repo
    def _fake_invoke(mode, ctx, proj, rt, on_execution_started=None):
        if on_execution_started:
            on_execution_started(1)
        return []

    monkeypatch.setattr(doc_documenter, "invoke_documenter", _fake_invoke)
    monkeypatch.setattr(doc_documenter, "_empty_result_reason",
                        lambda eid, raw: "el CLI crasheó por config faltante")

    report = doc_documenter.run_documenter("P", "claude_code_cli")
    assert report["written"] == []
    assert report["error"] is not None
    assert "el CLI crasheó por config faltante" in report["error"]


def test_run_documenter_error_stays_none_when_something_was_written(monkeypatch, tmp_path):
    # tmp_path (no ".", no _resolve_target_paths→None) para no escribir en el
    # CWD del repo (evita ensuciar el working tree con una carpeta-sombra real).
    import services.doc_graph as dg
    monkeypatch.setattr(dg, "build_graph",
                        lambda project_name=None, **k: {"doc_health": {"status": "SANA"},
                                                        "nodes": [], "orphans": []})
    monkeypatch.setattr(doc_documenter, "_resolve_target_paths",
                        lambda p: (None, None, str(tmp_path)))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        doc_documenter, "invoke_documenter",
        lambda mode, ctx, proj, rt, on_execution_started=None: [
            doc_documenter.DocProposal(path="a.md", action="create",
                                       content="x [V]", marks_ok=True)
        ])
    report = doc_documenter.run_documenter("P", "claude_code_cli")
    assert report["written"] == ["a.md"]
    assert report["error"] is None
