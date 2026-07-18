"""Plan 177 F2 — diff del working tree + intent store (`services/incident_dev_pr.py`).

Usan un repo git temporal REAL para ejercitar el snapshot/delta y `remote_origin_url`.
El intent store se aísla vía STACKY_DATA_DIR (leído por runtime_paths.data_dir).
"""
import subprocess
from pathlib import Path

import pytest

from services import incident_dev_pr as pr


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init")
    _git(path, "config", "user.email", "test@stacky.local")
    _git(path, "config", "user.name", "Stacky Test")
    return path


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_snapshot_and_delta_detects_new_untracked_file(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    baseline = pr.snapshot_worktree(str(repo))
    _write(repo / "a.py", "print('nuevo')\n")
    current = pr.snapshot_worktree(str(repo))
    delta = pr.compute_changed_files(baseline, current)
    assert "a.py" in delta["added_or_modified"]
    assert delta["deleted"] == []


def test_delta_ignores_preexisting_dirty_file_untouched(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    _write(repo / "b.py", "v1\n")
    _git(repo, "add", "b.py")
    _git(repo, "commit", "-m", "add b")
    _write(repo / "b.py", "v2-dirty\n")  # dirty ANTES del run
    baseline = pr.snapshot_worktree(str(repo))
    # el agente NO toca b.py
    current = pr.snapshot_worktree(str(repo))
    delta = pr.compute_changed_files(baseline, current)
    assert "b.py" not in delta["added_or_modified"]


def test_delta_includes_preexisting_dirty_file_reedited(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    _write(repo / "c.py", "v1\n")
    _git(repo, "add", "c.py")
    _git(repo, "commit", "-m", "add c")
    _write(repo / "c.py", "v2-dirty\n")  # dirty ANTES del run
    baseline = pr.snapshot_worktree(str(repo))
    _write(repo / "c.py", "v3-agent\n")  # el agente lo RE-edita
    current = pr.snapshot_worktree(str(repo))
    delta = pr.compute_changed_files(baseline, current)
    assert "c.py" in delta["added_or_modified"]


def test_delta_reports_deleted_file(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    _write(repo / "d.py", "borrame\n")
    _git(repo, "add", "d.py")
    _git(repo, "commit", "-m", "add d")
    baseline = pr.snapshot_worktree(str(repo))  # d.py limpio → no en status
    (repo / "d.py").unlink()  # el agente lo borra
    current = pr.snapshot_worktree(str(repo))
    delta = pr.compute_changed_files(baseline, current)
    assert "d.py" in delta["deleted"]
    assert "d.py" not in delta["added_or_modified"]


def test_classify_splits_tests_from_code():
    out = pr.classify_changed_files(
        ["src/x.py", "backend/tests/test_x.py", "web/x.test.ts"]
    )
    assert out["code"] == ["src/x.py"]
    assert "backend/tests/test_x.py" in out["tests"]
    assert "web/x.test.ts" in out["tests"]


def test_resolve_repo_root_returns_toplevel_for_subdir(tmp_path):
    import os

    repo = _init_repo(tmp_path / "repo")
    sub = repo / "pkg" / "sub"
    sub.mkdir(parents=True)
    top = pr.resolve_repo_root(str(sub))
    assert top is not None
    assert os.path.samefile(top, repo)
    # vacío / no-git → None
    assert pr.resolve_repo_root("") is None
    nogit = tmp_path / "nogit"
    nogit.mkdir()
    assert pr.resolve_repo_root(str(nogit)) is None
    assert pr.resolve_repo_root(str(tmp_path / "doesnotexist")) is None


def test_intent_store_roundtrip_and_mark_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path / "data"))
    pr.record_intent(999, {"open_pr": True, "repo_root": "/x", "baseline": {"entries": {}}})
    got = pr.get_intent(999)
    assert got is not None
    assert got["open_pr"] is True
    assert got["repo_root"] == "/x"
    pr.mark_intent(999, pr_url="http://pr/1", status="opened")
    pr.mark_intent(999, pr_url="http://pr/1", status="opened")  # dos veces, idempotente
    final = pr.get_intent(999)
    assert final["pr_url"] == "http://pr/1"
    assert final["status"] == "opened"
    assert final["open_pr"] is True  # el merge preserva lo anterior
    assert pr.get_intent(12345) is None  # inexistente


def test_remote_origin_url_reads_origin(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    _git(repo, "remote", "add", "origin", "https://example.test/org/repo.git")
    assert pr.remote_origin_url(str(repo)) == "https://example.test/org/repo.git"
    # repo sin origin → None
    repo2 = _init_repo(tmp_path / "repo2")
    assert pr.remote_origin_url(str(repo2)) is None
    # vacío / no-git → None
    assert pr.remote_origin_url("") is None
    nogit = tmp_path / "nogit"
    nogit.mkdir()
    assert pr.remote_origin_url(str(nogit)) is None
