"""tests/test_plan89_environments_flag.py — F0: alta de la flag
STACKY_DEVOPS_ENVIRONMENTS_ENABLED (4 patas + deploy). Patrón: planes 87/88 F0.
"""
import importlib


def test_f0_flag_in_registry():
    from services.harness_flags import FLAG_REGISTRY
    spec = next((f for f in FLAG_REGISTRY if f.key == "STACKY_DEVOPS_ENVIRONMENTS_ENABLED"), None)
    assert spec is not None
    assert spec.env_only is False
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"
    assert spec.group == "global"
    assert spec.label


def test_f0_flag_in_category_devops():
    from services.harness_flags import _CATEGORY_KEYS
    assert "STACKY_DEVOPS_ENVIRONMENTS_ENABLED" in _CATEGORY_KEYS["devops"]


def test_f0_config_default_on(monkeypatch):
    monkeypatch.delenv("STACKY_DEVOPS_ENVIRONMENTS_ENABLED", raising=False)
    import config
    importlib.reload(config)
    assert config.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED is True
    monkeypatch.delenv("STACKY_DEVOPS_ENVIRONMENTS_ENABLED", raising=False)
    importlib.reload(config)


def test_f0_flag_has_plain_help():
    from services.harness_flags_help import plain_help_for
    help_ = plain_help_for("STACKY_DEVOPS_ENVIRONMENTS_ENABLED")
    assert help_ is not None
    assert help_["what"]


def test_f0_harness_defaults_contains_flag():
    from pathlib import Path
    text = (Path(__file__).parent.parent / "harness_defaults.env").read_text(encoding="utf-8")
    assert "STACKY_DEVOPS_ENVIRONMENTS_ENABLED=true" in text
