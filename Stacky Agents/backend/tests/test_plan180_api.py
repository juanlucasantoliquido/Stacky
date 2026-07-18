"""Plan 180 — Puente diff→repo: flags (F0) + API del blueprint db_compare_repo (F4).

Ver Stacky Agents/docs/180_PLAN_PUENTE_DIFF_REPO_...md §F0 y §F4.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS


def _spec(key: str):
    for s in FLAG_REGISTRY:
        if s.key == key:
            return s
    return None


# ─────────────────────────── F0 — Flags ───────────────────────────

def test_flags_registradas():
    enabled = _spec("STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED")
    globs = _spec("STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS")
    max_files = _spec("STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES")
    assert enabled is not None and globs is not None and max_files is not None
    assert enabled.type == "bool"
    assert enabled.default is True
    assert globs.type == "csv"
    assert globs.default is None  # gotcha _CURATED_DEFAULTS_ON: sin default= en el spec
    assert max_files.type == "int"
    assert max_files.default is None
    assert (max_files.min_value, max_files.max_value) == (100, 50000)
    for spec in (enabled, globs, max_files):
        assert spec.requires == "STACKY_DB_COMPARE_ENABLED"


def test_flags_en_categoria():
    keys = _CATEGORY_KEYS["comparador_bd"]
    assert "STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED" in keys
    assert "STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS" in keys
    assert "STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES" in keys


def test_config_attrs_existen_con_tipo():
    # Determinista (fix C9): solo verifica tipos, no valores dependientes del env.
    import config as _config

    assert isinstance(_config.config.STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED, bool)
    assert isinstance(_config.config.STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS, str)
    assert isinstance(_config.config.STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES, int)


# ─────────────────────────── F4 — API ───────────────────────────

import runtime_paths
import services.dbcompare_repo_scripts as repo_mod
import services.dbcompare_runs as dbcompare_runs


def _mkfile(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _set_ws(monkeypatch, ws):
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: ws)


def _install(tmp_path, monkeypatch, *, master=True, bridge=True, ws=None):
    import config as cfg

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dbcompare_runs, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: ws)
    monkeypatch.setattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", master, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED", bridge, raising=False)
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _write_run(tmp_path, run_id, **fields):
    d = tmp_path / "db_compare" / "runs"
    d.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": run_id, "source_alias": "DEV", "target_alias": "TEST",
        "engine": "mssql", "status": "done",
        "started_at": "2026-07-18T12:00:00Z", "finished_at": "2026-07-18T12:01:00Z",
    }
    run.update(fields)
    (d / f"{run_id}.json").write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")


def _write_index(tmp_path, ws, scripts):
    d = tmp_path / "db_compare" / "repo_scripts"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.json").write_text(
        json.dumps({"version": 1, "workspace_root": str(ws), "scripts": scripts}),
        encoding="utf-8",
    )


def _install_counter(monkeypatch):
    calls = {"n": 0}
    real = repo_mod.build_index

    def counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(repo_mod, "build_index", counting)
    return calls


_ROUTES = [
    ("get", "/api/db-compare/repo-scripts"),
    ("post", "/api/db-compare/repo-scripts/refresh"),
    ("get", "/api/db-compare/runs/run_x/repo-coverage"),
]


def test_403_flags_off(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch, master=False, bridge=True)
    for method, path in _ROUTES:
        assert getattr(c, method)(path).status_code == 403
    c2 = _install(tmp_path, monkeypatch, master=True, bridge=False)
    for method, path in _ROUTES:
        assert getattr(c2, method)(path).status_code == 403


def test_sin_workspace_noop(tmp_path, monkeypatch):
    c = _install(tmp_path, monkeypatch, ws=None)
    r = c.get("/api/db-compare/repo-scripts")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["index"] is None and body["workspace"] is None


def test_get_autoescanea_primera_vez(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _mkfile(ws / "trunk/BD/real/600001 - c.sql", "INSERT INTO C (id) VALUES (1);")
    c = _install(tmp_path, monkeypatch, ws=ws)
    calls = _install_counter(monkeypatch)
    r1 = c.get("/api/db-compare/repo-scripts")
    assert r1.status_code == 200 and r1.get_json()["index"] is not None
    r2 = c.get("/api/db-compare/repo-scripts")
    assert r2.status_code == 200 and r2.get_json()["index"] is not None
    assert calls["n"] == 1  # segundo GET NO re-escanea


def test_cambio_de_proyecto_reescanea(tmp_path, monkeypatch):
    ws_a = tmp_path / "wsA"
    ws_b = tmp_path / "wsB"
    _mkfile(ws_a / "trunk/BD/a/600001 - a.sql", "INSERT INTO A (id) VALUES (1);")
    _mkfile(ws_b / "trunk/BD/b/600002 - b.sql", "INSERT INTO B (id) VALUES (1);")
    c = _install(tmp_path, monkeypatch, ws=ws_a)
    repo_mod.build_index()  # persiste índice de A (real, sin contar)
    _set_ws(monkeypatch, ws_b)
    calls = _install_counter(monkeypatch)
    r = c.get("/api/db-compare/repo-scripts")
    assert r.status_code == 200
    assert calls["n"] == 1  # índice de A no sirve para B => reescanea
    assert r.get_json()["workspace"] == str(ws_b)


def test_refresh_fuerza_reescaneo(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _mkfile(ws / "trunk/BD/real/600001 - c.sql", "INSERT INTO C (id) VALUES (1);")
    c = _install(tmp_path, monkeypatch, ws=ws)
    repo_mod.build_index()  # índice ya existe
    calls = _install_counter(monkeypatch)
    r = c.post("/api/db-compare/repo-scripts/refresh")
    assert r.status_code == 200 and r.get_json()["index"] is not None
    assert calls["n"] == 1


def test_coverage_run_inexistente_404(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    c = _install(tmp_path, monkeypatch, ws=ws)
    r = c.get("/api/db-compare/runs/nope/repo-coverage")
    assert r.status_code == 404


def test_coverage_run_sin_diff_409(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    c = _install(tmp_path, monkeypatch, ws=ws)
    _write_run(tmp_path, "run_running", status="running", diff=None)
    r = c.get("/api/db-compare/runs/run_running/repo-coverage")
    assert r.status_code == 409


def test_coverage_feliz(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    c = _install(tmp_path, monkeypatch, ws=ws)
    diff = {"items": [
        {"object_type": "table", "schema": "dbo", "name": "RIDIOMA", "action": "changed", "severity": "warn"},
        {"object_type": "table", "schema": "dbo", "name": "RTABL", "action": "added", "severity": "info"},
        {"object_type": "table", "schema": "dbo", "name": "RNUEVA", "action": "added", "severity": "danger"},
    ]}
    _write_run(tmp_path, "run_done", status="done", diff=diff)
    _write_index(tmp_path, ws, [
        {"path": "a.sql", "ticket": "600001", "tables": ["RIDIOMA"], "tables_qualified": [], "mtime": 1},
        {"path": "b.sql", "ticket": "600002", "tables": ["RTABL"], "tables_qualified": [], "mtime": 2},
    ])
    r = c.get("/api/db-compare/runs/run_done/repo-coverage")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["coverage"]["covered_count"] == 2
    assert body["coverage"]["total_count"] == 3
    assert body["workspace"] == str(ws)
