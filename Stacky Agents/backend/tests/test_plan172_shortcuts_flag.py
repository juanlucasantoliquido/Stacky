"""Plan 172 F0 — La flag de atajos, cableada por la vía canónica completa.

El kill-switch existe desde el día cero: si el registro de atajos molesta, se
apaga y quedan exactamente los 3 atajos de siempre.
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

_KEY = "STACKY_UI_SHORTCUTS_ENABLED"


def test_flag_registrada_default_on():
    from config import config as cfg
    from services.harness_flags import FLAG_REGISTRY

    spec = next((s for s in FLAG_REGISTRY if s.key == _KEY), None)
    assert spec is not None
    assert spec.type == "bool" and spec.default is True
    assert getattr(cfg, _KEY) is True


def test_flag_categorizada_y_curada():
    from services.harness_flags import _CATEGORY_KEYS
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    todas = {k for keys in _CATEGORY_KEYS.values() for k in keys}
    assert _KEY in todas
    assert _KEY in _CURATED_DEFAULTS_ON


def test_flag_no_declara_requires():
    """Es un kill-switch de presentación: no cuelga de nada."""
    from services.harness_flags import FLAG_REGISTRY

    spec = next(s for s in FLAG_REGISTRY if s.key == _KEY)
    assert spec.requires is None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def test_health_expone_la_flag(client):
    # OJO: el bloque de flags de UI vive en /api/diag/health, no en /api/health.
    body = client.get("/api/diag/health").get_json()

    assert isinstance(body.get("ui_shortcuts_enabled"), bool)
    # Las keys que el frontend ya consumía no se pueden perder.
    assert "shell_v2_enabled" in body


def test_health_refleja_el_valor_real(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY, False, raising=False)

    assert client.get("/api/diag/health").get_json()["ui_shortcuts_enabled"] is False
