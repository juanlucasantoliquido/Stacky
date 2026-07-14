"""Plan 128 F0 — flag STACKY_PLANS_BOARD_ENABLED (tests primero).

Espejo de tests/test_plan93_preflight_flag.py. Default OFF (opt-in): la flag
NO tiene `default=` explícito en el FlagSpec (queda en el sentinel None del
dataclass) y config.py cae a "false" sin env var. Sin `requires` (no tiene
master). Categoría `observabilidad_notif` (existente).
"""
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

_KEY = "STACKY_PLANS_BOARD_ENABLED"


def _spec():
    return next((s for s in FLAG_REGISTRY if s.key == _KEY), None)


def test_flag_declarada_en_registry():
    spec = _spec()
    assert spec is not None
    assert spec.type == "bool"
    assert spec.label  # no vacío


def test_flag_ui_editable():
    spec = _spec()
    assert spec.env_only is False


def test_flag_sin_default_explicito():
    spec = _spec()
    assert spec.default is None


def test_config_default_off(monkeypatch):
    monkeypatch.delenv(_KEY, raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_PLANS_BOARD_ENABLED is False


def test_categoria_observabilidad():
    assert _KEY in _CATEGORY_KEYS["observabilidad_notif"]


def test_defaults_env_y_help():
    backend_root = Path(__file__).parent.parent
    defaults_path = backend_root / "harness_defaults.env"
    assert defaults_path.exists()
    content = defaults_path.read_text(encoding="utf-8")
    assert "STACKY_PLANS_BOARD_ENABLED=false" in content
    assert _KEY in PLAIN_HELP
