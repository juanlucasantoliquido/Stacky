"""Plan 201 F3 — Detección de toolchain y doctor.

El servicio nunca instala nada y nunca lanza: si no puede compilar, lo dice.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import build_toolchain as bt  # noqa: E402


def test_msbuild_detected_via_vswhere(tmp_path, monkeypatch):
    msbuild = tmp_path / "MSBuild.exe"
    msbuild.write_text("x", encoding="utf-8")
    monkeypatch.setattr(bt, "_vswhere_path", lambda: str(tmp_path / "vswhere.exe"))
    monkeypatch.setattr(bt, "_run", lambda args, timeout=20: (0, f"{msbuild}\n", ""))
    monkeypatch.setattr(bt, "_which", lambda exe: "/usr/bin/dotnet")

    tc = bt.detect_toolchain()

    assert tc["available"] is True
    assert tc["builder"] == "msbuild", "MSBuild es el camino primario en Windows"
    assert tc["msbuild_path"] == str(msbuild)
    assert tc["remediation"] is None


def test_dotnet_fallback_when_no_msbuild(monkeypatch):
    monkeypatch.setattr(bt, "_vswhere_path", lambda: None)
    monkeypatch.setattr(bt, "_which", lambda exe: "C:\\dotnet\\dotnet.exe" if exe == "dotnet" else None)
    monkeypatch.setattr(bt, "_run", lambda args, timeout=20: (0, "8.0.404\n", ""))

    tc = bt.detect_toolchain()

    assert tc["available"] is True
    assert tc["builder"] == "dotnet"
    assert tc["version"] == "8.0.404"
    assert tc["msbuild_path"] is None


def test_vswhere_sin_msbuild_cae_a_dotnet(monkeypatch):
    monkeypatch.setattr(bt, "_vswhere_path", lambda: "C:\\vswhere.exe")
    monkeypatch.setattr(bt, "_which", lambda exe: "C:\\dotnet.exe")
    llamadas = []

    def _run(args, timeout=20):
        llamadas.append(args)
        if "vswhere" in args[0]:
            return (0, "", "")  # vswhere corre pero no encuentra MSBuild
        return (0, "9.0.100\n", "")

    monkeypatch.setattr(bt, "_run", _run)

    tc = bt.detect_toolchain()

    assert tc["builder"] == "dotnet"
    assert len(llamadas) == 2


def test_dotnet_roto_devuelve_doctor(monkeypatch):
    monkeypatch.setattr(bt, "_vswhere_path", lambda: None)
    monkeypatch.setattr(bt, "_which", lambda exe: "C:\\dotnet.exe")
    monkeypatch.setattr(bt, "_run", lambda args, timeout=20: (1, "", "boom"))

    tc = bt.detect_toolchain()

    assert tc["available"] is False
    assert tc["builder"] is None


def test_doctor_when_nothing_available(monkeypatch):
    monkeypatch.setattr(bt, "_vswhere_path", lambda: None)
    monkeypatch.setattr(bt, "_which", lambda exe: None)

    tc = bt.detect_toolchain()

    assert tc["available"] is False
    assert tc["builder"] is None
    assert tc["remediation"]["command"]
    assert tc["remediation"]["url"].startswith("https://")
    assert "instal" in tc["remediation"]["message"].lower()


def test_never_raises_on_subprocess_error(monkeypatch):
    monkeypatch.setattr(bt, "_vswhere_path", lambda: "C:\\vswhere.exe")

    def _boom(args, timeout=20):
        raise OSError("subprocess roto")

    monkeypatch.setattr(bt, "_run", _boom)

    tc = bt.detect_toolchain()

    assert tc["available"] is False
    assert tc["remediation"] is not None


def test_doctor_no_es_la_constante_mutable(monkeypatch):
    monkeypatch.setattr(bt, "_vswhere_path", lambda: None)
    monkeypatch.setattr(bt, "_which", lambda exe: None)

    primero = bt.detect_toolchain()
    primero["remediation"]["command"] = "MUTADO"
    segundo = bt.detect_toolchain()

    assert segundo["remediation"]["command"] != "MUTADO", "el doctor debe devolver copias"


def test_nunca_usa_shell_true():
    fuente = (ROOT / "services" / "build_toolchain.py").read_text(encoding="utf-8")

    assert "shell=True" not in fuente, "siempre lista de args, nunca string de shell"
