"""Tests del paso `_inject_client_profile_block` (plan 16, Fase 2)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import services.client_profile as cp
    import services.context_enrichment as ce

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects_dir)

    return {"projects_dir": projects_dir, "ce": ce, "cp": cp}


def _write_profile(env, name: str, profile: dict) -> None:
    pdir = env["projects_dir"] / name.upper()
    pdir.mkdir(parents=True, exist_ok=True)
    cfg = {"name": name.upper(), "client_profile": profile}
    (pdir / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


_PROFILE = {
    "schema_version": 1,
    "code_layout": {"online_path": "trunk/OnLine"},
    "language": {"primary": "csharp"},
    "terminology": {"client_label": "Demo Corp", "product_name": "DemoApp"},
    "tracker_state_machine": {
        "functional": {"next_state_ok": "Technical review"},
        "technical": {"next_state_ok": "To Do"},
        "developer": {"next_state_ok": "Reviewed by Dev"},
    },
}


def test_injects_when_profile_present(env, monkeypatch):
    monkeypatch.delenv("STACKY_INJECT_CLIENT_PROFILE", raising=False)
    _write_profile(env, "DEMO", _PROFILE)
    ce = env["ce"]
    msgs = []
    out = ce._inject_client_profile_block([], "DEMO", lambda lvl, msg: msgs.append((lvl, msg)))
    assert len(out) == 1
    assert out[0]["id"] == "client-profile"
    assert "Demo Corp" in out[0]["title"]
    assert "online_path" in out[0]["content"]
    assert any("client-profile inyectado" in m for _, m in msgs)


def test_skipped_when_no_project_name(env, monkeypatch):
    monkeypatch.delenv("STACKY_INJECT_CLIENT_PROFILE", raising=False)
    _write_profile(env, "DEMO", _PROFILE)
    out = env["ce"]._inject_client_profile_block([], None, lambda *a: None)
    assert out == []


def test_skipped_when_profile_missing(env, monkeypatch):
    monkeypatch.delenv("STACKY_INJECT_CLIENT_PROFILE", raising=False)
    # No profile written.
    out = env["ce"]._inject_client_profile_block([], "DEMO", lambda *a: None)
    assert out == []


def test_skipped_when_flag_off(env, monkeypatch):
    monkeypatch.setenv("STACKY_INJECT_CLIENT_PROFILE", "false")
    _write_profile(env, "DEMO", _PROFILE)
    out = env["ce"]._inject_client_profile_block([], "DEMO", lambda *a: None)
    assert out == []


@pytest.mark.parametrize("flag", ["0", "off", "false", "FALSE", "Off"])
def test_flag_variants(env, monkeypatch, flag):
    monkeypatch.setenv("STACKY_INJECT_CLIENT_PROFILE", flag)
    _write_profile(env, "DEMO", _PROFILE)
    out = env["ce"]._inject_client_profile_block([], "DEMO", lambda *a: None)
    assert out == []


def test_does_not_duplicate_existing_block(env, monkeypatch):
    monkeypatch.delenv("STACKY_INJECT_CLIENT_PROFILE", raising=False)
    _write_profile(env, "DEMO", _PROFILE)
    existing = [{"id": "client-profile", "title": "old", "content": "stale"}]
    out = env["ce"]._inject_client_profile_block(existing, "DEMO", lambda *a: None)
    # Mantiene el existente, no añade otro.
    assert len(out) == 1
    assert out[0]["content"] == "stale"


def test_content_is_deterministic_json(env, monkeypatch):
    monkeypatch.delenv("STACKY_INJECT_CLIENT_PROFILE", raising=False)
    _write_profile(env, "DEMO", _PROFILE)
    ce = env["ce"]
    a = ce._inject_client_profile_block([], "DEMO", lambda *a: None)
    b = ce._inject_client_profile_block([], "DEMO", lambda *a: None)
    assert a == b
    # Es JSON parseable.
    parsed = json.loads(a[0]["content"])
    assert parsed["schema_version"] == 1
