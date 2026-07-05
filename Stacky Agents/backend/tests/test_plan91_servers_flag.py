"""Plan 91 F1 — flag master STACKY_DEVOPS_SERVERS_ENABLED (tests primero)."""
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

_KEY = "STACKY_DEVOPS_SERVERS_ENABLED"


def _spec():
    return next((s for s in FLAG_REGISTRY if s.key == _KEY), None)


def test_f1_flag_in_registry():
    spec = _spec()
    assert spec is not None
    assert spec.type == "bool"
    assert spec.env_only is False
    assert spec.default is None
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_f1_flag_in_devops_category():
    assert _KEY in _CATEGORY_KEYS["devops"]


def test_f1_harness_defaults_contains_flag():
    backend_root = Path(__file__).parent.parent
    defaults_path = backend_root / "harness_defaults.env"
    assert defaults_path.exists()
    content = defaults_path.read_text(encoding="utf-8")
    assert "STACKY_DEVOPS_SERVERS_ENABLED=false" in content


def test_f1_config_default_is_false(monkeypatch):
    monkeypatch.delenv("STACKY_DEVOPS_SERVERS_ENABLED", raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_DEVOPS_SERVERS_ENABLED is False


def test_f1_flag_has_plain_help():
    assert _KEY in PLAIN_HELP
