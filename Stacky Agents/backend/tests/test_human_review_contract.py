"""Plan 47 F0 — Contrato del veredicto humano (módulo puro)."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _b(**kw):
    from services.human_review import build_human_review
    return build_human_review(**kw)


def test_build_valid_approved():
    r = _b(verdict="approved", note=None, reviewed_by="op@x")
    assert r["verdict"] == "approved"
    assert r["note"] is None
    datetime.fromisoformat(r["reviewed_at"])  # parseable


def test_build_approved_with_notes_requires_note():
    with pytest.raises(ValueError):
        _b(verdict="approved_with_notes", note="", reviewed_by="op")


def test_build_rejected_with_note_ok():
    r = _b(verdict="rejected", note="no cumple criterio", reviewed_by="op")
    assert r["note"] == "no cumple criterio"


def test_invalid_verdict_raises():
    with pytest.raises(ValueError):
        _b(verdict="foo", note=None, reviewed_by="op")


def test_note_too_long_raises():
    with pytest.raises(ValueError):
        _b(verdict="rejected", note="x" * 2001, reviewed_by="op")


def test_note_whitespace_trimmed():
    r = _b(verdict="rejected", note="  ok  ", reviewed_by="op")
    assert r["note"] == "ok"


def test_normalize_legacy_discarded():
    r = _b(verdict="discarded", note=None, reviewed_by="op")
    assert r["verdict"] == "rejected"
