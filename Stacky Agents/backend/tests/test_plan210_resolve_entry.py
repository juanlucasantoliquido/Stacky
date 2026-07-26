"""Plan 210 F1 — Resolución determinista de la entrada de build.

Prefiere el `.sln` declarado; si no hay, escanea; un `.csproj` suelto NO cuenta
salvo que el perfil lo permita explícitamente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.dev_build_verify import resolve_build_entry  # noqa: E402

_SLN = """Microsoft Visual Studio Solution File, Format Version 12.00
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "App", "App\\App.csproj", "{11111111-1111-1111-1111-111111111111}"
EndProject
"""


def _perfil(**build) -> dict:
    return {"build": build} if build else {}


def _con_sln(root: Path) -> Path:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    sln = src / "App.sln"
    sln.write_text(_SLN, encoding="utf-8")
    app = src / "App"
    app.mkdir(exist_ok=True)
    (app / "App.csproj").write_text("<Project Sdk='Microsoft.NET.Sdk'/>", encoding="utf-8")
    return sln


def test_workspace_missing_returns_none(tmp_path):
    assert resolve_build_entry({}, None)["reason"] == "workspace_missing"
    assert resolve_build_entry({}, "")["reason"] == "workspace_missing"
    assert resolve_build_entry({}, str(tmp_path / "no-existe"))["reason"] == "workspace_missing"


def test_declared_online_solutions_win(tmp_path):
    sln = _con_sln(tmp_path)

    out = resolve_build_entry(_perfil(online_solutions=["src/App.sln"]), str(tmp_path))

    assert out["entry_kind"] == "sln"
    assert out["reason"] == "ok"
    assert out["solutions"] == [os.path.normpath(str(sln))]
    assert os.path.isabs(out["solutions"][0]), "la ruta declarada se resuelve a absoluta"


def test_declared_inexistente_cae_a_escaneo(tmp_path):
    sln = _con_sln(tmp_path)

    out = resolve_build_entry(_perfil(online_solutions=["no/existe.sln"]), str(tmp_path))

    assert out["entry_kind"] == "sln"
    assert out["solutions"] == [str(sln)]


def test_empty_online_solutions_falls_back_to_scan(tmp_path):
    sln = _con_sln(tmp_path)

    out = resolve_build_entry(_perfil(online_solutions=[]), str(tmp_path))

    assert out["entry_kind"] == "sln"
    assert out["solutions"] == [str(sln)]


def test_perfil_sin_build_funciona(tmp_path):
    _con_sln(tmp_path)

    assert resolve_build_entry({}, str(tmp_path))["entry_kind"] == "sln"


def test_no_sln_is_blocking(tmp_path):
    proj = tmp_path / "solo" / "Solo.csproj"
    proj.parent.mkdir(parents=True, exist_ok=True)
    proj.write_text("<Project Sdk='Microsoft.NET.Sdk'/>", encoding="utf-8")

    out = resolve_build_entry({}, str(tmp_path))

    assert out["entry_kind"] == "none", "un .csproj suelto NO es entrada verificable"
    assert out["reason"] == "csproj_not_allowed"


def test_workspace_vacio_es_no_sln(tmp_path):
    (tmp_path / "readme.md").write_text("nada", encoding="utf-8")

    out = resolve_build_entry({}, str(tmp_path))

    assert out["entry_kind"] == "none"
    assert out["reason"] == "no_sln"


def test_csproj_allowed_when_opted_in(tmp_path):
    proj = tmp_path / "solo" / "Solo.csproj"
    proj.parent.mkdir(parents=True, exist_ok=True)
    proj.write_text("<Project Sdk='Microsoft.NET.Sdk'/>", encoding="utf-8")

    out = resolve_build_entry(_perfil(allow_csproj_entry=True), str(tmp_path))

    assert out["entry_kind"] == "csproj"
    assert out["reason"] == "csproj_entry"
    assert out["solutions"]


def test_scanner_import_error_degrades(tmp_path, monkeypatch):
    """Sin el Taller de Compilación no se rompe: degrada a 'no verificado'."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "services.solution_scanner":
            raise ImportError("simulado")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    _con_sln(tmp_path)

    out = resolve_build_entry({}, str(tmp_path))

    assert out["entry_kind"] == "none", "sin scanner no puede AFIRMAR que hay .sln"
    assert out["reason"] in {"no_sln", "csproj_not_allowed"}


def test_determinista(tmp_path):
    _con_sln(tmp_path)

    primero = resolve_build_entry({}, str(tmp_path))
    segundo = resolve_build_entry({}, str(tmp_path))

    assert primero == segundo
