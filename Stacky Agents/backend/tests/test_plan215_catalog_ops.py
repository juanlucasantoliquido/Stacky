"""Plan 215 F3 — extensiones aditivas del catálogo: alta manual, re-scan preservador y deep-scan."""
from __future__ import annotations

import os

import pytest

from services import solution_deep_scan as deep
from services import solution_scanner as sc
from services import solution_store as store

# Fixtures LITERALES del Plan 201 (tests/test_plan201_solution_scanner.py).
_SLN = """Microsoft Visual Studio Solution File, Format Version 12.00
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Web.App", "Web.App\\Web.App.csproj", "{11111111-1111-1111-1111-111111111111}"
EndProject
Global
EndGlobal
"""
_CSPROJ_WEB = ('<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup>'
               "<TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>")


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "store_path", lambda: tmp_path / "build_solutions.json")
    yield


def _mk_solution(root, name="Mi.Sln"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "Web.App").mkdir(parents=True, exist_ok=True)
    (root / "Web.App" / "Web.App.csproj").write_text(_CSPROJ_WEB, encoding="utf-8")
    sln = root / f"{name}.sln"
    sln.write_text(_SLN, encoding="utf-8")
    return str(sln)


def test_scan_single_solution_builds_entry(tmp_path):
    sln = _mk_solution(tmp_path / "ws")
    entry = sc.scan_single_solution(sln)
    assert entry is not None
    assert entry["sln_name"] == "Mi.Sln"
    assert entry["slug"]
    assert entry["projects"][0]["type"] == "web"


def test_scan_single_rejects_non_sln_and_missing(tmp_path):
    assert sc.scan_single_solution(str(tmp_path / "no-existe.sln")) is None
    txt = tmp_path / "leeme.txt"
    txt.write_text("x", encoding="utf-8")
    assert sc.scan_single_solution(str(txt)) is None
    assert sc.scan_single_solution("") is None


def test_add_manual_inside_workspace_persists_with_origin_manual(tmp_path):
    ws = tmp_path / "ws"
    sln = _mk_solution(ws)
    block = store.add_manual_solution(str(ws), sln)
    assert len(block["solutions"]) == 1
    assert block["solutions"][0]["origin"] == "manual"
    assert block["solutions"][0]["tracked"] is True
    # visible desde el catálogo del 201 (misma key cruda del workspace)
    assert len(store.load_catalog(str(ws))["solutions"]) == 1


def test_add_manual_outside_workspace_rejected(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = _mk_solution(tmp_path / "afuera")
    with pytest.raises(ValueError) as exc:
        store.add_manual_solution(str(ws), outside)
    assert "workspace" in str(exc.value)


def test_add_manual_duplicate_is_noop(tmp_path):
    ws = tmp_path / "ws"
    sln = _mk_solution(ws)
    store.add_manual_solution(str(ws), sln)
    block = store.add_manual_solution(str(ws), sln)
    assert len(block["solutions"]) == 1


def test_add_manual_non_sln_rejected(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    txt = ws / "leeme.txt"
    txt.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        store.add_manual_solution(str(ws), str(txt))
    assert ".sln" in str(exc.value)


def test_rescan_preserving_manual_keeps_manual_beyond_walk(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    sln = _mk_solution(ws)
    store.add_manual_solution(str(ws), sln)
    # El walk acotado del 201 NO la encuentra:
    monkeypatch.setattr(store, "scan_solutions_ex",
                        lambda root: {"solutions": [], "truncated": False})
    block = store.rescan_preserving_manual(str(ws))
    paths = [s["sln_path"] for s in block["solutions"]]
    assert os.path.normpath(sln) in paths
    assert block["solutions"][0]["origin"] == "manual"


def test_rescan_drops_manual_whose_file_disappeared(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    sln = _mk_solution(ws)
    store.add_manual_solution(str(ws), sln)
    os.remove(sln)
    monkeypatch.setattr(store, "scan_solutions_ex",
                        lambda root: {"solutions": [], "truncated": False})
    block = store.rescan_preserving_manual(str(ws))
    assert block["solutions"] == []


def test_deep_scan_finds_sln_and_respects_budget(tmp_path):
    ws = tmp_path / "ws"
    sln = _mk_solution(ws)
    (ws / "node_modules" / "hondo").mkdir(parents=True, exist_ok=True)
    (ws / "node_modules" / "hondo" / "Ruido.sln").write_text(_SLN, encoding="utf-8")

    out = deep.deep_scan_sln_paths(str(ws))
    assert os.path.normpath(sln) in [os.path.normpath(p) for p in out["paths"]]
    assert not any("node_modules" in p for p in out["paths"]), "node_modules debe ignorarse"
    assert out["timed_out"] is False

    cortado = deep.deep_scan_sln_paths(str(ws), time_budget_sec=0)
    assert cortado["timed_out"] is True

    assert deep.deep_scan_sln_paths(str(tmp_path / "no-existe")) == {"paths": [], "timed_out": False}
