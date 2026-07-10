"""Plan 113 F3 — Gate git: rama revertible en worktree, sin tocar el working tree."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from services import doc_documenter


def _run(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _run(root, "init", "-b", "main")
    _run(root, "config", "user.email", "t@t.com")
    _run(root, "config", "user.name", "t")
    (root / "README.md").write_text("hola", encoding="utf-8")
    _run(root, "add", "-A")
    _run(root, "commit", "-m", "init")
    return str(root)


def test_prepare_creates_branch_worktree_without_touching_main(git_repo):
    wt = doc_documenter.prepare_doc_branch(git_repo)
    assert wt is not None and Path(wt).is_dir()
    branch = doc_documenter.branch_of_worktree(wt)
    assert branch and branch.startswith("stacky/doc-")
    # working tree original limpio
    status = _run(git_repo, "status", "--porcelain")
    assert status.stdout.strip() == ""
    doc_documenter.discard_doc_branch(git_repo, branch)  # cleanup


def test_discard_removes_branch_and_worktree(git_repo):
    wt = doc_documenter.prepare_doc_branch(git_repo)
    branch = doc_documenter.branch_of_worktree(wt)
    doc_documenter.discard_doc_branch(git_repo, branch)
    assert not Path(wt).exists()
    branches = _run(git_repo, "branch", "--list", branch).stdout.strip()
    assert branches == ""  # rama borrada


def test_keep_preserves_branch_removes_worktree(git_repo):
    wt = doc_documenter.prepare_doc_branch(git_repo)
    branch = doc_documenter.branch_of_worktree(wt)
    doc_documenter.keep_doc_branch(git_repo, branch)
    assert not Path(wt).exists()  # worktree removido
    branches = _run(git_repo, "branch", "--list", branch).stdout.strip()
    assert branch in branches  # rama conservada
    doc_documenter.discard_doc_branch(git_repo, branch)  # cleanup


def test_prepare_returns_none_on_non_git(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert doc_documenter.prepare_doc_branch(str(plain)) is None


def test_never_pushes(git_repo, monkeypatch):
    seen = []
    real_run = subprocess.run

    def _spy(cmd, *a, **k):
        seen.append(list(cmd))
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", _spy)
    wt = doc_documenter.prepare_doc_branch(git_repo)
    branch = doc_documenter.branch_of_worktree(wt)
    doc_documenter.keep_doc_branch(git_repo, branch)
    doc_documenter.discard_doc_branch(git_repo, branch)
    all_tokens = [tok for cmd in seen for tok in cmd]
    assert "push" not in all_tokens
    assert "merge" not in all_tokens
    assert "stash" not in all_tokens
    # y el guard duro rechaza push explícito
    with pytest.raises(ValueError):
        doc_documenter._git(git_repo, "push", "origin", "main")
