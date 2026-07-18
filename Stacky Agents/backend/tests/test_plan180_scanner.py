"""Plan 180 F2 — Escáner read-only ACOTADO + índice persistido atómico.

Ver Stacky Agents/docs/180_PLAN_PUENTE_DIFF_REPO_...md §F2 (KPI-2/3/6/7/8).
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import runtime_paths
import services.dbcompare_repo_scripts as mod


def _mkfile(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _install(tmp_path, monkeypatch, ws):
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: ws)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path / "data")


def test_sin_workspace_none(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path / "data")
    assert mod.build_index() is None


def test_indexa_convencion_prior_art(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _mkfile(ws / "trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql",
            "INSERT INTO RIDIOMA (id) VALUES (1);")
    _install(tmp_path, monkeypatch, ws)
    index = mod.build_index()
    assert index is not None
    assert len(index["scripts"]) == 1
    s = index["scripts"][0]
    assert s["ticket"] == "600804"
    assert s["tables"] == ["RIDIOMA"]
    assert s["path"] == "trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql"
    assert index["version"] == 1
    assert index["workspace_root"] == str(ws)
    assert index["truncated"] is False
    assert index["truncated_reason"] is None


def test_indice_determinista(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _mkfile(ws / "trunk/BD/a/600001 - a.sql", "CREATE TABLE dbo.A (id INT);")
    _mkfile(ws / "trunk/BD/b/600002 - b.sql", "INSERT INTO B (id) VALUES (1);")
    _install(tmp_path, monkeypatch, ws)
    first = mod.build_index()
    second = mod.build_index()
    assert first["scripts"] == second["scripts"]


def test_cap_reportado(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    for i in range(5):
        _mkfile(ws / f"trunk/BD/dir/6000{i} - t{i}.sql", f"INSERT INTO T{i} (id) VALUES (1);")
    _install(tmp_path, monkeypatch, ws)
    monkeypatch.setattr(mod, "_max_files", lambda: 3)
    index = mod.build_index()
    assert index["files_scanned"] == 3
    assert index["truncated"] is True
    assert index["truncated_reason"] == "max_files"


def test_presupuesto_trunca(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _mkfile(ws / "trunk/BD/dir/600001 - t.sql", "INSERT INTO T (id) VALUES (1);")
    _install(tmp_path, monkeypatch, ws)
    monkeypatch.setattr(mod, "_SCAN_BUDGET_SEC", -1)
    index = mod.build_index()
    assert index["scripts"] == []
    assert index["truncated"] is True
    assert index["truncated_reason"] == "budget"


def test_skip_dirs_excluidos(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _mkfile(ws / "node_modules/x/BD/a.sql", "INSERT INTO A (id) VALUES (1);")
    _mkfile(ws / ".git/BD/b.sql", "INSERT INTO B (id) VALUES (1);")
    _mkfile(ws / "trunk/BD/real/600001 - c.sql", "INSERT INTO C (id) VALUES (1);")
    _install(tmp_path, monkeypatch, ws)
    index = mod.build_index()
    paths = [s["path"] for s in index["scripts"]]
    assert not any("node_modules" in p for p in paths)
    assert not any(".git" in p for p in paths)
    assert index["dirs_pruned"] >= 2


def test_prune_symlink_junction(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _mkfile(ws / "linkdir/BD/x.sql", "INSERT INTO X (id) VALUES (1);")
    _mkfile(ws / "trunk/BD/real/600001 - c.sql", "INSERT INTO C (id) VALUES (1);")
    _install(tmp_path, monkeypatch, ws)
    real_isjunction = os.path.isjunction
    monkeypatch.setattr(
        os.path, "isjunction",
        lambda p: os.path.basename(str(p)) == "linkdir" or real_isjunction(p),
    )
    index = mod.build_index()
    paths = [s["path"] for s in index["scripts"]]
    assert not any("linkdir" in p for p in paths)
    assert index["dirs_pruned"] >= 1


def test_glob_invalido_descartado(tmp_path, monkeypatch):
    import config as _config

    ws = tmp_path / "ws"
    _mkfile(ws / "trunk/BD/real/600001 - c.sql", "INSERT INTO C (id) VALUES (1);")
    _install(tmp_path, monkeypatch, ws)
    monkeypatch.setattr(
        _config.config, "STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS",
        "C:/**,../**,trunk/BD/**/*.sql", raising=False,
    )
    assert mod._globs() == ["trunk/BD/**/*.sql"]
    index = mod.build_index()  # no debe lanzar
    assert index is not None


def test_workspace_intacto(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _mkfile(ws / "trunk/BD/real/600001 - c.sql", "INSERT INTO C (id) VALUES (1);")
    _install(tmp_path, monkeypatch, ws)
    before = {str(p): p.stat().st_mtime for p in ws.rglob("*") if p.is_file()}
    mod.build_index()
    after = {str(p): p.stat().st_mtime for p in ws.rglob("*") if p.is_file()}
    assert before == after  # ningún archivo creado/modificado bajo ws


def test_load_index_corrupto_none(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _install(tmp_path, monkeypatch, ws)
    idx = mod._index_path()
    idx.write_text("{ basura no json", encoding="utf-8")
    assert mod.load_index() is None


def test_load_index_otro_workspace_none(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _install(tmp_path, monkeypatch, ws)
    idx = mod._index_path()
    idx.write_text(json.dumps({"version": 1, "workspace_root": "C:/otro", "scripts": []}),
                   encoding="utf-8")
    assert mod.load_index() is not None  # existe
    assert mod.load_index_for(ws) is None  # pero es de otro workspace


def test_escritura_atomica_sin_tmp(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _mkfile(ws / "trunk/BD/real/600001 - c.sql", "INSERT INTO C (id) VALUES (1);")
    _install(tmp_path, monkeypatch, ws)
    mod.build_index()
    tmp = mod._index_path().with_suffix(".json.tmp")
    assert not tmp.exists()
