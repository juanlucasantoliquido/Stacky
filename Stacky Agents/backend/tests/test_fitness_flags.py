"""Plan 168 F0 — flags del arnés de fitness (patrón triple, tests primero).

Espejo estructural de tests/test_evolution_flags.py del 167 F0. 3 flags:
- STACKY_EVAL_HARNESS_ENABLED (bool, default ON, requires master 167)
- STACKY_EVAL_JUDGE_ENABLED (bool, default ON, requires master 167)
- STACKY_EVAL_RUN_TOKEN_BUDGET (int, default 30000 en config, SIN default= en spec — v2 C10)
"""
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP
from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

_ROOT = "STACKY_EVOLUTION_CENTER_ENABLED"
_HARNESS = "STACKY_EVAL_HARNESS_ENABLED"
_JUDGE = "STACKY_EVAL_JUDGE_ENABLED"
_BUDGET = "STACKY_EVAL_RUN_TOKEN_BUDGET"
_ALL = (_HARNESS, _JUDGE, _BUDGET)


def _spec(key):
    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_harness_flag_en_registry():
    spec = _spec(_HARNESS)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == _ROOT


def test_judge_flag_en_registry():
    spec = _spec(_JUDGE)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == _ROOT


def test_budget_flag_int():
    spec = _spec(_BUDGET)
    assert spec is not None
    assert spec.type == "int"
    assert spec.default is None  # v2 C10 — el default EFECTIVO 30000 lo da config.py (caso 5)
    assert spec.requires == _ROOT


def test_las_3_estan_categorizadas():
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
        assert config.config.STACKY_EVAL_HARNESS_ENABLED is True
        assert config.config.STACKY_EVAL_JUDGE_ENABLED is True
        assert config.config.STACKY_EVAL_RUN_TOKEN_BUDGET == 30000
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
