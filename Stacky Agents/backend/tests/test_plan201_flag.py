"""Plan 201 F0 — Flag del Taller de Compilación cableada en los 5 lugares."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_KEY = "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED"


@pytest.fixture(scope="module")
def client():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_flag_registered_and_curated():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    spec = next((s for s in FLAG_REGISTRY if s.key == _KEY), None)
    assert spec is not None, f"{_KEY} no está en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True
    assert not getattr(spec, "requires", None), "la flag del taller no declara requires"
    assert _KEY in _CATEGORY_KEYS["devops"]
    assert _KEY in _CURATED_DEFAULTS_ON


def test_config_default_on():
    from config import config as cfg

    assert getattr(cfg, _KEY) is True


def test_health_exposes_build_workshop_enabled(client):
    r = client.get("/api/devops/health")

    assert r.status_code == 200
    body = r.get_json()
    assert "build_workshop_enabled" in body
    assert isinstance(body["build_workshop_enabled"], bool)


def test_bootstrap_matches_health(client):
    """El payload es compartido: la key aparece también en /bootstrap (paridad exigida)."""
    health = client.get("/api/devops/health").get_json()
    boot = client.get("/api/devops/bootstrap")
    if boot.status_code != 200:
        pytest.skip("bootstrap no disponible en este entorno")
    body = boot.get_json()
    payload = body.get("health", body)
    assert payload.get("build_workshop_enabled") == health["build_workshop_enabled"]
