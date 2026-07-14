"""Plan 128 F2 — collect_unpushed_docs (tests primero, monkeypatch de subprocess.run)."""
import subprocess
from pathlib import Path
from types import SimpleNamespace

from services.plans_board import collect_unpushed_docs


def _fake_run(returncode=0, stdout=""):
    def _run(*args, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    return _run


def test_salida_normal_dos_paths(monkeypatch):
    stdout = (
        "Stacky Agents/docs/126_PLAN_A.md\n"
        "Stacky Agents/docs/127_PLAN_B.md\n\n"
        "Stacky Agents/docs/126_PLAN_A.md\n"
    )
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout))
    result = collect_unpushed_docs(Path("."))
    assert result == {"Stacky Agents/docs/126_PLAN_A.md", "Stacky Agents/docs/127_PLAN_B.md"}


def test_path_c_quoteado(monkeypatch):
    stdout = '"Stacky Agents/docs/X con espacio.md"\n'
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout))
    result = collect_unpushed_docs(Path("."))
    assert result == {"Stacky Agents/docs/X con espacio.md"}


def test_returncode_1_devuelve_none(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(1, ""))
    assert collect_unpushed_docs(Path(".")) is None


def test_timeout_y_filenotfound_devuelven_none(monkeypatch):
    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=5)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    assert collect_unpushed_docs(Path(".")) is None

    def _raise_fnf(*args, **kwargs):
        raise FileNotFoundError("git no encontrado")

    monkeypatch.setattr(subprocess, "run", _raise_fnf)
    assert collect_unpushed_docs(Path(".")) is None


def test_root_none_devuelve_none():
    assert collect_unpushed_docs(None) is None


def test_comando_exacto(monkeypatch):
    captured = {}

    def _run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    collect_unpushed_docs(Path("/fake/root"))
    assert captured["args"] == [
        "git",
        "log",
        "--name-only",
        "--pretty=format:",
        "origin/main..HEAD",
        "--",
        "Stacky Agents/docs",
    ]
    assert captured["kwargs"]["cwd"] == "/fake/root" or captured["kwargs"]["cwd"] == str(Path("/fake/root"))
    assert captured["kwargs"].get("shell") is not True
