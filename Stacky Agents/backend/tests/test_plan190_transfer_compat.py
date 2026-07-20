"""Plan 190 F2 — Compatibilidad congelada (bundles viejos y nuevos).

Contrato de compatibilidad:
- CURRENT_SCHEMA_VERSION sigue en 1 (las secciones devops son aditivas y opcionales).
- Un bundle viejo (sin secciones devops) importa idéntico a hoy: la respuesta NO
  incluye `devops` ni `skipped_sections`.
- meta.sections del bundle refleja SOLO las secciones efectivamente exportadas.
- El export de las secciones devops es determinista (mismo dato → mismo checksum,
  salvo meta.exportedAt que es un timestamp).
- La ruta per-proyecto SALTEA las secciones devops (son globales).
"""
from __future__ import annotations

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
        self.store.pop((service, key), None)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import services.config_transfer as ct
    import services.deploy_store as deploy_store
    import services.server_registry as server_registry
    import project_manager
    from config import config as cfg

    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(server_registry, "data_dir", lambda: data)
    monkeypatch.setattr(server_registry, "keyring", FakeKeyring())
    monkeypatch.setattr(deploy_store, "data_dir", lambda: data)
    monkeypatch.setattr(ct, "data_dir", lambda: data)
    monkeypatch.setattr(project_manager, "get_active_project", lambda: "__TESTPROJ__")
    monkeypatch.setattr(project_manager, "get_all_projects", lambda: [])
    monkeypatch.setattr(cfg, FLAG, True, raising=False)

    return {"data": data, "ct": ct, "sr": server_registry, "ds": deploy_store,
            "cfg": cfg, "monkeypatch": monkeypatch}


def _app(app_id="webapp"):
    return {
        "id": app_id,
        "name": "Web App",
        "artifact": {"kind": "folder", "path": "C:\\build\\web"},
        "targets": {
            "prod": {
                "install_path": "C:\\inetpub\\web",
                "smoke": {"kind": "none"},
            }
        },
    }


def test_schema_version_sigue_en_1(env):
    assert env["ct"].CURRENT_SCHEMA_VERSION == 1


def test_kpi4_bundle_viejo_importa_identico(env):
    ct = env["ct"]
    # Bundle "viejo": solo secciones existentes (uiPreferences), sin devops.
    bundle = ct.build_all_projects_export(sections=["uiPreferences"])
    assert "devopsServers" not in bundle
    assert "devopsApps" not in bundle

    res = ct.apply_all_projects_import(bundle, mode="merge")
    assert res["applied"] is True
    # La respuesta NO gana claves nuevas para un bundle viejo.
    assert "devops" not in res
    assert "skipped_sections" not in res


def test_meta_sections_refleja_seleccion(env):
    sr, ds, ct = env["sr"], env["ds"], env["ct"]
    sr.upsert_server("a", "a.com", "", "u", "")
    ds.upsert_app(_app())

    bundle = ct.build_all_projects_export(sections=["devopsServers"])
    assert bundle["meta"]["sections"] == ["devopsServers"]
    assert "devopsApps" not in bundle


def test_checksum_estable_con_devops(env):
    sr, ds, ct = env["sr"], env["ds"], env["ct"]
    sr.upsert_server("a", "a.com", "", "u", "notas")
    ds.upsert_app(_app())

    b1 = ct.build_all_projects_export(sections=["devopsServers", "devopsApps"])
    b2 = ct.build_all_projects_export(sections=["devopsServers", "devopsApps"])
    # El único no-determinismo legítimo es meta.exportedAt (timestamp); igualarlo.
    b1["meta"]["exportedAt"] = b2["meta"]["exportedAt"] = "FIXED"
    assert ct.compute_checksum(b1) == ct.compute_checksum(b2)
    assert b1["devopsServers"] == b2["devopsServers"]
    assert b1["devopsApps"] == b2["devopsApps"]


def test_per_project_saltea_devops(env, monkeypatch):
    ct, sr = env["ct"], env["sr"]
    import project_manager

    # El proyecto existe → compute_diff no agrega 'projects add' y no escribe nada.
    monkeypatch.setattr(project_manager, "get_project_config", lambda name: {"name": str(name).upper()})
    bundle = {
        "meta": {"schemaVersion": 1},
        "devopsServers": {
            "servers": [{"alias": "a", "host": "a.com", "domain": "", "username": "u", "notes": ""}],
            "credentials_manifest": [],
        },
    }
    res = ct.apply_import("SOMEPROJ", bundle, mode="merge")
    assert res.get("skipped_sections") == ["devopsServers"]
    # Stores globales intactos: la ruta per-proyecto NUNCA aplica devops.
    assert sr.list_servers() == []
