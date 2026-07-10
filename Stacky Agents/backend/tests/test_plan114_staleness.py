"""Plan 114 F1 — git_last_commit_epoch + annotate_staleness (repo git real, fechas deterministas)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from services import doc_staleness


# ── helpers de repo git determinista ──────────────────────────────────────────

def _git(root: Path, *args: str, epoch: int | None = None) -> None:
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    if epoch is not None:
        iso = f"@{epoch} +0000"  # formato raw epoch de git
        env["GIT_AUTHOR_DATE"] = iso
        env["GIT_COMMITTER_DATE"] = iso
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True, env=env)


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")


def _commit_file(root: Path, rel: str, content: str, epoch: int) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(root, "add", rel)
    _git(root, "commit", "-q", "-m", f"c {rel}", epoch=epoch)


def _make_graph(note_rel: str, code_rel: str, source_relpath: str = "docs",
                extra_edges: list[dict] | None = None) -> dict:
    note_id = f"note:src1:{note_rel}"
    edges = [{"source": note_id, "target": f"code:{code_rel}", "kind": "code_ref"}]
    if extra_edges:
        edges += extra_edges
    return {
        "sources": [{"id": "src1", "relative_path": source_relpath}],
        "nodes": [
            {"id": note_id, "kind": "note", "path": note_rel, "source_id": "src1"},
            {"id": f"code:{code_rel}", "kind": "code", "path": code_rel, "source_id": ""},
        ],
        "edges": edges,
    }


# ── tests ─────────────────────────────────────────────────────────────────────

def test_code_newer_than_note_is_stale(tmp_path):
    doc_staleness._epoch_cache.clear()
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "docs/note.md", "nota", epoch=1_000_000)
    _commit_file(repo, "src/mod.py", "code", epoch=2_000_000)  # código más nuevo
    g = _make_graph("note.md", "src/mod.py")
    doc_staleness.annotate_staleness(g, str(repo))
    e = next(x for x in g["edges"] if x["kind"] == "code_ref")
    assert e["stale"] is True


def test_note_newer_than_code_not_stale(tmp_path):
    doc_staleness._epoch_cache.clear()
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "src/mod.py", "code", epoch=1_000_000)
    _commit_file(repo, "docs/note.md", "nota", epoch=2_000_000)  # nota más nueva
    g = _make_graph("note.md", "src/mod.py")
    doc_staleness.annotate_staleness(g, str(repo))
    e = next(x for x in g["edges"] if x["kind"] == "code_ref")
    assert e["stale"] is False


def test_missing_epoch_is_not_stale(tmp_path):
    doc_staleness._epoch_cache.clear()
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "docs/note.md", "nota", epoch=1_000_000)
    # el código NO existe en git → epoch None
    g = _make_graph("note.md", "src/ausente.py")
    doc_staleness.annotate_staleness(g, str(repo))
    e = next(x for x in g["edges"] if x["kind"] == "code_ref")
    assert e["stale"] is False


def test_non_code_ref_edges_have_no_stale_field(tmp_path):
    """C4 — aristas md/wikilink NO ganan la key `stale`."""
    doc_staleness._epoch_cache.clear()
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "docs/note.md", "nota", epoch=1_000_000)
    _commit_file(repo, "src/mod.py", "code", epoch=2_000_000)
    extra = [
        {"source": "note:src1:note.md", "target": "note:src1:otra.md", "kind": "md"},
        {"source": "note:src1:note.md", "target": "missing:x", "kind": "wikilink"},
    ]
    g = _make_graph("note.md", "src/mod.py", extra_edges=extra)
    doc_staleness.annotate_staleness(g, str(repo))
    for e in g["edges"]:
        if e["kind"] != "code_ref":
            assert "stale" not in e


def test_node_has_stale_reflects_edges(tmp_path):
    doc_staleness._epoch_cache.clear()
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "docs/note.md", "nota", epoch=1_000_000)
    _commit_file(repo, "src/mod.py", "code", epoch=2_000_000)
    g = _make_graph("note.md", "src/mod.py")
    doc_staleness.annotate_staleness(g, str(repo))
    note = next(n for n in g["nodes"] if n["kind"] == "note")
    assert note["has_stale"] is True


def test_degrades_on_non_git(tmp_path):
    doc_staleness._epoch_cache.clear()
    non_git = tmp_path / "plain"
    non_git.mkdir()
    g = _make_graph("note.md", "src/mod.py")
    doc_staleness.annotate_staleness(g, str(non_git))  # no lanza
    e = next(x for x in g["edges"] if x["kind"] == "code_ref")
    assert e["stale"] is False


def test_note_path_resolved_via_source_relative_path(tmp_path, monkeypatch):
    """C2 — node.path es relativo a la fuente; el epoch se consulta con relative_path + path."""
    doc_staleness._epoch_cache.clear()
    seen: list[str] = []

    def fake_epoch(repo_root, rel_path):
        seen.append(rel_path)
        return 1000

    monkeypatch.setattr(doc_staleness, "git_last_commit_epoch", fake_epoch)
    g = _make_graph("a.md", "src/mod.py", source_relpath="docs")
    doc_staleness.annotate_staleness(g, "/repo")
    assert "docs/a.md" in seen  # no "a.md" pelado


def test_lookup_cap_respected(tmp_path, monkeypatch):
    """C3 — con el tope en 1, la 2da consulta no ejecuta subprocess y queda stale=False."""
    doc_staleness._epoch_cache.clear()
    monkeypatch.setattr(doc_staleness, "_MAX_GIT_LOOKUPS", 1)
    calls = {"n": 0}

    def fake_epoch(repo_root, rel_path):
        calls["n"] += 1
        return 5000

    monkeypatch.setattr(doc_staleness, "git_last_commit_epoch", fake_epoch)
    g = _make_graph("note.md", "src/mod.py")
    doc_staleness.annotate_staleness(g, "/repo")
    e = next(x for x in g["edges"] if x["kind"] == "code_ref")
    assert calls["n"] <= 1
    assert e["stale"] is False  # falta el epoch de la nota (cap) → no stale


def test_stale_stats_counts(tmp_path):
    """[ADICIÓN ARQUITECTO] stale_stats coherente con las marcas."""
    doc_staleness._epoch_cache.clear()
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "docs/note.md", "nota", epoch=1_000_000)
    _commit_file(repo, "src/mod.py", "code", epoch=2_000_000)
    g = _make_graph("note.md", "src/mod.py")
    doc_staleness.annotate_staleness(g, str(repo))
    assert g["stale_stats"] == {"stale_edges": 1, "stale_notes": 1}
