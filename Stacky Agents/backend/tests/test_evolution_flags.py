"""Plan 167 F0 — flags del Centro de Evolución (patrón triple, tests primero).

Espejo estructural de tests/test_plan128_plans_board_flag.py. 4 flags:
- STACKY_EVOLUTION_CENTER_ENABLED (bool, default ON, master)
- STACKY_EVOLUTION_CYCLE_ENABLED (bool, default ON, requires master)
- STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED (bool, default OFF, requires master)
- STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET (int, default 20000 en config, SIN default= en spec)
"""
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

_CENTER = "STACKY_EVOLUTION_CENTER_ENABLED"
_CYCLE = "STACKY_EVOLUTION_CYCLE_ENABLED"
_AUTO = "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED"
_BUDGET = "STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET"
_ALL = (_CENTER, _CYCLE, _AUTO, _BUDGET)


def _spec(key):
    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_center_flag_en_registry():
    spec = _spec(_CENTER)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True


def test_cycle_flag_requires_center():
    spec = _spec(_CYCLE)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == _CENTER


def test_auto_apply_default_off():
    spec = _spec(_AUTO)
    assert spec is not None
    assert spec.default is None  # C1: no curada, default efectivo OFF en config.py
    import config
    assert config.config.STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED is False


def test_budget_flag_int():
    spec = _spec(_BUDGET)
    assert spec is not None
    assert spec.type == "int"
    assert spec.default is None  # C1: el default efectivo 20000 lo da config.py (caso 6)
    assert spec.requires == _CENTER


def test_las_4_estan_categorizadas():
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
        assert config.config.STACKY_EVOLUTION_CENTER_ENABLED is True
        assert config.config.STACKY_EVOLUTION_CYCLE_ENABLED is True
        assert config.config.STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET == 20000
    finally:
        importlib.reload(config)


def test_aristas_requires_congeladas():
    for hija in (_CYCLE, _AUTO, _BUDGET):
        spec = _spec(hija)
        assert spec is not None
        assert spec.requires == _CENTER


def test_help_presente():
    for key in _ALL:
        assert key in PLAIN_HELP, f"{key} sin entrada en PLAIN_HELP"
