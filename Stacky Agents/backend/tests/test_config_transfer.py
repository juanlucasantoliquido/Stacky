"""
Tests de services.config_transfer (Requerimiento A, plan 2026-05-27).

Cubre: export con checksum + secretsRef sin secretos, validación de schema y
checksum, dry-run con diff, import idempotente (merge), y portabilidad entre
proyectos.
"""
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


def _write_project(projects_dir: Path, name: str, cfg: dict, *, pat: str | None = None) -> None:
    pdir = projects_dir / name.upper()
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    if pat is not None:
        auth = pdir / "auth"
        auth.mkdir(parents=True, exist_ok=True)
        # Simula el formato cifrado real (valor opaco, nunca el PAT en claro).
        (auth / "ado_auth.json").write_text(
            json.dumps({"pat": "AQAAANCMnd8ENCRYPTEDBLOB==", "pat_format": "dpapi_preencoded"}),
            encoding="utf-8",
        )


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import project_manager
    import services.config_transfer as ct

    projects_dir = tmp_path / "projects"
    data_dir = tmp_path / "data"
    projects_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(ct, "projects_dir", lambda: projects_dir)
    monkeypatch.setattr(ct, "data_dir", lambda: data_dir)

    return {"projects_dir": projects_dir, "data_dir": data_dir, "ct": ct}


SOURCE_CFG = {
    "name": "SOURCE",
    "display_name": "Source Project",
    "workspace_root": "C:/repos/source/trunk",
    "docs_paths": {"technical": "C:/docs/tech", "functional": ""},
    "issue_tracker": {
        "type": "azure_devops",
        "organization": "UbimiaPacifico",
        "project": "Strategist_Pacifico",
        "auth_file": "auth/ado_auth.json",
    },
    "pinned_agents": ["business.agent.md", "qa.agent.md"],
    "agent_workflow_configs": {
        "qa.agent.md": {"allowed_states": ["Active"], "transition_state": "Resolved"}
    },
}


def test_export_includes_checksum_and_no_secrets(env):
    ct = env["ct"]
    _write_project(env["projects_dir"], "SOURCE", SOURCE_CFG, pat="supersecret-pat")

    bundle = ct.build_export("SOURCE")
    meta = bundle["meta"]

    assert meta["schemaVersion"] == ct.CURRENT_SCHEMA_VERSION
    assert meta["checksum"].startswith("sha256:")
    assert meta["projectId"] == "SOURCE"

    # secretsRef informa qué credenciales existían, sin valores.
    refs = bundle["secretsRef"]
    assert any(r["auth_file"] == "auth/ado_auth.json" and r["fields"] == ["pat"] for r in refs)

    # El PAT (ni cifrado ni en claro) jamás aparece en el JSON serializado.
    raw = json.dumps(bundle)
    assert "supersecret-pat" not in raw
    assert "ENCRYPTEDBLOB" not in raw
    assert "pat" not in bundle["integrations"]["issue_tracker"]


def test_validate_detects_tamper(env):
    ct = env["ct"]
    _write_project(env["projects_dir"], "SOURCE", SOURCE_CFG, pat="x")
    bundle = ct.build_export("SOURCE")

    ok = ct.validate_import(bundle)
    assert ok.ok and ok.checksum_ok

    # Manipular un valor invalida el checksum.
    bundle["settings"]["display_name"] = "Hacked"
    bad = ct.validate_import(bundle)
    assert not bad.ok
    assert not bad.checksum_ok
    assert any("hecksum" in e or "checksum" in e.lower() for e in bad.errors)


def test_reject_newer_schema(env):
    ct = env["ct"]
    _write_project(env["projects_dir"], "SOURCE", SOURCE_CFG)
    bundle = ct.build_export("SOURCE")
    bundle["meta"]["schemaVersion"] = ct.CURRENT_SCHEMA_VERSION + 5
    bundle["meta"]["checksum"] = ct.compute_checksum(bundle)
    res = ct.validate_import(bundle)
    assert not res.ok
    assert any("nuevo" in e for e in res.errors)


def test_dry_run_then_merge_is_idempotent(env):
    ct = env["ct"]
    _write_project(env["projects_dir"], "SOURCE", SOURCE_CFG, pat="x")
    # Proyecto destino vacío (sólo tracker mínimo).
    _write_project(env["projects_dir"], "TARGET", {
        "name": "TARGET",
        "display_name": "TARGET",
        "workspace_root": "",
        "docs_paths": {"technical": "", "functional": ""},
        "issue_tracker": {"type": "azure_devops", "auth_file": "auth/ado_auth.json"},
    })

    bundle = ct.build_export("SOURCE")

    # dry-run: hay cambios y NO persiste.
    dry = ct.apply_import("TARGET", bundle, mode="dry-run")
    assert dry["applied"] is False
    assert len(dry["changes"]) > 0
    # El destino no tiene credenciales → secrets_required avisa.
    assert any(s["auth_file"] == "auth/ado_auth.json" for s in dry["secrets_required"])

    # merge real: aplica.
    applied = ct.apply_import("TARGET", bundle, mode="merge")
    assert applied["applied"] is True
    assert applied.get("idempotent") is not True

    # Verifica persistencia.
    target_cfg = json.loads(
        (env["projects_dir"] / "TARGET" / "config.json").read_text(encoding="utf-8")
    )
    assert target_cfg["display_name"] == "Source Project"
    assert target_cfg["issue_tracker"]["organization"] == "UbimiaPacifico"
    assert "qa.agent.md" in target_cfg["agent_workflow_configs"]
    assert set(target_cfg["pinned_agents"]) == {"business.agent.md", "qa.agent.md"}

    # Segunda aplicación = idempotente (sin cambios).
    again = ct.apply_import("TARGET", bundle, mode="merge")
    assert again["applied"] is True
    assert again.get("idempotent") is True
    assert again["changes"] == []


def test_audit_events_recorded(env):
    ct = env["ct"]
    ct.record_event(action="export", project="SOURCE", result="ok", schema_version=1)
    ct.record_event(action="import", project="SOURCE", result="applied", mode="merge")
    events = ct.list_events(project="SOURCE")
    assert len(events) == 2
    # Más reciente primero.
    assert events[0]["action"] == "import"
    assert events[1]["action"] == "export"


def test_selective_export(env):
    ct = env["ct"]
    _write_project(env["projects_dir"], "SOURCE", SOURCE_CFG)
    bundle = ct.build_export("SOURCE", sections=["settings"])
    assert "settings" in bundle
    assert "integrations" not in bundle
    assert "workflows" not in bundle
    assert bundle["meta"]["sections"] == ["settings"]


# ── Plan 16 — clientProfile en export/import ──────────────────────────────────

_PROFILE_CLEAN = {
    "schema_version": 1,
    "code_layout": {"online_path": "trunk/OnLine"},
    "language": {"primary": "csharp"},
    "database": {
        "type": "sqlserver",
        "server": "demo",
        "readonly_user_hint": "DEMOREAD",
        "readonly_auth_ref": "auth/db_readonly.json",
    },
    "tracker_state_machine": {
        "functional": {"next_state_ok": "Technical review"},
        "technical": {"next_state_ok": "To Do"},
        "developer": {"next_state_ok": "Reviewed by Dev"},
    },
}


def test_client_profile_section_round_trip(env):
    ct = env["ct"]
    src_cfg = dict(SOURCE_CFG)
    src_cfg["client_profile"] = _PROFILE_CLEAN
    _write_project(env["projects_dir"], "SOURCE", src_cfg, pat="x")

    bundle = ct.build_export("SOURCE")
    assert "clientProfile" in bundle
    assert bundle["clientProfile"]["profile"]["language"]["primary"] == "csharp"

    # Destino sin client_profile.
    _write_project(env["projects_dir"], "TARGET", {
        "name": "TARGET",
        "display_name": "TARGET",
        "workspace_root": "",
        "docs_paths": {"technical": "", "functional": ""},
        "issue_tracker": {"type": "azure_devops", "auth_file": "auth/ado_auth.json"},
    })

    applied = ct.apply_import("TARGET", bundle, mode="merge")
    assert applied["applied"] is True
    target_cfg = json.loads(
        (env["projects_dir"] / "TARGET" / "config.json").read_text(encoding="utf-8")
    )
    assert target_cfg["client_profile"]["language"]["primary"] == "csharp"

    # Idempotente: re-aplicar no añade cambios.
    again = ct.apply_import("TARGET", bundle, mode="merge")
    assert again["applied"] is True
    assert again.get("idempotent") is True


def test_export_rejects_secret_in_client_profile(env):
    ct = env["ct"]
    src_cfg = dict(SOURCE_CFG)
    src_cfg["client_profile"] = {
        "schema_version": 1,
        "extensions": {"sentry": {"api_key": "leak"}},
    }
    _write_project(env["projects_dir"], "SOURCE", src_cfg, pat="x")
    with pytest.raises(ct.ConfigTransferError):
        ct.build_export("SOURCE")


def test_import_rejects_secret_in_incoming_profile(env):
    ct = env["ct"]
    _write_project(env["projects_dir"], "SOURCE", SOURCE_CFG, pat="x")
    _write_project(env["projects_dir"], "TARGET", {
        "name": "TARGET",
        "display_name": "TARGET",
        "workspace_root": "",
        "docs_paths": {"technical": "", "functional": ""},
        "issue_tracker": {"type": "azure_devops", "auth_file": "auth/ado_auth.json"},
    })
    # Forzar un bundle con secret y recomputar checksum: validate_import lo deja
    # pasar (no es su responsabilidad), pero apply_import debe rechazar.
    bundle = ct.build_export("SOURCE")
    bundle["clientProfile"] = {"profile": {"schema_version": 1, "database": {"password": "x"}}}
    bundle["meta"]["checksum"] = ct.compute_checksum(bundle)
    with pytest.raises(ct.ConfigTransferError):
        ct.apply_import("TARGET", bundle, mode="merge")


def test_all_projects_export_import_creates_missing_projects_from_scratch(env, monkeypatch):
    ct = env["ct"]
    import project_manager

    target_projects_dir = env["projects_dir"]
    target_data_dir = env["data_dir"]
    _write_project(target_projects_dir, "SOURCE", SOURCE_CFG, pat="x")
    second_cfg = {
        **SOURCE_CFG,
        "name": "SECOND",
        "display_name": "Second Project",
        "workspace_root": "C:/repos/second/trunk",
        "issue_tracker": {
            "type": "jira",
            "url": "https://jira.example.test",
            "project_key": "SEC",
            "auth_file": "auth/jira_auth.json",
        },
        "pinned_agents": ["developer.agent.md"],
    }
    _write_project(target_projects_dir, "SECOND", second_cfg)
    project_manager.set_active_project("SECOND")
    (target_data_dir / "preferences.json").write_text(
        json.dumps({"theme": "dark", "pinned": ["qa.agent.md"]}),
        encoding="utf-8",
    )

    bundle = ct.build_all_projects_export()
    assert bundle["meta"]["scope"] == "allProjects"
    assert bundle["meta"]["projectCount"] == 2
    assert bundle["meta"]["activeProject"] == "SECOND"
    assert len(bundle["projects"]) == 2
    assert "uiPreferences" in bundle

    fresh_projects_dir = env["projects_dir"] / "fresh"
    fresh_data_dir = env["data_dir"] / "fresh"
    fresh_projects_dir.mkdir()
    fresh_data_dir.mkdir()
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", fresh_projects_dir)
    monkeypatch.setattr(project_manager, "ACTIVE_FILE", fresh_data_dir / "active_project.json")
    monkeypatch.setattr(ct, "projects_dir", lambda: fresh_projects_dir)
    monkeypatch.setattr(ct, "data_dir", lambda: fresh_data_dir)

    dry = ct.apply_all_projects_import(bundle, mode="dry-run")
    assert dry["applied"] is False
    assert {p["project"] for p in dry["projects"]} == {"SOURCE", "SECOND"}
    assert any(c["section"] == "projects" and c["action"] == "add" for c in dry["changes"])
    assert not (fresh_projects_dir / "SOURCE" / "config.json").exists()

    applied = ct.apply_all_projects_import(bundle, mode="merge")
    assert applied["applied"] is True
    assert (fresh_projects_dir / "SOURCE" / "config.json").exists()
    assert (fresh_projects_dir / "SECOND" / "config.json").exists()
    restored = json.loads((fresh_projects_dir / "SECOND" / "config.json").read_text(encoding="utf-8"))
    assert restored["issue_tracker"]["type"] == "jira"
    assert restored["pinned_agents"] == ["developer.agent.md"]
    assert json.loads((fresh_data_dir / "preferences.json").read_text(encoding="utf-8"))["theme"] == "dark"
    assert project_manager.get_active_project() == "SECOND"

    again = ct.apply_all_projects_import(bundle, mode="merge")
    assert again["idempotent"] is True
    assert again["changes"] == []
