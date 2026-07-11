"""Plan 97 F0-bis — flag STACKY_DEVOPS_STACK_DETECT_ENABLED (tests primero)."""
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

_KEY = "STACKY_DEVOPS_STACK_DETECT_ENABLED"


def _spec():
    return next((s for s in FLAG_REGISTRY if s.key == _KEY), None)


def test_f0_flag_in_registry():
    spec = _spec()
    assert spec is not None
    assert spec.env_only is False
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"
    assert spec.group == "global"
    assert spec.label
    assert spec.default is True  # activación operador 2026-07-09 (curada en _CURATED_DEFAULTS_ON)


def test_f0_flag_in_category_devops():
    assert _KEY in _CATEGORY_KEYS["devops"]


def test_f0_config_default_on(monkeypatch):
    """Default ON desde 2026-07-09 (activación explícita del operador)."""
    monkeypatch.delenv(_KEY, raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_DEVOPS_STACK_DETECT_ENABLED is True


def test_f0_flag_has_plain_help():
    assert _KEY in PLAIN_HELP


def test_f0_harness_defaults_contains_flag():
    backend_root = Path(__file__).parent.parent
    defaults_path = backend_root / "harness_defaults.env"
    assert defaults_path.exists()
    content = defaults_path.read_text(encoding="utf-8")
    assert "STACKY_DEVOPS_STACK_DETECT_ENABLED=false" in content
