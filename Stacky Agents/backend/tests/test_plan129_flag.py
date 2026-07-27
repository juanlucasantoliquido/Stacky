"""Plan 129 F0 — flag STACKY_PALETTE_DEEP_SEARCH_ENABLED + health de la paleta global."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config
from services.harness_flags import FLAG_REGISTRY, read_current

_KEY = "STACKY_PALETTE_DEEP_SEARCH_ENABLED"


def _spec():
    return next(s for s in FLAG_REGISTRY if s.key == _KEY)


def test_flag_conocida():
    keys = {row["key"] for row in read_current()}
    assert _KEY in keys


def test_flag_default_on():
    """Barrido default-ON 2026-07-27: la búsqueda es LOCAL (sin IA), de solo
    lectura y solo corre cuando el operador abre la paleta y tipea — no quema
    tokens en reposo ni escribe en ningún sistema real."""
    assert config.STACKY_PALETTE_DEEP_SEARCH_ENABLED is True


def test_flag_curada():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    assert _KEY in _CURATED_DEFAULTS_ON
    assert _spec().default is True


@pytest.fixture
def app_client():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_search_health_siempre_200(app_client):
    resp = app_client.get("/api/search/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    # El health refleja el estado REAL de la flag, no un literal: tras el barrido
    # default-ON 2026-07-27 nace encendida.
    assert data["flag_enabled"] is config.STACKY_PALETTE_DEEP_SEARCH_ENABLED
