"""tests/test_plan130_code_integrity_flag.py — Plan 130 F0.

Flag STACKY_CODE_INTEGRITY_ENABLED: patron triple default ON (espejo Plan 127 SS3.6 /
tanda default-ON 93-108). 7 casos.
"""
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

_KEY = "STACKY_CODE_INTEGRITY_ENABLED"


def _spec():
    return next((s for s in FLAG_REGISTRY if s.key == _KEY), None)


def test_flag_declarada_bool():
    spec = _spec()
    assert spec is not None
    assert spec.type == "bool"
    assert spec.group == "global"


def test_flag_default_true_en_spec():
    spec = _spec()
    assert spec.default is True


def test_flag_ui_editable():
    spec = _spec()
    assert spec.env_only is False
    assert spec.requires is None


def test_flag_en_set_curado():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert _KEY in _CURATED_DEFAULTS_ON


def test_config_default_on(monkeypatch):
    monkeypatch.delenv(_KEY, raising=False)
    import importlib
    import config

    importlib.reload(config)
    try:
        assert config.config.STACKY_CODE_INTEGRITY_ENABLED is True
    finally:
        importlib.reload(config)


def test_categoria_capacidades_optin():
    assert _KEY in _CATEGORY_KEYS["capacidades_optin"]


def test_help_y_defaults_env_sin_linea_off():
    from services.harness_flags_help import PLAIN_HELP
    from pathlib import Path

    assert _KEY in PLAIN_HELP

    env_path = Path(__file__).resolve().parents[1] / "harness_defaults.env"
    text = env_path.read_text(encoding="utf-8")
    assert f"{_KEY}=false" not in text
