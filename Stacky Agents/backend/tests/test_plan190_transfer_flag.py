"""Plan 190 F0 — Flag + composición dinámica del catálogo de secciones.

Verifica: FlagSpec declarada (bool, default ON, sin requires), pertenencia a
_CURATED_DEFAULTS_ON, ALL_SECTIONS intacta (guardia anti-regresión), y que
available_sections() respeta la flag y el scope (devops solo en scope "all").
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import services.config_transfer as ct  # noqa: E402

FLAG = "STACKY_CONFIG_TRANSFER_DEVOPS_ENABLED"


def _spec():
    from services.harness_flags import FLAG_REGISTRY

    return next((s for s in FLAG_REGISTRY if s.key == FLAG), None)


def test_flag_declarada_bool_default_on():
    spec = _spec()
    assert spec is not None, f"FlagSpec {FLAG} no está en el registry"
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires is None


def test_flag_en_curated_defaults_on():
    # La vía canónica del default ON es la pertenencia al set curado.
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert FLAG in _CURATED_DEFAULTS_ON


def test_all_sections_intacta():
    assert ct.ALL_SECTIONS == (
        "settings",
        "integrations",
        "workflows",
        "agentProfiles",
        "clientProfile",
        "uiPreferences",
        "secretsRef",
    )


def test_available_sections_on(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, FLAG, True, raising=False)
    got = ct.available_sections("all")
    assert got[-2:] == ("devopsServers", "devopsApps")
    assert got[: len(ct.ALL_SECTIONS)] == ct.ALL_SECTIONS


def test_available_sections_off(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, FLAG, False, raising=False)
    assert ct.available_sections("all") == ct.ALL_SECTIONS


def test_project_scope_sin_devops(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, FLAG, True, raising=False)
    # scope "project" NUNCA incluye devops, aun con flag ON.
    assert ct.available_sections("project") == ct.ALL_SECTIONS


def test_catalogo_endpoint_refleja_flag(monkeypatch):
    from flask import Flask

    from api.config_transfer import bp
    from config import config as cfg

    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()

    monkeypatch.setattr(cfg, FLAG, True, raising=False)
    on = client.get("/config/sections").get_json()["sections"]
    assert "devopsServers" in on and "devopsApps" in on

    monkeypatch.setattr(cfg, FLAG, False, raising=False)
    off = client.get("/config/sections").get_json()["sections"]
    assert "devopsServers" not in off and "devopsApps" not in off
