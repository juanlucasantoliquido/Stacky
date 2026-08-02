"""Plan 293 F2 — Las TRES opciones del tablero de trabajo y sus guardianes.

Acotado a estas 3 keys a proposito. Los gates globales de flags
(tests/test_harness_flags*.py) son asserts de CONJUNTO y ademas tienen 5 rojos de
fabrica, asi que "delta cero en el conteo" NO discrimina si me olvide una entrada.
De ahi el caso de discriminacion del final.
"""
from __future__ import annotations

import pytest

from config import config
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

LECTURA = "STACKY_WORKBENCH_ENABLED"
ESCRITURA = "STACKY_WORKBENCH_WRITE_ENABLED"
ENVIO = "STACKY_WORKBENCH_PUSH_ENABLED"
LAS_TRES = (LECTURA, ESCRITURA, ENVIO)

_POR_KEY = {s.key: s for s in FLAG_REGISTRY}


@pytest.mark.parametrize("key", LAS_TRES)
def test_01_esta_en_el_registro(key):
    assert key in _POR_KEY, f"{key} no esta en FLAG_REGISTRY"
    assert _POR_KEY[key].type == "bool"


def test_02_la_de_lectura_nace_encendida():
    """Solo lectura: mira el estado del repo, agrupa y muestra diferencias.
    El riel dice que lo de solo lectura NUNCA es excepcion, asi que va ON."""
    assert _POR_KEY[LECTURA].default is True
    assert config.STACKY_WORKBENCH_ENABLED is True


@pytest.mark.parametrize("key", (ESCRITURA, ENVIO))
def test_03_las_de_escritura_nacen_apagadas(key):
    """Excepcion (B): escriben en un sistema REAL del operador."""
    assert _POR_KEY[key].default is None, (
        f"{key} nace OFF, asi que NO debe declarar default= en su FlagSpec"
    )
    assert getattr(config, key) is False


@pytest.mark.parametrize("key", LAS_TRES)
def test_04_existe_en_config(key):
    assert hasattr(config, key), f"{key} no existe en config.py: la flag queda INERTE"
    assert isinstance(getattr(config, key), bool)


@pytest.mark.parametrize("key", LAS_TRES)
def test_05_no_declaran_requires(key):
    """Sin requires= a proposito: la dependencia entre las tres se resuelve EN
    CODIGO (el semaforo de F4), no en el grafo declarativo."""
    assert _POR_KEY[key].requires is None


@pytest.mark.parametrize("key", LAS_TRES)
def test_06_estan_categorizadas(key):
    todas = {k for keys in _CATEGORY_KEYS.values() for k in keys}
    assert key in todas, f"{key} sin categoria: test_every_registry_flag_is_categorized rompe"


@pytest.mark.parametrize("key", LAS_TRES)
def test_07_tienen_ayuda_llana(key):
    assert key in PLAIN_HELP, f"{key} sin entrada en PLAIN_HELP"


@pytest.mark.parametrize("key", LAS_TRES)
def test_08_la_ayuda_empieza_con_si_sin_tilde(key):
    ayuda = PLAIN_HELP[key]
    assert ayuda.on_effect.startswith("Si "), f"{key}.on_effect debe empezar con 'Si ' SIN tilde"
    assert ayuda.off_effect.startswith("Si "), f"{key}.off_effect debe empezar con 'Si ' SIN tilde"
    assert len(ayuda.on_effect) <= 240
    assert len(ayuda.off_effect) <= 240
    assert 10 <= len(ayuda.what) <= 200
    assert len(ayuda.example) <= 300


@pytest.mark.parametrize("key", LAS_TRES)
def test_09_la_ayuda_no_usa_jerga(key):
    """Las opciones las lee alguien que no sabe git: la ayuda no puede tener jerga."""
    from tests.test_harness_flags_help import JARGON_DENYLIST

    ayuda = PLAIN_HELP[key]
    texto = f"{ayuda.what} {ayuda.on_effect} {ayuda.off_effect} {ayuda.example}".lower()
    encontrados = [j for j in JARGON_DENYLIST if j.lower() in texto]
    assert not encontrados, f"{key} usa jerga prohibida: {encontrados}"


def test_10_curated_defaults_on_contiene_solo_la_de_lectura():
    """_CURATED_DEFAULTS_ON es IGUALDAD EXACTA de conjuntos: la ON tiene que estar
    y las dos OFF NO pueden estar. Cualquiera de los dos errores pone rojo un test
    hoy verde, por razones distintas."""
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert LECTURA in _CURATED_DEFAULTS_ON
    assert ESCRITURA not in _CURATED_DEFAULTS_ON
    assert ENVIO not in _CURATED_DEFAULTS_ON


def test_11_las_dos_ediciones_acopladas_de_la_flag_on():
    """Estar en _CURATED_DEFAULTS_ON y declarar default=True son DOS ediciones.
    Hacer una sola rompe dos tests distintos (test_declared_default_true_set y
    test_default_known_only_for_curated)."""
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert (LECTURA in _CURATED_DEFAULTS_ON) is (_POR_KEY[LECTURA].default is True)


def test_12_caso_de_discriminacion_el_gate_de_ayuda_puede_fallar():
    """Los 4 rojos de fabrica de test_harness_flags_help.py son asserts de CONJUNTO:
    omitir una entrada NO cambia el conteo. Este caso prueba que el gate de ESTE
    plan si discrimina, borrando una entrada y exigiendo que se ponga rojo.

    Molde: tests/test_plan271_flags.py.
    """
    copia = dict(PLAIN_HELP)
    copia.pop(ESCRITURA)
    faltantes = [k for k in LAS_TRES if k not in copia]
    assert faltantes == [ESCRITURA], (
        "el gate de ayuda llana no discrimina: al borrar una entrada deberia detectarlo"
    )
