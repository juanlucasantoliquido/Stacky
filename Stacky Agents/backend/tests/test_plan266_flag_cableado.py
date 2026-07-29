"""Plan 266 F3.5 (A4) — las SEIS patas del cableado de la flag, en un solo gate.

El v3 de este plan listaba CINCO y se olvidaba de `_REQUIRES_MAP_FROZEN`
(test_harness_flags_requires.py:316 es una igualdad de conjuntos), lo que ponía
en ROJO un gate que estaba verde. Este test existe para que esa clase de error
no dependa de que alguien lea una tabla.
"""
import config
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS, categorize
from services.harness_flags_help import PLAIN_HELP
from tests.test_harness_flags import _CURATED_DEFAULTS_ON
from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

KEY = "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED"
MADRE = "STACKY_DB_COMPARE_ENABLED"


def _spec():
    for s in FLAG_REGISTRY:
        if s.key == KEY:
            return s
    return None


def test_pata1_config_declara_el_atributo():
    assert hasattr(config.config, KEY)
    assert getattr(config.config, KEY) is True


def test_pata2_flagspec_con_default_on_y_requires():
    spec = _spec()
    assert spec is not None, f"{KEY} no está en FLAG_REGISTRY"
    assert spec.default is True
    assert spec.type == "bool"
    assert spec.requires == MADRE
    assert spec.group == "comparador_bd"


def test_pata3_categoria_comparador_bd():
    assert KEY in _CATEGORY_KEYS["comparador_bd"]
    assert categorize(KEY) == "comparador_bd"


def test_pata4_curada_en_defaults_on():
    assert KEY in _CURATED_DEFAULTS_ON


def test_pata5_tiene_ayuda_llana():
    assert KEY in PLAIN_HELP
    entry = PLAIN_HELP[KEY]
    assert entry.what.strip()
    assert entry.on_effect.strip()
    assert entry.off_effect.strip()
    assert entry.example.strip()
    assert len(entry.what) <= 200


def test_pata6_arista_requires_congelada():
    assert _REQUIRES_MAP_FROZEN.get(KEY) == MADRE


def test_profundidad_1_la_madre_no_declara_requires():
    madre_spec = None
    for s in FLAG_REGISTRY:
        if s.key == MADRE:
            madre_spec = s
            break
    assert madre_spec is not None, f"{MADRE} no está en FLAG_REGISTRY"
    assert madre_spec.requires is None
