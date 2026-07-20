"""Plan 190 F1 — Handlers de las 2 secciones devops (export + import en 3 modos).

Verifica KPI-1 (cero secretos), KPI-2 (round-trip overwrite), KPI-3 (dry-run inocuo),
KPI-5 (checklist de re-credencialización), semántica merge/overwrite DIFF-BASED (C1),
campos derivados no aplicados, notes enmascaradas (C4) y skipped_sections con flag OFF.

Fixtures: tmp_path + monkeypatch de data_dir de server_registry/deploy_store/ct +
keyring FAKE en memoria (espeja el estilo de test_config_transfer).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

FLAG = "STACKY_CONFIG_TRANSFER_DEVOPS_ENABLED"


class FakeKeyring:
    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def set_password(self, service, key, value):
        self.store[(service, key)] = value

    def get_password(self, service, key):
        return self.store.get((service, key))

    def delete_password(self, service, key):
        if (service, key) in self.store:
            del self.store[(service, key)]
        else:
            raise KeyError((service, key))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import services.config_transfer as ct
    import services.deploy_store as deploy_store
    import services.server_registry as server_registry
    import project_manager
    from config import config as cfg

    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)

    kr = FakeKeyring()
    monkeypatch.setattr(server_registry, "data_dir", lambda: data)
    monkeypatch.setattr(server_registry, "keyring", kr)
    monkeypatch.setattr(deploy_store, "data_dir", lambda: data)
    monkeypatch.setattr(ct, "data_dir", lambda: data)
    monkeypatch.setattr(project_manager, "get_active_project", lambda: "__TESTPROJ__")
    monkeypatch.setattr(project_manager, "get_all_projects", lambda: [])
    monkeypatch.setattr(cfg, FLAG, True, raising=False)

    return {
        "data": data, "ct": ct, "sr": server_registry, "ds": deploy_store,
        "kr": kr, "cfg": cfg, "monkeypatch": monkeypatch,
    }


def _app(app_id="webapp", token="abc123def456"):
    return {
        "id": app_id,
        "name": "Web App",
        "artifact": {"kind": "folder", "path": "C:\\build\\web"},
        "targets": {
            "prod": {
                "install_path": "C:\\inetpub\\web",
                "smoke": {"kind": "http", "url": "http://localhost/health"},
                "deploy_token": token,
            }
        },
    }


def _hash_or_missing(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "MISSING"


# ── KPI-1 — cero secretos en el bundle ────────────────────────────────────────

def test_kpi1_cero_secretos_en_bundle(env):
    sr, ds, ct = env["sr"], env["ds"], env["ct"]
    sr.upsert_server("a", "a.example.com", "DOM", "user", "sin token")
    sr.set_password("a", "super-secret-pw")
    ds.upsert_app(_app(token="abc123def456"))

    bundle = ct.build_all_projects_export(sections=["devopsServers", "devopsApps"])
    raw = json.dumps(bundle, ensure_ascii=False)

    assert "super-secret-pw" not in raw
    assert "abc123def456" not in raw
    # el valor del deploy_token quedó enmascarado (la clave puede permanecer).
    assert "<omitido>" in raw


# ── KPI-2 — round-trip overwrite ──────────────────────────────────────────────

def test_kpi2_round_trip_overwrite(env):
    sr, ds, ct = env["sr"], env["ds"], env["ct"]
    sr.upsert_server("a", "a.example.com", "DOM", "user", "notas a")
    sr.set_password("a", "pw-a")
    sr.upsert_server("b", "b.example.com", "", "svc", "notas b")
    ds.upsert_app(_app("webapp"))

    bundle = ct.build_all_projects_export(sections=["devopsServers", "devopsApps"])
    exported_servers = bundle["devopsServers"]["servers"]
    exported_apps = bundle["devopsApps"]["apps"]

    # Wipe de los stores (keyring INTACTO — las credenciales no viajan).
    (env["data"] / "devops_servers.json").unlink()
    (env["data"] / "deploy_apps.json").unlink()
    assert sr.list_servers() == []
    assert ds.list_apps() == []

    ct.apply_all_projects_import(bundle, mode="overwrite")

    assert sr.list_servers() == exported_servers
    assert ds.list_apps() == exported_apps


# ── KPI-3 — dry-run inocuo ────────────────────────────────────────────────────

def test_kpi3_dry_run_inocuo(env):
    sr, ds, ct = env["sr"], env["ds"], env["ct"]
    sr.upsert_server("a", "a.example.com", "", "u", "")
    sr.upsert_server("b", "b.example.com", "", "u", "")
    ds.upsert_app(_app("app1"))
    ds.upsert_app(_app("app2"))

    bundle = ct.build_all_projects_export(sections=["devopsServers", "devopsApps"])

    # Wipe → local vacío: un import real agregaría 2 servers y 2 apps.
    servers_file = env["data"] / "devops_servers.json"
    apps_file = env["data"] / "deploy_apps.json"
    servers_file.unlink()
    apps_file.unlink()

    h_srv_before = _hash_or_missing(servers_file)
    h_app_before = _hash_or_missing(apps_file)

    res = ct.apply_all_projects_import(bundle, mode="dry-run")

    assert _hash_or_missing(servers_file) == h_srv_before
    assert _hash_or_missing(apps_file) == h_app_before
    assert res["applied"] is False
    assert res["devops"]["servers"]["add"] == 2
    assert res["devops"]["servers"]["update"] == 0
    assert res["devops"]["apps"]["add"] == 2


# ── KPI-5 — el manifest divide pending vs never_set ───────────────────────────

def test_kpi5_manifest_divide_pending_y_never_set(env):
    ct = env["ct"]
    bundle = {
        "meta": {"schemaVersion": 1, "scope": "allProjects"},
        "devopsServers": {
            "servers": [
                {"alias": "a", "host": "a.com", "domain": "", "username": "u", "notes": ""},
                {"alias": "b", "host": "b.com", "domain": "", "username": "u", "notes": ""},
            ],
            "credentials_manifest": ["a"],
        },
    }
    res = ct.apply_all_projects_import(bundle, mode="overwrite")
    assert res["devops"]["credentials_pending"] == ["a"]
    assert res["devops"]["credentials_never_set"] == ["b"]


# ── merge conserva lo local ───────────────────────────────────────────────────

def test_merge_conserva_lo_local(env):
    sr, ct = env["sr"], env["ct"]
    sr.upsert_server("extra", "extra.com", "", "u", "")
    bundle = {
        "meta": {"schemaVersion": 1, "scope": "allProjects"},
        "devopsServers": {
            "servers": [{"alias": "a", "host": "a.com", "domain": "", "username": "u", "notes": ""}],
            "credentials_manifest": [],
        },
    }
    ct.apply_all_projects_import(bundle, mode="merge")
    aliases = {s["alias"] for s in sr.list_servers()}
    assert aliases == {"extra", "a"}


# ── overwrite borra SOLO los ausentes (C1) ────────────────────────────────────

def test_overwrite_borra_solo_ausentes(env):
    sr, ct, kr = env["sr"], env["ct"], env["kr"]
    sr.upsert_server("viejo", "viejo.com", "", "u", "")
    sr.set_password("viejo", "pw-viejo")
    sr.upsert_server("a", "a.com", "", "u", "")

    bundle = {
        "meta": {"schemaVersion": 1, "scope": "allProjects"},
        "devopsServers": {
            "servers": [{"alias": "a", "host": "a.com", "domain": "", "username": "u", "notes": ""}],
            "credentials_manifest": [],
        },
    }
    ct.apply_all_projects_import(bundle, mode="overwrite")

    assert sr.get_server("viejo") is None
    assert sr.has_password("viejo") is False           # credencial borrada (semántica 91)
    assert ("stacky-devops", "viejo") not in kr.store
    assert sr.get_server("a") is not None


# ── overwrite CONSERVA el password del alias reimportado (C1 — bug de la v1) ──

def test_overwrite_conserva_password_de_alias_reimportado(env):
    sr, ct, kr = env["sr"], env["ct"], env["kr"]
    sr.upsert_server("a", "a.com", "", "u", "")
    sr.set_password("a", "pw-a")

    bundle = {
        "meta": {"schemaVersion": 1, "scope": "allProjects"},
        "devopsServers": {
            "servers": [{"alias": "a", "host": "a.com", "domain": "", "username": "u", "notes": ""}],
            "credentials_manifest": ["a"],
        },
    }
    ct.apply_all_projects_import(bundle, mode="overwrite")

    assert sr.has_password("a") is True
    assert kr.store.get(("stacky-devops", "a")) == "pw-a"


# ── flag OFF → skipped_sections + stores intactos ─────────────────────────────

def test_flag_off_skipped_sections(env):
    sr, ds, ct, cfg = env["sr"], env["ds"], env["ct"], env["cfg"]
    # Bundle construido con flag ON.
    sr.upsert_server("a", "a.com", "", "u", "")
    ds.upsert_app(_app("app1"))
    bundle = ct.build_all_projects_export(sections=["devopsServers", "devopsApps"])
    # Wipe y flag OFF: importar NO debe tocar los stores.
    (env["data"] / "devops_servers.json").unlink()
    (env["data"] / "deploy_apps.json").unlink()
    env["monkeypatch"].setattr(cfg, FLAG, False, raising=False)

    res = ct.apply_all_projects_import(bundle, mode="overwrite")

    assert sr.list_servers() == []
    assert ds.list_apps() == []
    assert set(res["skipped_sections"]) == {"devopsServers", "devopsApps"}
    assert "devops" not in res


# ── campos derivados NO se aplican ────────────────────────────────────────────

def test_campos_derivados_no_se_aplican(env):
    sr, ct = env["sr"], env["ct"]
    bundle = {
        "meta": {"schemaVersion": 1, "scope": "allProjects"},
        "devopsServers": {
            "servers": [{
                "alias": "c", "host": "c.com", "domain": "", "username": "u", "notes": "",
                "has_password": True,                       # derivado — NO debe copiarse
                "last_connected_at": "2020-01-01T00:00:00",  # derivado — NO debe copiarse
            }],
            "credentials_manifest": [],
        },
    }
    ct.apply_all_projects_import(bundle, mode="overwrite")

    stored = sr.get_server("c")
    assert stored is not None
    assert "last_connected_at" not in stored          # campo derivado no aplicado
    assert sr.has_password("c") is False              # refleja el keyring local real


# ── notes enmascaradas (C4) ───────────────────────────────────────────────────

def test_notes_enmascaradas(env):
    sr, ct = env["sr"], env["ct"]
    token = "glpat-" + "x" * 12  # literal PARTIDO (gotcha push-protection)
    sr.upsert_server("a", "a.com", "", "u", f"token {token} en notas")

    bundle = ct.build_all_projects_export(sections=["devopsServers", "devopsApps"])
    raw = json.dumps(bundle, ensure_ascii=False)

    assert token not in raw
    assert "<posible-secreto-omitido>" in raw
