"""Plan 170 F0 — flags del flywheel de conocimiento (patrón triple, tests primero).

Espejo estructural de tests/test_optimizer_flags.py del 169 F0. 5 flags:
- STACKY_KNOWLEDGE_FLYWHEEL_ENABLED   (bool, default ON, requires master 167)
- STACKY_KNOWLEDGE_INJECTION_ENABLED  (bool, default ON, requires master 167)
- STACKY_KNOWLEDGE_INJECT_TOP_N        (int, efectivo 3, SIN default= — C14)
- STACKY_KNOWLEDGE_INJECT_MAX_CHARS    (int, efectivo 4000, SIN default= — C14)
- STACKY_KNOWLEDGE_MAX_LESSONS         (int, efectivo 200, SIN default= — C14)

Nota C14 (verificada 167/168/169): `default_is_known(spec) = spec.default is not None`
es TYPE-AGNOSTIC (harness_flags.py). Una FlagSpec int con `default=N` rompe
`test_default_known_only_for_curated` porque los int NO se curan. Por eso las 3 int
van SIN `default=` y el efectivo vive en config.py; este test lo verifica por config.
"""
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP
from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

_ROOT = "STACKY_EVOLUTION_CENTER_ENABLED"
_FLYWHEEL = "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED"
_INJECTION = "STACKY_KNOWLEDGE_INJECTION_ENABLED"
_TOP_N = "STACKY_KNOWLEDGE_INJECT_TOP_N"
_MAX_CHARS = "STACKY_KNOWLEDGE_INJECT_MAX_CHARS"
_MAX_LESSONS = "STACKY_KNOWLEDGE_MAX_LESSONS"
_ALL = (_FLYWHEEL, _INJECTION, _TOP_N, _MAX_CHARS, _MAX_LESSONS)


def _spec(key):
    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_flywheel_flag_en_registry():
    spec = _spec(_FLYWHEEL)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == _ROOT


def test_injection_flag_en_registry():
    spec = _spec(_INJECTION)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == _ROOT


def test_top_n_flag_int():
    spec = _spec(_TOP_N)
    assert spec is not None
    assert spec.type == "int"
    assert spec.default is None  # C14 — efectivo 3 en config.py (test_config_defaults)
    assert spec.requires == _ROOT


def test_max_chars_flag_int():
    spec = _spec(_MAX_CHARS)
    assert spec is not None
    assert spec.type == "int"
    assert spec.default is None  # C14
    assert spec.requires == _ROOT


def test_max_lessons_flag_int():
    spec = _spec(_MAX_LESSONS)
    assert spec is not None
    assert spec.type == "int"
    assert spec.default is None  # C14
    assert spec.requires == _ROOT


def test_las_5_estan_categorizadas():
    flat = [k for keys in _CATEGORY_KEYS.values() for k in keys]
    for key in _ALL:
        assert key in flat, f"{key} no está en _CATEGORY_KEYS"


def test_config_defaults_y_aristas(monkeypatch):
    for key in _ALL:
        monkeypatch.delenv(key, raising=False)
    import importlib
    import config
    importlib.reload(config)
    try:
        assert config.config.STACKY_KNOWLEDGE_FLYWHEEL_ENABLED is True
        assert config.config.STACKY_KNOWLEDGE_INJECTION_ENABLED is True
        assert config.config.STACKY_KNOWLEDGE_INJECT_TOP_N == 3
        assert config.config.STACKY_KNOWLEDGE_INJECT_MAX_CHARS == 4000
        assert config.config.STACKY_KNOWLEDGE_MAX_LESSONS == 200
    finally:
        importlib.reload(config)
    for key in _ALL:
        assert _REQUIRES_MAP_FROZEN.get(key) == _ROOT


def test_help_presente():
    for key in _ALL:
        assert key in PLAIN_HELP, f"{key} sin entrada en PLAIN_HELP"
