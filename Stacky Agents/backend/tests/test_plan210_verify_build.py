"""Plan 210 F2 — verify_build: el hecho lo produce la máquina.

Ninguna rama que no haya compilado de verdad puede terminar con `gate_ok`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dev_build_verify as dbv  # noqa: E402

_ADO = 210001
_SLN_TEXT = """Microsoft Visual Studio Solution File, Format Version 12.00
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "App", "App\\App.csproj", "{11111111-1111-1111-1111-111111111111}"
EndProject
"""


@pytest.fixture(autouse=True)
def _sin_perfil(monkeypatch):
    from services import client_profile

    monkeypatch.setattr(client_profile, "load_effective_client_profile",
                        lambda project: {}, raising=True)
    monkeypatch.setattr(dbv, "_POLL_INTERVAL_SEC", 0, raising=True)


@pytest.fixture
def ws(tmp_path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "App.sln").write_text(_SLN_TEXT, encoding="utf-8")
    app = src / "App"
    app.mkdir(exist_ok=True)
    (app / "App.csproj").write_text("<Project Sdk='Microsoft.NET.Sdk'/>", encoding="utf-8")
    return tmp_path


def _toolchain(monkeypatch, available=True):
    monkeypatch.setattr(dbv, "_detect_toolchain_safe", lambda: {
        "available": available, "builder": "dotnet" if available else None,
        "version": "8.0.404" if available else None, "remediation": None,
    }, raising=True)


def _catalogo(monkeypatch, ws, slug="app"):
    from services import solution_store

    sln = str(ws / "src" / "App.sln")
    monkeypatch.setattr(solution_store, "rescan_and_save", lambda w: None, raising=True)
    monkeypatch.setattr(
        solution_store, "load_catalog",
        lambda w: {"scanned_at": None, "truncated": False,
                   "solutions": [{"slug": slug, "sln_path": sln}]},
        raising=True,
    )


def _builder(monkeypatch, status="success", returncodes=None, base_dir="", none_always=False):
    from services import solution_builder

    llamadas: list = []
    monkeypatch.setattr(solution_builder, "start_build",
                        lambda slugs, unified, workspace_root:
                            llamadas.append((slugs, unified)) or "bid-1",
                        raising=True)
    if none_always:
        monkeypatch.setattr(solution_builder, "get_status", lambda bid: None, raising=True)
        return llamadas

    estados = [
        {"status": "running", "mode": "single", "slugs": ["app"], "log": [],
         "artifact_ready": False, "error": None, "summary": None},
        {"status": status, "mode": "single", "slugs": ["app"], "log": [],
         "artifact_ready": status == "success", "error": None,
         "summary": {"returncodes": returncodes if returncodes is not None else {"app": 0},
                     "base_dir": base_dir, "status": status}},
    ]
    secuencia = iter(estados)
    ultimo = {"v": estados[-1]}

    def _get_status(bid):
        try:
            ultimo["v"] = next(secuencia)
        except StopIteration:
            pass
        return ultimo["v"]

    monkeypatch.setattr(solution_builder, "get_status", _get_status, raising=True)
    return llamadas


def test_no_sln_writes_blocking_verdict_no_build(tmp_path, monkeypatch):
    from services import solution_builder

    (tmp_path / "readme.md").write_text("nada", encoding="utf-8")
    llamadas: list = []
    monkeypatch.setattr(solution_builder, "start_build",
                        lambda *a, **kw: llamadas.append(a) or "x", raising=True)

    v = dbv.verify_build(ado_id=_ADO, project_name="p", workspace_root=str(tmp_path))

    assert llamadas == [], "sin .sln NUNCA se dispara un build"
    assert v.gate_ok is False and v.ok is False
    assert v.reason in {"no_sln", "csproj_not_allowed"}
    assert dbv.read_verdict(_ADO, str(tmp_path)).reason == v.reason


def test_toolchain_missing_verdict(ws, monkeypatch):
    from services import solution_builder

    _toolchain(monkeypatch, available=False)
    llamadas: list = []
    monkeypatch.setattr(solution_builder, "start_build",
                        lambda *a, **kw: llamadas.append(a) or "x", raising=True)

    v = dbv.verify_build(ado_id=_ADO, project_name="p", workspace_root=str(ws))

    assert v.reason == "toolchain_missing"
    assert v.ok is False and v.gate_ok is False
    assert v.entry_kind == "sln"
    assert llamadas == []


def test_workshop_unavailable_when_builder_import_fails(ws, monkeypatch):
    import builtins

    _toolchain(monkeypatch)
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "services" and args and "solution_builder" in (args[2] or ()):
            raise ImportError("simulado")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    v = dbv.verify_build(ado_id=_ADO, project_name="p", workspace_root=str(ws))

    assert v.reason == "build_workshop_unavailable"
    assert v.gate_ok is False


def test_success_verdict_ok_and_gate_ok(ws, monkeypatch):
    _toolchain(monkeypatch)
    _catalogo(monkeypatch, ws)
    base = str(ws / "artefactos")
    _builder(monkeypatch, status="success", returncodes={"app": 0}, base_dir=base)

    v = dbv.verify_build(ado_id=_ADO, project_name="p", workspace_root=str(ws),
                         execution_id=5)

    assert v.ok is True and v.gate_ok is True
    assert v.reason == "ok"
    assert v.entry_kind == "sln"
    assert v.returncode == 0
    assert v.summary_path == os.path.join(base, "build.summary.json")
    assert v.build_id == "bid-1"


def test_build_failed_sets_reason(ws, monkeypatch):
    _toolchain(monkeypatch)
    _catalogo(monkeypatch, ws)
    _builder(monkeypatch, status="failed", returncodes={"app": 1}, base_dir=str(ws))

    v = dbv.verify_build(ado_id=_ADO, project_name="p", workspace_root=str(ws))

    assert v.ok is False and v.gate_ok is False
    assert v.reason == "build_failed"
    assert v.returncode == 1


def test_get_status_none_is_synthetic_failed(ws, monkeypatch):
    _toolchain(monkeypatch)
    _catalogo(monkeypatch, ws)
    _builder(monkeypatch, none_always=True)

    v = dbv.verify_build(ado_id=_ADO, project_name="p", workspace_root=str(ws))

    assert v.reason == "build_failed", "un build perdido nunca es 'ok'"
    assert v.gate_ok is False


def test_sin_slug_en_catalogo_no_dispara_build(ws, monkeypatch):
    from services import solution_builder, solution_store

    _toolchain(monkeypatch)
    monkeypatch.setattr(solution_store, "rescan_and_save", lambda w: None, raising=True)
    monkeypatch.setattr(solution_store, "load_catalog",
                        lambda w: {"solutions": []}, raising=True)
    llamadas: list = []
    monkeypatch.setattr(solution_builder, "start_build",
                        lambda *a, **kw: llamadas.append(a) or "x", raising=True)

    v = dbv.verify_build(ado_id=_ADO, project_name="p", workspace_root=str(ws))

    assert v.reason == "build_failed"
    assert llamadas == []


def test_execution_id_is_stamped(ws, monkeypatch):
    _toolchain(monkeypatch)
    _catalogo(monkeypatch, ws)
    _builder(monkeypatch, base_dir=str(ws))

    dbv.verify_build(ado_id=_ADO, project_name="p", workspace_root=str(ws), execution_id=77)

    assert dbv.read_verdict(_ADO, str(ws)).execution_id == 77


def test_verdict_roundtrip(tmp_path):
    v = dbv.BuildVerdict(
        ok=True, gate_ok=True, entry_kind="sln", solution="a.sln",
        solutions=("a.sln", "b.sln"), returncode=0, summary_path="s.json",
        reason="ok", toolchain={"available": True, "builder": "dotnet", "version": "8"},
        build_id="b1", verified_at="2026-07-25T00:00:00Z", execution_id=9,
        blocking_findings=(), warnings=(),
    )
    dbv.write_verdict(_ADO, str(tmp_path), v)

    leido = dbv.read_verdict(_ADO, str(tmp_path))

    assert leido == v
    assert isinstance(leido.solutions, tuple), "json.load da listas; el frozen espera tuplas"
    assert isinstance(leido.blocking_findings, tuple)


def test_read_verdict_ausente_es_none(tmp_path):
    assert dbv.read_verdict(999999, str(tmp_path)) is None


def test_read_verdict_corrupto_es_none(tmp_path):
    path = dbv.verdict_path(_ADO, str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{{{ roto", encoding="utf-8")

    assert dbv.read_verdict(_ADO, str(tmp_path)) is None


def test_verdict_viejo_sin_execution_id_default_cero(tmp_path):
    path = dbv.verdict_path(_ADO, str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ok": True, "gate_ok": True, "reason": "ok"}),
                    encoding="utf-8")

    assert dbv.read_verdict(_ADO, str(tmp_path)).execution_id == 0


def test_verdict_path_junto_al_deliverable(tmp_path):
    path = dbv.verdict_path(_ADO, str(tmp_path))

    assert path.parts[-4:] == ("Agentes", "outputs", str(_ADO), "build.verdict.json")


def test_ninguna_rama_bloqueante_tiene_gate_ok(ws, monkeypatch):
    """Invariante: si no compiló de verdad, gate_ok es False, sin excepción."""
    for setup in (
        lambda: _toolchain(monkeypatch, available=False),
        lambda: (_toolchain(monkeypatch), _catalogo(monkeypatch, ws),
                 _builder(monkeypatch, status="failed", returncodes={"app": 2},
                          base_dir=str(ws))),
        lambda: (_toolchain(monkeypatch), _catalogo(monkeypatch, ws),
                 _builder(monkeypatch, status="cancelled", returncodes={"app": 0},
                          base_dir=str(ws))),
    ):
        setup()
        v = dbv.verify_build(ado_id=_ADO, project_name="p", workspace_root=str(ws))
        assert v.gate_ok is False, f"{v.reason} no puede ser gate_ok"
        assert v.reason != "ok"
