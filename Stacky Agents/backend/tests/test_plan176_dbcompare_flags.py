"""Plan 176 F0 — Las 4 flags del triage curado, registradas y expuestas en health."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_KEYS = (
    "STACKY_DB_COMPARE_TRIAGE_ENABLED",
    "STACKY_DB_COMPARE_GATES_ENABLED",
    "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED",
    "STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED",
)
_MASTER = "STACKY_DB_COMPARE_ENABLED"


def _spec(key: str):
    from services.harness_flags import FLAG_REGISTRY

    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_las_cuatro_flags_existen_en_registry():
    faltantes = [k for k in _KEYS if _spec(k) is None]

    assert not faltantes, faltantes


def test_las_cuatro_flags_default_on():
    from config import config as cfg
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    for key in _KEYS:
        assert _spec(key).default is True, key
        assert getattr(cfg, key) is True, key
        assert key in _CURATED_DEFAULTS_ON, \
            f"{key}: una bool default ON debe estar curada o rompe el meta-test"


def test_las_cuatro_flags_requieren_master():
    """Profundidad 1: la arista va al master, nunca a una flag hija."""
    for key in _KEYS:
        assert _spec(key).requires == _MASTER, key


def test_las_cuatro_flags_categorizadas_en_comparador_bd():
    from services.harness_flags import _CATEGORY_KEYS

    for key in _KEYS:
        assert key in _CATEGORY_KEYS["comparador_bd"], key


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


def test_health_reporta_flags_nuevas(client):
    r = client.get("/api/db-compare/health")

    assert r.status_code == 200
    body = r.get_json()
    for nueva in ("triage_enabled", "gates_enabled",
                  "table_prefs_enabled", "diff_ux_v2_enabled"):
        assert isinstance(body.get(nueva), bool), nueva
    # Las keys que ya consumía el frontend no se pueden perder.
    for vieja in ("flag_enabled", "data_diff_enabled", "config_in_place_enabled",
                  "webconfig_import_enabled", "migration_panel_enabled"):
        assert vieja in body, vieja
