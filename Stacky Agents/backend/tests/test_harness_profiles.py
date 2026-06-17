"""V0.1 — Tests de perfiles del arnés (services/harness_profiles.py)."""
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
    # Limpia las env vars gestionadas para no contaminar entre tests.
    from services.harness_profiles import _managed_keys

    for key in _managed_keys():
        monkeypatch.delenv(key, raising=False)
    yield


def test_apply_full_turns_on_flags():
    from services.harness_profiles import apply_profile
    from config import config

    applied = apply_profile("full")
    assert applied["CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED"] is True
    assert applied["STACKY_RUNAWAY_MAX_TURNS"] == 80
    # config refleja el cambio al instante
    assert config.CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED is True
    assert config.STACKY_SKILLS_ENABLED is True
    # env_only flag va a os.environ
    assert os.getenv("STACKY_MEMORY_INJECTION_ENABLED") == "true"


def test_apply_off_turns_off_union():
    from services.harness_profiles import apply_profile, _managed_keys
    from config import config

    apply_profile("full")
    apply_profile("off")
    # toda clave gestionada queda apagada
    assert config.CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED is False
    assert config.STACKY_RUNAWAY_MAX_TURNS == 0
    assert config.STACKY_SKILLS_ENABLED is False
    assert os.getenv("STACKY_MEMORY_INJECTION_ENABLED") == "false"


def test_unknown_profile_raises():
    from services.harness_profiles import apply_profile

    with pytest.raises(ValueError):
        apply_profile("turbo")


def test_detect_full():
    from services.harness_profiles import apply_profile, detect_profile

    apply_profile("full")
    assert detect_profile() == "full"


def test_detect_safe():
    from services.harness_profiles import apply_profile, detect_profile

    apply_profile("safe")
    assert detect_profile() == "safe"


def test_detect_off():
    from services.harness_profiles import apply_profile, detect_profile

    apply_profile("off")
    assert detect_profile() == "off"


def test_detect_custom_returns_none():
    from services.harness_profiles import apply_profile, detect_profile
    from config import config

    apply_profile("safe")
    # cambiar un solo flag rompe el match exacto → custom
    config.STACKY_RUNAWAY_MAX_TURNS = 999
    assert detect_profile() is None


def test_respect_explicit_env_on_boot(monkeypatch):
    from services.harness_profiles import apply_profile
    from config import config

    # operador fijó explícitamente un valor distinto al del preset
    monkeypatch.setenv("STACKY_RUNAWAY_MAX_TURNS", "42")
    applied = apply_profile("safe", respect_explicit_env=True)
    # el perfil NO pisó la env explícita
    assert "STACKY_RUNAWAY_MAX_TURNS" not in applied
    # pero sí aplicó las claves no definidas explícitamente
    assert applied["CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED"] is True


# ---------------------------------------------------------------------------
# Endpoint: POST /api/harness-flags/profile + GET active_profile
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
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
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def test_post_profile_full_then_get_reflects(client):
    r = client.post("/api/harness-flags/profile", json={"name": "full"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["active_profile"] == "full"

    g = client.get("/api/harness-flags").get_json()
    assert g["active_profile"] == "full"


def test_post_profile_unknown_returns_400(client):
    r = client.post("/api/harness-flags/profile", json={"name": "turbo"})
    assert r.status_code == 400
    body = r.get_json()
    assert body["ok"] is False
    assert "off" in body["valid_profiles"]
