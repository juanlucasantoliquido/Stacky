from __future__ import annotations

import subprocess

from services.pre_run_git import run_pull_check


def test_pull_check_disabled_warns_for_missing_workspace(tmp_path):
    missing = tmp_path / "missing"

    result = run_pull_check(str(missing), enabled=False, required=False, fetch=False)

    assert result.ok is True
    assert result.errors == []
    assert result.warnings
    assert "no existe" in result.warnings[0]


def test_pull_check_required_fails_for_non_git_workspace(tmp_path):
    result = run_pull_check(str(tmp_path), enabled=True, required=True, fetch=False)

    assert result.ok is False
    assert result.errors == ["workspace no es un repositorio git"]


def test_pull_check_git_repo_skips_fetch_when_disabled(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    result = run_pull_check(str(tmp_path), enabled=False, required=False, fetch=False)

    assert result.ok is True
    assert result.repo_root
    assert result.steps[-1].name == "fetch"
    assert result.steps[-1].skipped is True


def test_run_git_injects_noninteractive_auth_and_redacts(monkeypatch):
    from pathlib import Path

    from services import pre_run_git

    captured = {}

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(pre_run_git.subprocess, "run", fake_run)
    step = pre_run_git._run_git(
        Path("."), ["fetch", "--prune"], 5, auth_header="Basic SUPERSECRET=="
    )

    # credential.helper= y core.longpaths=true SIEMPRE; extraheader con el PAT.
    assert "credential.helper=" in captured["cmd"]
    assert "core.longpaths=true" in captured["cmd"]
    assert "http.extraheader=Authorization: Basic SUPERSECRET==" in captured["cmd"]
    # El PAT NO debe quedar en el command logueado del GitStep (no fuga a SSE/logs).
    assert all("SUPERSECRET" not in part for part in step.command)
    assert any("redacted" in part for part in step.command)


def test_pull_check_fetch_acquires_and_releases_lock(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Dos llamadas secuenciales con fetch activo: si el lock no se liberara, la
    # 2da colgaría/omitiría. Ambas completan y ambas ejecutan el step de fetch.
    r1 = run_pull_check(str(tmp_path), enabled=True, required=False, fetch=True, timeout_seconds=5)
    r2 = run_pull_check(str(tmp_path), enabled=True, required=False, fetch=True, timeout_seconds=5)

    assert r1.ok is True and r2.ok is True
    assert any(s.name == "fetch" and not s.skipped for s in r1.steps)
    assert any(s.name == "fetch" and not s.skipped for s in r2.steps)
