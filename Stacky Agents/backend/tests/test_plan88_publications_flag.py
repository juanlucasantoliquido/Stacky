"""Tests F0 — Plan 88: flag STACKY_DEVOPS_PUBLICATIONS_ENABLED en las 4 patas.

Patron: test_plan87_devops_flag.py / test_plan75_deep_links_wiring.py (C8).
"""
import importlib
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS


def _spec_for(key: str):
    return next((f for f in FLAG_REGISTRY if f.key == key), None)


def test_f0_flag_in_registry():
    spec = _spec_for("STACKY_DEVOPS_PUBLICATIONS_ENABLED")
    assert spec is not None
    assert spec.env_only is False
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"
    assert spec.group == "global"
    assert spec.label


def test_f0_flag_in_category_devops():
    assert "STACKY_DEVOPS_PUBLICATIONS_ENABLED" in _CATEGORY_KEYS["devops"]


def test_f0_config_default_off(monkeypatch):
    monkeypatch.delenv("STACKY_DEVOPS_PUBLICATIONS_ENABLED", raising=False)
    import config

    importlib.reload(config)
    try:
        assert config.config.STACKY_DEVOPS_PUBLICATIONS_ENABLED is False
    finally:
        importlib.reload(config)


def test_f0_flag_has_plain_help():
    from services.harness_flags_help import PLAIN_HELP

    assert "STACKY_DEVOPS_PUBLICATIONS_ENABLED" in PLAIN_HELP


def test_f0_harness_defaults_contains_flag():
    env_path = Path(__file__).resolve().parents[1] / "harness_defaults.env"
    assert env_path.exists()
    content = env_path.read_text(encoding="utf-8")
    assert "STACKY_DEVOPS_PUBLICATIONS_ENABLED=false" in content
