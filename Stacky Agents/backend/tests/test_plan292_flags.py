"""tests/test_plan292_flags.py — Plan 292 F3.

Las dos opciones del sync parcial y sus guardianes.

POR QUE ESTE ARCHIVO IMPORTA REGLAS DE OTROS ARCHIVOS EN VEZ DE CONFIAR EN SU
CONTEO: dos de los guardianes viven en suites ROJAS DE FABRICA
(`test_harness_flags_help.py` 4F/4P y `test_harness_flags_bounds.py` 1F/17P). Un
conteo sobre un archivo ya rojo NO DISCRIMINA: si esta fase rompiera algo ahi, el
total no se moveria. Peor todavia con `_FROZEN_BOUNDS`, que da 1F/17P en los TRES
escenarios posibles — hacerlo bien, olvidarlo, y hacerlo al reves. Por eso los
casos 9, 11 y 12 traen la regla ajena a este archivo VERDE, donde si discrimina.
Patron ya usado en tests/test_plan257_flags.py:99-110.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_BOOL = "STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED"
_NUM = "STACKY_GITLAB_SYNC_FULL_CADA_N"
_LAS_DOS = (_BOOL, _NUM)


def _spec(key):
    from services.harness_flags import FLAG_REGISTRY

    coincidencias = [s for s in FLAG_REGISTRY if s.key == key]
    assert len(coincidencias) == 1, f"{key}: se esperaba 1 spec, hay {len(coincidencias)}"
    return coincidencias[0]


def test_las_dos_keys_estan_en_el_registro():
    from services.harness_flags import FLAG_REGISTRY

    presentes = [s.key for s in FLAG_REGISTRY]
    for key in _LAS_DOS:
        assert key in presentes
        assert presentes.count(key) == 1, f"{key} duplicada en FLAG_REGISTRY"


def test_la_booleana_nace_encendida():
    from services.harness_flags import declared_default, default_is_known
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    spec = _spec(_BOOL)
    assert spec.type == "bool"
    assert declared_default(spec) is True
    assert default_is_known(spec) is True
    assert _BOOL in _CURATED_DEFAULTS_ON


def test_la_numerica_no_declara_default():
    """`default_is_known(spec)` es literalmente `spec.default is not None`:
    declarar `default=` metería esta key en el conjunto que
    test_default_known_only_for_curated exige que sea EXACTAMENTE
    _CURATED_DEFAULTS_ON, que es solo para booleanas ON. El valor 10 vive solo en
    config.py."""
    from services.harness_flags import default_is_known
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    spec = _spec(_NUM)
    assert spec.type == "int"
    assert spec.default is None
    assert default_is_known(spec) is False
    assert _NUM not in _CURATED_DEFAULTS_ON


def test_la_numerica_declara_cotas():
    spec = _spec(_NUM)
    assert spec.min_value == 1
    assert spec.max_value == 1000


def test_ninguna_declara_requires():
    """Protege la decision de §3.5: STACKY_GITLAB_ENABLED no esta en
    FLAG_REGISTRY (usarlo de madre rompe R1 de validate_requires_graph) y la
    dependencia con STACKY_GITLAB_SYNC_ENABLED ya esta resuelta EN CODIGO. Como
    test_requires_map_is_frozen filtra con `if s.requires`, no declararlo deja el
    mapa congelado intacto: un guardian menos, sin trampa."""
    for key in _LAS_DOS:
        assert _spec(key).requires is None


def test_las_dos_existen_en_config():
    import config as _config_mod

    for key in _LAS_DOS:
        assert hasattr(_config_mod.config, key), f"{key} no esta en config.py"
    assert getattr(_config_mod.config, _BOOL) is True
    assert getattr(_config_mod.config, _NUM) == 10


def test_las_dos_estan_categorizadas_en_paridad_proveedores():
    from services.harness_flags import _KEY_CATEGORY

    for key in _LAS_DOS:
        assert _KEY_CATEGORY.get(key) == "paridad_proveedores"


def test_las_dos_tienen_ayuda_llana():
    from services.harness_flags_help import PLAIN_HELP

    topes = {"what": 200, "on_effect": 240, "off_effect": 240, "example": 300}
    for key in _LAS_DOS:
        assert key in PLAIN_HELP, f"{key} sin ayuda llana"
        ayuda = PLAIN_HELP[key]
        for campo, tope in topes.items():
            texto = getattr(ayuda, campo)
            assert texto and texto.strip(), f"{key}.{campo} vacio"
            assert len(texto) >= 10 if campo == "what" else True
            assert len(texto) <= tope, f"{key}.{campo} mide {len(texto)}, tope {tope}"


def test_la_ayuda_llana_respeta_la_denylist():
    """Importa la regla desde el archivo ROJO DE FABRICA. Su conteo (4F/4P) no
    discrimina: si la entrada nueva violara el denylist, el total seguiria en
    4F/4P."""
    from services.harness_flags_help import PLAIN_HELP
    from tests.test_harness_flags_help import JARGON_DENYLIST, _KEY_RE, _PHASE_RE

    for key in _LAS_DOS:
        ayuda = PLAIN_HELP[key]
        for campo in ("what", "on_effect", "off_effect", "example"):
            texto = getattr(ayuda, campo)
            for palabra in JARGON_DENYLIST:
                patron = re.compile(rf"\b{re.escape(palabra)}s?\b", re.IGNORECASE)
                assert not patron.search(texto), f"{key}.{campo} usa jerga: {palabra}"
            assert not _KEY_RE.search(texto), f"{key}.{campo} nombra una variable en mayusculas"
            assert not _PHASE_RE.search(texto), f"{key}.{campo} cita una fase de plan"


def test_la_ayuda_llana_empieza_con_si_sin_tilde():
    from services.harness_flags_help import PLAIN_HELP

    for key in _LAS_DOS:
        ayuda = PLAIN_HELP[key]
        assert ayuda.on_effect.startswith("Si "), f"{key}.on_effect no empieza con 'Si '"
        assert ayuda.off_effect.startswith("Si "), f"{key}.off_effect no empieza con 'Si '"


def test_la_numerica_esta_en_el_mapa_congelado_de_cotas():
    """§4.1-bis. SIN ESTE CASO, olvidarse del sitio 6 es INDETECTABLE: el archivo
    ajeno queda en 1 failed / 17 passed en los tres escenarios posibles (hacerlo
    bien, olvidarlo, hacerlo al reves)."""
    from tests.test_harness_flags_bounds import _FROZEN_BOUNDS

    assert _FROZEN_BOUNDS.get(_NUM) == (1, 1000)


def test_la_booleana_no_esta_en_el_mapa_de_cotas():
    """La MITAD DE CONTRASTE del caso anterior: guarda la PRESENCIA de una y la
    AUSENCIA de la otra en el mismo archivo, para que ninguna de las dos pase por
    accidente."""
    from tests.test_harness_flags_bounds import _FROZEN_BOUNDS

    assert _BOOL not in _FROZEN_BOUNDS
