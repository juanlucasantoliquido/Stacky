"""tests/test_plan296_flags.py - Plan 296 F0.

Las 2 flags del copiloto conversacional del perfil de cliente y sus guardianes.

POR QUE ESTE ARCHIVO IMPORTA REGLAS DE OTROS ARCHIVOS EN VEZ DE CONFIAR EN SU
CONTEO: dos de los guardianes viven en suites ROJAS DE FABRICA
(`test_harness_flags_help.py` 4F/4P). Un conteo sobre un archivo ya rojo NO
DISCRIMINA. Por eso las reglas ajenas se traen a este archivo VERDE, donde si
discriminan. Patron ya usado en tests/test_plan294_flags.py:5-10.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_ON = "STACKY_PROFILE_COPILOT_ENABLED"
_OFF = "STACKY_PROFILE_COPILOT_APPLY_ENABLED"
_AMBAS = (_ON, _OFF)


def _spec(key):
    from services.harness_flags import FLAG_REGISTRY

    coincidencias = [s for s in FLAG_REGISTRY if s.key == key]
    assert len(coincidencias) == 1, f"{key}: se esperaba 1 spec, hay {len(coincidencias)}"
    return coincidencias[0]


def test_flag_conversacional_nace_on():
    """Conversa, detecta faltantes, recomienda y MUESTRA el diff. No escribe."""
    import config as _config_mod

    assert getattr(_config_mod.config, _ON) is True


def test_flag_apply_nace_off():
    """Causal (B): escribe projects/<NAME>/config.json, la config real del operador."""
    import config as _config_mod

    assert getattr(_config_mod.config, _OFF) is False


def test_ambas_flags_estan_en_el_registry():
    from services.harness_flags import FLAG_REGISTRY

    presentes = [s.key for s in FLAG_REGISTRY]
    for key in _AMBAS:
        assert key in presentes, f"{key} no esta en FLAG_REGISTRY"
        assert presentes.count(key) == 1, f"{key} duplicada en FLAG_REGISTRY"


def test_apply_no_declara_default():
    """`default_is_known(spec)` es literalmente `spec.default is not None`:
    declarar `default=False` la meteria en el conjunto que
    test_default_known_only_for_curated exige que sea EXACTAMENTE
    _CURATED_DEFAULTS_ON, donde una OFF no entra. El OFF vive SOLO en config.py."""
    from services.harness_flags import default_is_known
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    spec = _spec(_OFF)
    assert spec.default is None, f"{_OFF} declara default={spec.default!r} y no debe"
    assert default_is_known(spec) is False
    assert _OFF not in _CURATED_DEFAULTS_ON


def test_conversacional_declara_default_true():
    from services.harness_flags import default_is_known
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    spec = _spec(_ON)
    assert spec.default is True, f"{_ON}.default = {spec.default!r}, se esperaba True"
    assert default_is_known(spec) is True
    assert _ON in _CURATED_DEFAULTS_ON, (
        f"{_ON} tiene default=True pero NO esta en _CURATED_DEFAULTS_ON: "
        f"test_default_known_only_for_curated compara CONJUNTOS y quedaria rojo."
    )


def test_apply_requiere_al_master():
    assert _spec(_OFF).requires == _ON
    assert _spec(_ON).requires is None, "R4: la madre no declara requires"


def test_ambas_son_editables_por_ui():
    """Riel duro de la casa: toda flag/config del operador va por UI."""
    for key in _AMBAS:
        assert _spec(key).env_only is False, f"{key} es env_only y no debe serlo"


def test_ambas_tienen_categoria():
    from services.harness_flags import _CATEGORY_KEYS, _KEY_CATEGORY

    encontradas = {
        key: [cat for cat, keys in _CATEGORY_KEYS.items() if key in keys]
        for key in _AMBAS
    }
    for key, cats in encontradas.items():
        assert len(cats) == 1, (
            f"{key} debe estar en EXACTAMENTE una tupla de _CATEGORY_KEYS; "
            f"categorias encontradas: {cats}"
        )
    assert _KEY_CATEGORY.get(_ON) == "flujo_funcional", (
        f"{_ON} categorizada como {_KEY_CATEGORY.get(_ON)!r}"
    )
    assert _KEY_CATEGORY.get(_OFF) == "capacidades_optin", (
        f"{_OFF} categorizada como {_KEY_CATEGORY.get(_OFF)!r}"
    )


def test_ambas_tienen_ayuda_llana():
    from services.harness_flags_help import PLAIN_HELP

    for key in _AMBAS:
        assert key in PLAIN_HELP, f"{key} sin ayuda llana en PLAIN_HELP"
        ayuda = PLAIN_HELP[key]
        for campo in ("what", "on_effect", "off_effect", "example"):
            texto = getattr(ayuda, campo)
            assert texto and texto.strip(), f"{key}.{campo} vacio"
        # El gate de la casa exige "Si " SIN TILDE.
        assert ayuda.on_effect.startswith("Si "), f"{key}.on_effect no empieza con 'Si '"
        assert ayuda.off_effect.startswith("Si "), f"{key}.off_effect no empieza con 'Si '"


def test_apply_esta_en_el_mapa_requires_congelado():
    """C3 - test_requires_map_is_frozen compara con `==`: declarar requires SIN
    registrarlo en el mapa congelado deja test_harness_flags_requires.py ROJO
    desde el commit que crea la FlagSpec."""
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

    real = _REQUIRES_MAP_FROZEN.get(_OFF)
    assert real == _ON, (
        f"_REQUIRES_MAP_FROZEN[{_OFF!r}] = {real!r}, se esperaba {_ON!r}. "
        f"test_requires_map_is_frozen daria Extras: ['{_OFF}']"
    )
