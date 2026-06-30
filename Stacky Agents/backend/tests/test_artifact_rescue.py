"""Tests F0/F1 (plan 47) — artifact_rescue: rescate determinístico del disco."""
from __future__ import annotations

import os

import pytest

from services import artifact_rescue

# Validadores falsos deterministas (no importar api.tickets en F0).
_extract = lambda s: s  # noqa: E731
_looks_valid = lambda h: bool(h) and "RF-" in h and "<h1" in h  # noqa: E731


# ── F0 ────────────────────────────────────────────────────────────────────────

def test_no_dir_returns_none():
    assert artifact_rescue.find_rescued_html(
        None, extract=_extract, looks_valid=_looks_valid
    ) is None


def test_empty_dir_returns_none(tmp_path):
    assert artifact_rescue.find_rescued_html(
        tmp_path, extract=_extract, looks_valid=_looks_valid
    ) is None


def test_returns_valid_html(tmp_path):
    (tmp_path / "ep.html").write_text("<h1>Épica</h1> RF-01 algo", encoding="utf-8")
    out = artifact_rescue.find_rescued_html(
        tmp_path, extract=_extract, looks_valid=_looks_valid
    )
    assert out is not None and "RF-01" in out


def test_picks_most_recent_valid(tmp_path):
    old = tmp_path / "old.html"
    new = tmp_path / "new.html"
    old.write_text("<h1>Vieja</h1> RF-OLD", encoding="utf-8")
    new.write_text("<h1>Nueva</h1> RF-NEW", encoding="utf-8")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))
    out = artifact_rescue.find_rescued_html(
        tmp_path, extract=_extract, looks_valid=_looks_valid
    )
    assert "RF-NEW" in out


def test_skips_invalid_files(tmp_path):
    narr = tmp_path / "notas.txt"
    valid = tmp_path / "ep.html"
    valid.write_text("<h1>E</h1> RF-01", encoding="utf-8")
    narr.write_text("solo narración, sin estructura", encoding="utf-8")
    os.utime(valid, (1000, 1000))
    os.utime(narr, (3000, 3000))  # más nuevo pero inválido
    out = artifact_rescue.find_rescued_html(
        tmp_path, extract=_extract, looks_valid=_looks_valid
    )
    assert "RF-01" in out


def test_ignores_unreadable_or_huge(tmp_path):
    huge = tmp_path / "huge.html"
    small = tmp_path / "small.html"
    huge.write_text("<h1>H</h1> RF-H " + ("x" * 600_000), encoding="utf-8")
    small.write_text("<h1>S</h1> RF-S", encoding="utf-8")
    os.utime(huge, (3000, 3000))
    os.utime(small, (1000, 1000))
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02")
    out = artifact_rescue.find_rescued_html(
        tmp_path, extract=_extract, looks_valid=_looks_valid
    )
    assert "RF-S" in out


def test_only_candidate_suffixes(tmp_path):
    (tmp_path / "ep.json").write_text("<h1>E</h1> RF-01", encoding="utf-8")
    assert artifact_rescue.find_rescued_html(
        tmp_path, extract=_extract, looks_valid=_looks_valid
    ) is None


def test_min_mtime_excludes_stale(tmp_path):
    old = tmp_path / "old.html"
    new = tmp_path / "new.html"
    old.write_text("<h1>O</h1> RF-OLD", encoding="utf-8")
    new.write_text("<h1>N</h1> RF-NEW", encoding="utf-8")
    t0 = 5000.0
    os.utime(old, (t0 - 100, t0 - 100))
    os.utime(new, (t0 + 100, t0 + 100))
    out = artifact_rescue.find_rescued_html(
        tmp_path, extract=_extract, looks_valid=_looks_valid, min_mtime=t0
    )
    assert "RF-NEW" in out
    # min_mtime posterior a ambos → nada escrito durante la run.
    assert artifact_rescue.find_rescued_html(
        tmp_path, extract=_extract, looks_valid=_looks_valid, min_mtime=t0 + 200
    ) is None


# ── F1 ────────────────────────────────────────────────────────────────────────

def test_resolve_outputs_dir_with_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    (tmp_path / "Agentes" / "outputs").mkdir(parents=True)
    out = artifact_rescue.resolve_outputs_dir()
    assert out is not None and out == tmp_path / "Agentes" / "outputs"


def test_resolve_outputs_dir_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    assert artifact_rescue.resolve_outputs_dir() is None


def test_resolve_outputs_dir_repo_root_raises_returns_none(monkeypatch):
    import runtime_paths

    def _boom():
        raise RuntimeError("no resolvable")

    monkeypatch.setattr(runtime_paths, "repo_root", _boom)
    assert artifact_rescue.resolve_outputs_dir() is None
