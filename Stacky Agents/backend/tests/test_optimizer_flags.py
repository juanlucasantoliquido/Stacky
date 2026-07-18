"""Plan 169 F0 — flags del optimizador evolutivo (patrón triple, tests primero).

Espejo estructural de tests/test_fitness_flags.py del 168 F0. 5 flags:
- STACKY_EVOLUTION_OPTIMIZER_ENABLED (bool, default ON, requires master 167)
- STACKY_EVOLUTION_OPTIMIZER_GENERATOR (str, efectivo "auto" en config, SIN default= — C14)
- STACKY_EVOLUTION_OPTIMIZER_VARIANTS (int, efectivo 3, SIN default= — C14)
- STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET (int, efectivo 60000, SIN default= — C14)
- STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT (int, efectivo 2, SIN default= — C14)
"""
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP
from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

_ROOT = "STACKY_EVOLUTION_CENTER_ENABLED"
_ENABLED = "STACKY_EVOLUTION_OPTIMIZER_ENABLED"
_GENERATOR = "STACKY_EVOLUTION_OPTIMIZER_GENERATOR"
_VARIANTS = "STACKY_EVOLUTION_OPTIMIZER_VARIANTS"
_BUDGET = "STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET"
_MARGIN = "STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT"
_ALL = (_ENABLED, _GENERATOR, _VARIANTS, _BUDGET, _MARGIN)


def _spec(key):
    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_master_flag_en_registry():
    spec = _spec(_ENABLED)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == _ROOT


def test_generator_flag_str():
    spec = _spec(_GENERATOR)
    assert spec is not None
    assert spec.type == "str"
    assert spec.default is None  # C14 — el efectivo "auto" lo verifica test_config_defaults
    assert spec.requires == _ROOT


def test_variants_y_budget_int():
    v = _spec(_VARIANTS)
    b = _spec(_BUDGET)
    assert v is not None and v.type == "int" and v.default is None  # C14
    assert b is not None and b.type == "int" and b.default is None  # C14
    assert v.requires == _ROOT and b.requires == _ROOT


def test_margin_flag_int():
    spec = _spec(_MARGIN)
    assert spec is not None
    assert spec.type == "int"
    assert spec.default is None  # C14
    assert spec.requires == _ROOT


def test_las_5_estan_categorizadas():
    flat = [k for keys in _CATEGORY_KEYS.values() for k in keys]
    for key in _ALL:
        assert key in flat, f"{key} no está en _CATEGORY_KEYS"


def test_config_defaults(monkeypatch):
    for key in _ALL:
        monkeypatch.delenv(key, raising=False)
    import importlib
    import config
    importlib.reload(config)
    try:
        assert config.config.STACKY_EVOLUTION_OPTIMIZER_ENABLED is True
        assert config.config.STACKY_EVOLUTION_OPTIMIZER_GENERATOR == "auto"
        assert config.config.STACKY_EVOLUTION_OPTIMIZER_VARIANTS == 3
        assert config.config.STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET == 60000
        assert config.config.STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT == 2
    finally:
        importlib.reload(config)


def test_aristas_requires_congeladas():
    for key in _ALL:
        assert _REQUIRES_MAP_FROZEN.get(key) == _ROOT
        spec = _spec(key)
        assert spec is not None
        assert spec.requires == _ROOT


def test_help_presente():
    for key in _ALL:
        assert key in PLAIN_HELP, f"{key} sin entrada en PLAIN_HELP"
