"""Plan 82 F4 — profile_deltas(): desvío respecto del perfil más cercano.

Mismo patrón de aislamiento de entorno que tests/test_harness_profiles.py
(grep "detect_profile" en tests/) para que apply_profile() real no contamine
otros tests.
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


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    from services.harness_profiles import _managed_keys

    for key in _managed_keys():
        monkeypatch.delenv(key, raising=False)
    yield


def test_deltas_zero_for_applied_profile():
    """[C2 v3] apply_profile('off') REAL dentro del test env → profile_deltas()['off'] == 0."""
    from services.harness_profiles import apply_profile, profile_deltas

    apply_profile("off")
    deltas = profile_deltas()
    assert deltas["off"] == 0


def test_deltas_counts_divergent_keys():
    from services.harness_profiles import apply_profile, profile_deltas
    from config import config

    apply_profile("safe")
    # desviar 2 keys del preset "safe"
    config.CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED = False
    config.STACKY_RUNAWAY_MAX_TURNS = 999
    deltas = profile_deltas()
    assert deltas["safe"] == 2


def test_deltas_keys_match_profiles():
    from services.harness_profiles import profile_deltas, PROFILES

    assert set(profile_deltas()) == set(PROFILES)


def test_get_endpoint_includes_profile_deltas(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    tmp_env = tmp_path / ".env"
    tmp_env.write_text("", encoding="utf-8")
    monkeypatch.setattr("api.global_config._ENV_PATH", tmp_env, raising=False)
    monkeypatch.setattr("api.harness_flags._ENV_PATH", tmp_env, raising=False)

    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    try:
        with app.test_client() as c:
            r = c.get("/api/harness-flags")
            assert r.status_code == 200
            body = r.get_json()
            assert "profile_deltas" in body
            assert set(body["profile_deltas"]) == {"off", "safe", "full"}
    finally:
        stop_stale_recovery()
        stop_manifest_watcher()
