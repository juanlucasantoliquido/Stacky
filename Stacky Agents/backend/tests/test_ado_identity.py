"""Tests de services.ado_identity (Requerimiento B, plan 2026-05-27)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def ident(tmp_path, monkeypatch):
    import services.ado_identity as ai

    monkeypatch.setattr(ai, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ai, "current_stacky_user", lambda: "tester")
    return ai


def test_save_and_get_identity_roundtrip(ident):
    assert ident.get_cached_identity("RSPACIFICO") is None

    entry = ident.save_identity("RSPACIFICO", {
        "unique_name": "jluca@ubimia.com",
        "display_name": "Juan L.",
        "id": "abc-123",
    })
    assert entry["ado_unique_name"] == "jluca@ubimia.com"
    assert entry["project"] == "RSPACIFICO"
    assert entry["verified_at"].endswith("Z")

    cached = ident.get_cached_identity("rspacifico")  # case-insensitive key
    assert cached is not None
    assert cached["ado_unique_name"] == "jluca@ubimia.com"
    assert cached["stacky_user"] == "tester"


def test_identity_scoped_per_project(ident):
    ident.save_identity("PROJ_A", {"unique_name": "a@x.com", "display_name": "A"})
    ident.save_identity("PROJ_B", {"unique_name": "b@x.com", "display_name": "B"})
    assert ident.get_cached_identity("PROJ_A")["ado_unique_name"] == "a@x.com"
    assert ident.get_cached_identity("PROJ_B")["ado_unique_name"] == "b@x.com"
