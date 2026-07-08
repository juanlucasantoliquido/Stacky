"""tests/test_plan94_variables_flag.py — Plan 94 F0.
Tests de la flag STACKY_DEVOPS_VARIABLES_ENABLED (6 patas)."""
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

_KEY = "STACKY_DEVOPS_VARIABLES_ENABLED"


def _spec():
    return next((s for s in FLAG_REGISTRY if s.key == _KEY), None)


def test_f0_flag_in_registry():
    """La flag está en FLAG_REGISTRY con metadatos correctos."""
    spec = _spec()
    assert spec is not None
    assert spec.type == "bool"
    assert spec.env_only is False  # editable por UI
    assert spec.default is None  # SIN default= explícito (gotcha _CURATED_DEFAULTS_ON)
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"
    assert spec.group == "global"
    assert "94" in spec.label
    assert spec.label  # no vacío


def test_f0_flag_in_category_devops():
    """La flag está en la categoría 'devops'."""
    assert _KEY in _CATEGORY_KEYS["devops"]


def test_f0_config_default_off(monkeypatch):
    """La flag existe en config.py y default es OFF."""
    monkeypatch.delenv(_KEY, raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_DEVOPS_VARIABLES_ENABLED is False


def test_f0_flag_has_plain_help():
    """La flag tiene entrada PlainHelp."""
    assert _KEY in PLAIN_HELP


def test_f0_harness_defaults_contains_flag():
    """La flag tiene línea en harness_defaults.env (default false)."""
    backend_root = Path(__file__).parent.parent
    defaults_path = backend_root / "harness_defaults.env"
    assert defaults_path.exists()
    content = defaults_path.read_text(encoding="utf-8")
    assert f"{_KEY}=false" in content


def test_f0_requires_map_includes_plan94():
    """La arista de requires está en el mapa congelado (C1 — 6ª pata)."""
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN
    assert _REQUIRES_MAP_FROZEN.get(_KEY) == "STACKY_DEVOPS_PANEL_ENABLED"

