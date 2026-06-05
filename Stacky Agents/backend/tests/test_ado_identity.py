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


# ── B1/B3: matcheo tolerante de identidad (user_matches) ──────────────────────


def test_user_matches_exact_and_casing(ident):
    assert ident.user_matches("jluca@ubimia.com", "jluca@ubimia.com") is True
    # casing / espacios
    assert ident.user_matches("  JLuca@Ubimia.com ", "jluca@ubimia.com") is True


def test_user_matches_local_part_fallback(ident):
    # email vs uniqueName sin dominio
    assert ident.user_matches("jluca", "jluca@ubimia.com") is True
    assert ident.user_matches("jluca@ubimia.com", "jluca@otra-org.com") is True


def test_user_matches_distinct_users(ident):
    assert ident.user_matches("otro@ubimia.com", "jluca@ubimia.com") is False


def test_user_matches_empty_returns_false(ident):
    assert ident.user_matches(None, "jluca@ubimia.com") is False
    assert ident.user_matches("jluca@ubimia.com", "") is False
    assert ident.user_matches("", "") is False


# ── B1/B3: resolve_me_unique_name ─────────────────────────────────────────────


def test_resolve_me_prefers_cache(ident):
    ident.save_identity("RSPACIFICO", {"unique_name": "jluca@ubimia.com", "display_name": "J"})
    # No debe tocar ADO si el cache tiene la identidad.
    assert ident.resolve_me_unique_name("RSPACIFICO") == "jluca@ubimia.com"


def test_resolve_me_returns_empty_when_unresolvable(ident, monkeypatch):
    # Sin cache y con build_ado_client fallando → "" (filtro inerte, no rompe).
    def _boom(*_a, **_k):
        raise RuntimeError("sin PAT")

    import services.project_context as pc
    monkeypatch.setattr(pc, "build_ado_client", _boom)
    assert ident.resolve_me_unique_name("SIN_CACHE") == ""
