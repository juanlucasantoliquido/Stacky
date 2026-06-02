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


# ── Templates embebidos vs JSON (deploy congelado) ────────────────────────────

def test_embedded_templates_match_json(env):
    """Los templates embebidos en client_profile_default_templates.py deben ser
    idénticos a los JSON de client_profile_defaults/. El embebido es el que se
    usa en el deploy congelado (PyInstaller no empaqueta los JSON); este test
    evita que diverjan si alguien edita uno y olvida el otro."""
    from services.client_profile_default_templates import DEFAULT_TEMPLATES

    cp = env["cp"]
    for tracker, embedded in DEFAULT_TEMPLATES.items():
        json_path = cp._DEFAULTS_DIR / f"{tracker}.json"
        assert json_path.exists(), f"Falta el JSON espejo de {tracker}"
        on_disk = json.loads(json_path.read_text(encoding="utf-8"))
        assert embedded == on_disk, (
            f"El template embebido '{tracker}' difiere del JSON. "
            f"Sincronizá services/client_profile_default_templates.py con "
            f"services/client_profile_defaults/{tracker}.json."
        )


def test_default_template_works_without_json_files(env, tmp_path, monkeypatch):
    """Simula el deploy congelado: los JSON no están en disco. El default DEBE
    seguir completo (vía el fallback embebido), no `{"schema_version": 1}`."""
    cp = env["cp"]
    missing_dir = tmp_path / "no_such_defaults"
    monkeypatch.setattr(cp, "_DEFAULTS_DIR", missing_dir)

    template = cp.get_default_client_profile("azure_devops")
    assert "code_layout" in template
    assert template["code_layout"]["online_path"] == "trunk/OnLine"
    assert "language" in template
    assert "tracker_state_machine" in template
    # jira sigue resolviendo a su template (no a ADO) desde el embebido.
    jira = cp.get_default_client_profile("jira")
    assert jira["database"]["type"] == "postgres"


def test_complete_without_json_files_fills_required(env, tmp_path, monkeypatch):
    """Sin JSON en disco, completar un perfil vacío sigue rellenando las
    secciones requeridas (esto es lo que el editor persiste al Guardar)."""
    cp = env["cp"]
    monkeypatch.setattr(cp, "_DEFAULTS_DIR", tmp_path / "no_such_defaults")
    completed = cp.complete_client_profile({"schema_version": 1}, "azure_devops")
    assert "code_layout" in completed
    assert "language" in completed
    assert "tracker_state_machine" in completed
    # Validar el completado no debe disparar warnings de secciones requeridas.
    res = cp.validate_client_profile(completed)
    assert res.ok, res.errors
    assert not any("code_layout" in w for w in res.warnings)
    assert not any("language" in w for w in res.warnings)
    assert not any("tracker_state_machine" in w for w in res.warnings)


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


# ── get_project_tracker_type ──────────────────────────────────────────────────

def test_tracker_type_reads_issue_tracker(env):
    cp = env["cp"]
    _write_cfg(env, "DEMO", {"name": "DEMO", "issue_tracker": {"type": "Jira"}})
    assert cp.get_project_tracker_type("DEMO") == "jira"


def test_tracker_type_fallback_when_missing(env):
    cp = env["cp"]
    _write_cfg(env, "DEMO", {"name": "DEMO"})  # sin issue_tracker
    assert cp.get_project_tracker_type("DEMO") == "azure_devops"


def test_tracker_type_fallback_when_no_config(env):
    cp = env["cp"]
    # Proyecto inexistente → fallback, sin lanzar.
    assert cp.get_project_tracker_type("GHOST") == "azure_devops"


# ── load_effective_client_profile (siempre devuelve un dict) ──────────────────

def test_effective_returns_configured_as_is(env):
    cp = env["cp"]
    configured = {
        "schema_version": 1,
        "code_layout": {"online_path": "trunk/Custom"},
        "language": {"primary": "csharp"},
        "tracker_state_machine": {"developer": {"next_state_ok": "Done"}},
    }
    _write_cfg(env, "DEMO", {"name": "DEMO", "client_profile": configured})
    eff = cp.load_effective_client_profile("DEMO")
    assert eff == configured  # tal cual, sin merge con defaults


def test_effective_falls_back_to_tracker_default(env):
    cp = env["cp"]
    _write_cfg(env, "DEMO", {"name": "DEMO", "issue_tracker": {"type": "jira"}})
    eff = cp.load_effective_client_profile("DEMO")
    # Sin perfil configurado → default del tracker (jira → postgres).
    assert eff["database"]["type"] == "postgres"
    assert eff["schema_version"] == cp.SCHEMA_VERSION


def test_effective_falls_back_to_ado_when_no_config(env):
    cp = env["cp"]
    eff = cp.load_effective_client_profile("GHOST")
    assert eff["language"]["primary"] == "csharp"


# ── seed-on-create en initialize_project (idempotente) ────────────────────────

def test_initialize_project_seeds_client_profile(env):
    import project_manager

    cfg = project_manager.initialize_project(
        name="SEEDED",
        issue_tracker={"type": "jira"},
    )
    assert isinstance(cfg.get("client_profile"), dict)
    # Default del tracker elegido.
    assert cfg["client_profile"]["database"]["type"] == "postgres"
    # Persistido en disco.
    on_disk = json.loads(
        (env["projects_dir"] / "SEEDED" / "config.json").read_text(encoding="utf-8")
    )
    assert on_disk["client_profile"]["database"]["type"] == "postgres"


def test_initialize_project_preserves_existing_profile(env):
    import project_manager

    project_manager.initialize_project(name="SEEDED", issue_tracker={"type": "azure_devops"})
    # El operador edita su perfil.
    cp = env["cp"]
    custom = cp.get_default_client_profile("azure_devops")
    custom["code_layout"]["online_path"] = "trunk/MiRutaCustom"
    cp.save_client_profile("SEEDED", custom)

    # Una actualización (PATCH pasa por initialize_project) NO debe pisarlo.
    project_manager.initialize_project(name="SEEDED", issue_tracker={"type": "azure_devops"})
    reloaded = cp.load_client_profile("SEEDED")
    assert reloaded["code_layout"]["online_path"] == "trunk/MiRutaCustom"


# ── complete_client_profile (plan 17) ─────────────────────────────────────────

def test_complete_fills_layout_from_ado_default(env):
    cp = env["cp"]
    # Perfil vacío → todas las secciones no-BD se rellenan con el template ADO.
    completed = cp.complete_client_profile(None, "azure_devops")
    assert completed["code_layout"]["online_path"] == "trunk/OnLine"
    assert completed["docs_indexes"]["technical_master"] != ""
    assert "language" in completed
    assert "tracker_state_machine" in completed


def test_complete_does_not_inject_database(env):
    cp = env["cp"]
    # Sin database en el perfil de entrada → no debe aparecer en el resultado.
    completed = cp.complete_client_profile({}, "azure_devops")
    assert "database" not in completed


def test_complete_preserves_existing_database(env):
    cp = env["cp"]
    profile = {"schema_version": 1, "database": {"server": "mi-servidor"}}
    completed = cp.complete_client_profile(profile, "azure_devops")
    # La sección database que vino en el perfil se conserva tal cual.
    assert completed["database"]["server"] == "mi-servidor"
    # No se inyectan otros campos de database del template.
    assert "type" not in completed["database"]


def test_complete_profile_wins_over_default(env):
    cp = env["cp"]
    profile = {
        "schema_version": 1,
        "code_layout": {"online_path": "src/custom"},
    }
    completed = cp.complete_client_profile(profile, "azure_devops")
    # El valor del operador gana.
    assert completed["code_layout"]["online_path"] == "src/custom"
    # El resto del layout se rellena con el default.
    assert completed["code_layout"]["batch_path"] == "trunk/Batch"


def test_complete_is_idempotent(env):
    cp = env["cp"]
    first = cp.complete_client_profile(None, "azure_devops")
    second = cp.complete_client_profile(first, "azure_devops")
    assert first == second


# ── resolve_layout_paths (plan 17) ────────────────────────────────────────────

def test_resolve_marks_nonexistent_as_false(env, tmp_path):
    cp = env["cp"]
    profile = {
        "code_layout": {"online_path": "trunk/OnLine"},
        "docs_indexes": {},
    }
    results = cp.resolve_layout_paths(profile, str(tmp_path))
    assert len(results) == 1
    assert results[0]["rel"] == "trunk/OnLine"
    assert results[0]["exists"] is False


def test_resolve_marks_existing_as_true(env, tmp_path):
    cp = env["cp"]
    online = tmp_path / "trunk" / "OnLine"
    online.mkdir(parents=True)
    profile = {"code_layout": {"online_path": "trunk/OnLine"}}
    results = cp.resolve_layout_paths(profile, str(tmp_path))
    assert results[0]["exists"] is True


def test_resolve_skips_empty_paths(env, tmp_path):
    cp = env["cp"]
    profile = {"code_layout": {"online_path": ""}}
    results = cp.resolve_layout_paths(profile, str(tmp_path))
    assert results == []


def test_resolve_abs_uses_forward_slashes(env, tmp_path):
    cp = env["cp"]
    profile = {"code_layout": {"online_path": "trunk/OnLine"}}
    results = cp.resolve_layout_paths(profile, str(tmp_path))
    assert "\\" not in results[0]["abs"]


def test_resolve_empty_workspace_root_returns_empty_abs(env):
    cp = env["cp"]
    profile = {"code_layout": {"online_path": "trunk/OnLine"}}
    results = cp.resolve_layout_paths(profile, "")
    assert results[0]["abs"] == ""
    assert results[0]["exists"] is False
