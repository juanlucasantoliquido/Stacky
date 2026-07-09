"""Plan 106 F0/F2 — Config + flags del arnés para el modelo local (Qwen 3 u otro).

F0: 4 configs (LOCAL_LLM_ENABLED bool, LOCAL_LLM_ENDPOINT str, LOCAL_LLM_MODEL str,
LOCAL_LLM_TIMEOUT_SEC int) editables por UI, flag master default OFF, health expuesto
en api/diag.py.

F2: modo avanzado LLM_BACKEND=local_llm reconocido por services/llm_router.py
(_available_models, decide) sin romper los backends existentes.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


# ── F0 ───────────────────────────────────────────────────────────────────────

def test_f0_flag_default_off():
    import importlib
    import config as cfg
    importlib.reload(cfg)
    assert cfg.config.LOCAL_LLM_ENABLED is False


def test_f0_flags_registered_in_registry():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in (
        "LOCAL_LLM_ENABLED",
        "LOCAL_LLM_ENDPOINT",
        "LOCAL_LLM_MODEL",
        "LOCAL_LLM_TIMEOUT_SEC",
    ):
        assert key in by_key, f"{key} no está en FLAG_REGISTRY"

    assert by_key["LOCAL_LLM_ENABLED"].requires is None
    assert by_key["LOCAL_LLM_ENDPOINT"].requires == "LOCAL_LLM_ENABLED"
    assert by_key["LOCAL_LLM_MODEL"].requires == "LOCAL_LLM_ENABLED"
    assert by_key["LOCAL_LLM_TIMEOUT_SEC"].requires == "LOCAL_LLM_ENABLED"


def test_f0_flags_have_plain_help():
    from services.harness_flags_help import PLAIN_HELP

    for key in (
        "LOCAL_LLM_ENABLED",
        "LOCAL_LLM_ENDPOINT",
        "LOCAL_LLM_MODEL",
        "LOCAL_LLM_TIMEOUT_SEC",
    ):
        assert key in PLAIN_HELP, f"{key} no tiene PlainHelp"


def test_f0_config_defaults():
    import importlib
    import config as cfg
    importlib.reload(cfg)
    assert cfg.config.LOCAL_LLM_ENDPOINT == "http://localhost:11434/v1/chat/completions"
    assert cfg.config.LOCAL_LLM_MODEL == "qwen3:32b"
    assert cfg.config.LOCAL_LLM_TIMEOUT_SEC == 120


def test_f0_health_exposes_local_llm_enabled():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    r = c.get("/api/diag/health")
    assert r.status_code == 200
    assert "local_llm_enabled" in r.get_json()


# ── F2 ───────────────────────────────────────────────────────────────────────

def test_f2_available_models_local_backend(monkeypatch):
    import config as cfg
    from services import llm_router

    monkeypatch.setattr(cfg.config, "LLM_BACKEND", "local_llm")
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_MODEL", "qwen-test:1b")
    assert llm_router._available_models() == ["qwen-test:1b"]


def test_f2_decide_local_backend(monkeypatch):
    import config as cfg
    from services import llm_router

    monkeypatch.setattr(cfg.config, "LOCAL_LLM_MODEL", "qwen-test:1b")
    decision = llm_router.decide(
        agent_type="developer", blocks=[], backend="local_llm",
    )
    assert decision.model == "qwen-test:1b"


def test_f2_available_models_other_backend_unchanged(monkeypatch):
    import config as cfg
    from services import llm_router

    monkeypatch.setattr(cfg.config, "LLM_BACKEND", "mock")
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_MODEL", "qwen-test-unique:1b")
    assert "qwen-test-unique:1b" not in llm_router._available_models()
