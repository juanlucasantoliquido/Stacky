"""Tests de services.client_profile (plan 16, Fase 1)."""
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
    import project_manager

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cp, "projects_dir", lambda: projects_dir)
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    return {"projects_dir": projects_dir, "cp": cp}


def _write_cfg(env, name: str, cfg: dict) -> None:
    pdir = env["projects_dir"] / name.upper()
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def test_get_default_template_ado(env):
    cp = env["cp"]
    template = cp.get_default_client_profile("azure_devops")
    assert template["schema_version"] == cp.SCHEMA_VERSION
    assert "code_layout" in template
    assert "language" in template
    assert "tracker_state_machine" in template
    assert template["tracker_state_machine"]["technical"]["next_state_ok"] == "To Do"


def test_get_default_template_jira(env):
    cp = env["cp"]
    template = cp.get_default_client_profile("jira")
    assert template["tracker_state_machine"]["developer"]["next_state_ok"] == "Code Review"
    assert template["database"]["type"] == "postgres"


def test_get_default_template_mantis(env):
    cp = env["cp"]
    template = cp.get_default_client_profile("mantis")
    assert template["tracker_state_machine"]["developer"]["next_state_ok"] == "resolved"
    assert template["database"]["type"] == "mysql"


def test_get_default_unknown_tracker_falls_back_to_ado(env):
    cp = env["cp"]
    template = cp.get_default_client_profile("does_not_exist")
    # ADO es el fallback más rico.
    assert template["language"]["primary"] == "csharp"


def test_validate_accepts_minimal_profile(env):
    cp = env["cp"]
    minimal = {
        "schema_version": 1,
        "code_layout": {"online_path": "trunk/OnLine"},
        "language": {"primary": "csharp"},
        "tracker_state_machine": {
            "functional": {"next_state_ok": "Technical review"},
            "technical": {"next_state_ok": "To Do"},
            "developer": {"next_state_ok": "Reviewed by Dev"},
        },
    }
    res = cp.validate_client_profile(minimal)
    assert res.ok, res.errors
    assert res.normalized["schema_version"] == 1


def test_validate_rejects_secret_keys(env):
    cp = env["cp"]
    with_secret = {
        "schema_version": 1,
        "database": {"password": "supersecret"},
    }
    res = cp.validate_client_profile(with_secret)
    assert not res.ok
    assert any("password" in e for e in res.errors)


def test_validate_rejects_pat_in_extensions(env):
    cp = env["cp"]
    with_secret = {
        "schema_version": 1,
        "extensions": {"sentry": {"api_key": "x"}},
    }
    res = cp.validate_client_profile(with_secret)
    assert not res.ok
    assert any("api_key" in e for e in res.errors)


def test_validate_warns_missing_required(env):
    cp = env["cp"]
    res = cp.validate_client_profile({"schema_version": 1})
    # Sin las secciones requeridas, validate() debe emitir warnings (no errors,
    # porque el caso "sin profile" es válido — el agente cae al fallback).
    assert res.ok, res.errors
    assert any("code_layout" in w for w in res.warnings)
    assert any("language" in w for w in res.warnings)
    assert any("tracker_state_machine" in w for w in res.warnings)


def test_validate_rejects_future_schema(env):
    cp = env["cp"]
    res = cp.validate_client_profile({"schema_version": 9999})
    assert not res.ok
    assert any("schema_version" in e for e in res.errors)


def test_validate_rejects_wrong_types(env):
    cp = env["cp"]
    res = cp.validate_client_profile({
        "schema_version": 1,
        "code_layout": "not a dict",
    })
    assert not res.ok
    assert any("code_layout" in e for e in res.errors)


def test_load_returns_none_when_missing(env):
    cp = env["cp"]
    _write_cfg(env, "DEMO", {"name": "DEMO"})
    assert cp.load_client_profile("DEMO") is None


def test_save_then_load_roundtrip(env):
    cp = env["cp"]
    _write_cfg(env, "DEMO", {"name": "DEMO"})
    profile = cp.get_default_client_profile("azure_devops")
    saved = cp.save_client_profile("DEMO", profile)
    loaded = cp.load_client_profile("DEMO")
    assert loaded == saved
    assert loaded["schema_version"] == 1


def test_save_rejects_secrets(env):
    cp = env["cp"]
    _write_cfg(env, "DEMO", {"name": "DEMO"})
    with pytest.raises(cp.ClientProfileError):
        cp.save_client_profile("DEMO", {"schema_version": 1, "database": {"password": "x"}})


def test_save_rejects_unknown_project(env):
    cp = env["cp"]
    with pytest.raises(cp.ClientProfileError):
        cp.save_client_profile("GHOST", cp.get_default_client_profile("azure_devops"))


def test_clear_removes_section(env):
    cp = env["cp"]
    _write_cfg(env, "DEMO", {"name": "DEMO"})
    cp.save_client_profile("DEMO", cp.get_default_client_profile("azure_devops"))
    assert cp.load_client_profile("DEMO") is not None
    assert cp.clear_client_profile("DEMO") is True
    assert cp.load_client_profile("DEMO") is None
    # Idempotente.
    assert cp.clear_client_profile("DEMO") is False


def test_merge_with_defaults_completes_missing(env):
    cp = env["cp"]
    partial = {
        "schema_version": 1,
        "code_layout": {"online_path": "src/web"},
        "language": {"primary": "csharp"},
    }
    merged = cp.merge_with_defaults(partial, "azure_devops")
    assert merged["code_layout"]["online_path"] == "src/web"
    # Defaults se preservan donde el operador no llenó.
    assert merged["build"]["tool"] == "msbuild"
    assert merged["conventions"]["string_sanitizer"] == "cFormat.StToBD()"


def test_has_client_profile_returns_bool(env):
    cp = env["cp"]
    _write_cfg(env, "DEMO", {"name": "DEMO"})
    assert cp.has_client_profile("DEMO") is False
    cp.save_client_profile("DEMO", cp.get_default_client_profile("azure_devops"))
    assert cp.has_client_profile("DEMO") is True
