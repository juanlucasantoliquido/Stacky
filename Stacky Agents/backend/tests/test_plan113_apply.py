"""Plan 113 F4 — apply_proposals: protege canónico, exige marcas, cap, idempotente."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from services import doc_documenter
from services.doc_documenter import DocProposal


def _prop(path, content="# X\ndato [V] (a.py:1)", action="create", marks_ok=True):
    return DocProposal(path=path, action=action, content=content,
                       marks_ok=marks_ok, sources=["a.py:1"])


def test_writes_valid_proposals(tmp_path):
    res = doc_documenter.apply_proposals([_prop("docs/modulo/nota.md")], str(tmp_path), "b")
    assert res.written == ["docs/modulo/nota.md"]
    assert (tmp_path / "docs/modulo/nota.md").read_text(encoding="utf-8").startswith("# X")


def test_rejects_docs_sistema_paths(tmp_path):
    res = doc_documenter.apply_proposals([_prop("docs/sistema/INDEX.md")], str(tmp_path), "b")
    assert res.written == []
    assert res.skipped and res.skipped[0][1] == "canonical_readonly"
    assert not (tmp_path / "docs/sistema/INDEX.md").exists()


def test_rejects_proposals_without_marks(tmp_path):
    res = doc_documenter.apply_proposals(
        [_prop("docs/x.md", content="sin marcas", marks_ok=False)], str(tmp_path), "b")
    assert res.written == []
    assert res.skipped[0][1] == "missing_confidence_marks"


def test_rejects_path_traversal(tmp_path):
    for bad in ("../escape.md", "/abs/x.md", "docs/../../x.md"):
        res = doc_documenter.apply_proposals([_prop(bad)], str(tmp_path), "b")
        assert res.written == [], bad
        assert res.skipped[0][1] == "unsafe_path", bad


def test_respects_max_files_cap(tmp_path, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_DOCS_DOCUMENTER_MAX_FILES", 2, raising=False)
    props = [_prop(f"docs/n{i}.md") for i in range(5)]
    res = doc_documenter.apply_proposals(props, str(tmp_path), "b")
    assert len(res.written) == 2
    assert any(reason == "max_files_cap" for _, reason in res.skipped)


def test_idempotent_upsert_no_duplicate(tmp_path):
    p = _prop("docs/nota.md", content="# V1\ndato [V] (a.py:1)")
    doc_documenter.apply_proposals([p], str(tmp_path), "b")
    p2 = _prop("docs/nota.md", content="# V2\ndato [V] (a.py:2)")
    res = doc_documenter.apply_proposals([p2], str(tmp_path), "b")
    assert res.written == ["docs/nota.md"]
    # un solo archivo, contenido actualizado (no duplicado)
    files = list((tmp_path / "docs").glob("nota.md"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8").startswith("# V2")
