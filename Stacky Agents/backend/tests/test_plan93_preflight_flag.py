"""Plan 93 F0 — flag STACKY_DEVOPS_PREFLIGHT_ENABLED (tests primero).

Espejo de tests/test_plan91_servers_flag.py, con los valores correctos para
esta flag: default OFF (SIN `default=` en el FlagSpec, gotcha
_CURATED_DEFAULTS_ON), requires STACKY_DEVOPS_PANEL_ENABLED.
"""
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

_KEY = "STACKY_DEVOPS_PREFLIGHT_ENABLED"


def _spec():
    return next((s for s in FLAG_REGISTRY if s.key == _KEY), None)


def test_f0_flag_in_registry():
    spec = _spec()
    assert spec is not None
    assert spec.type == "bool"
    assert spec.env_only is False
    assert spec.default is None  # SIN default= explícito (gotcha _CURATED_DEFAULTS_ON)
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"
    assert spec.group == "global"
    assert spec.label  # no vacío


def test_f0_flag_in_category_devops():
    assert _KEY in _CATEGORY_KEYS["devops"]


def test_f0_config_default_off(monkeypatch):
    monkeypatch.delenv(_KEY, raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_DEVOPS_PREFLIGHT_ENABLED is False


def test_f0_flag_has_plain_help():
    assert _KEY in PLAIN_HELP


def test_f0_harness_defaults_contains_flag():
    backend_root = Path(__file__).parent.parent
    defaults_path = backend_root / "harness_defaults.env"
    assert defaults_path.exists()
    content = defaults_path.read_text(encoding="utf-8")
    assert "STACKY_DEVOPS_PREFLIGHT_ENABLED=false" in content
