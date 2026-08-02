"""tests/test_plan294_flags.py — Plan 294 F1.

Las 3 flags del wizard guiado y sus guardianes.

POR QUE ESTE ARCHIVO IMPORTA REGLAS DE OTROS ARCHIVOS EN VEZ DE CONFIAR EN SU
CONTEO: dos de los guardianes viven en suites ROJAS DE FABRICA
(`test_harness_flags_help.py` 4F/4P y `test_harness_flags_bounds.py` 1F/17P). Un
conteo sobre un archivo ya rojo NO DISCRIMINA. Por eso las reglas ajenas se traen
a este archivo VERDE, donde si discriminan. Patron ya usado en
tests/test_plan292_flags.py:11-12.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

_ON = "STACKY_PIPELINE_WIZARD_ENABLED"
_OFF_COMMIT = "STACKY_PIPELINE_WIZARD_COMMIT_ENABLED"
_OFF_VARS = "STACKY_PIPELINE_TRIGGER_VARS_ENABLED"
_LAS_TRES = (_ON, _OFF_COMMIT, _OFF_VARS)


def _spec(key):
    from services.harness_flags import FLAG_REGISTRY

    coincidencias = [s for s in FLAG_REGISTRY if s.key == key]
    assert len(coincidencias) == 1, f"{key}: se esperaba 1 spec, hay {len(coincidencias)}"
    return coincidencias[0]


def test_las_tres_keys_estan_en_el_registro():
    from services.harness_flags import FLAG_REGISTRY

    presentes = [s.key for s in FLAG_REGISTRY]
    for key in _LAS_TRES:
        assert key in presentes, f"{key} no esta en FLAG_REGISTRY"
        assert presentes.count(key) == 1, f"{key} duplicada en FLAG_REGISTRY"


def test_el_wizard_nace_encendido():
    import config as _config_mod

    assert getattr(_config_mod.config, _ON) is True


def test_las_dos_que_escriben_nacen_apagadas():
    """Excepcion dura (B): una escribe en el repositorio real, la otra manda
    variables a una corrida real del CI del operador."""
    import config as _config_mod

    assert getattr(_config_mod.config, _OFF_COMMIT) is False
    assert getattr(_config_mod.config, _OFF_VARS) is False


def test_solo_la_que_nace_on_declara_default():
    """`default_is_known(spec)` es literalmente `spec.default is not None`:
    declarar `default=` en una OFF la meteria en el conjunto que
    test_default_known_only_for_curated exige que sea EXACTAMENTE
    _CURATED_DEFAULTS_ON, donde una OFF no entra. El OFF vive SOLO en config.py."""
    from services.harness_flags import default_is_known
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert default_is_known(_spec(_ON)) is True
    assert _ON in _CURATED_DEFAULTS_ON

    for key in (_OFF_COMMIT, _OFF_VARS):
        spec = _spec(key)
        assert spec.default is None, f"{key} declara default= y no debe"
        assert default_is_known(spec) is False
        assert key not in _CURATED_DEFAULTS_ON


def test_las_tres_estan_categorizadas_en_devops():
    from services.harness_flags import _KEY_CATEGORY

    for key in _LAS_TRES:
        assert _KEY_CATEGORY.get(key) == "devops", (
            f"{key} sin categoria devops; test_every_registry_flag_is_categorized "
            f"se pondria rojo"
        )


def test_las_tres_tienen_ayuda_llana_que_empieza_con_si_sin_tilde():
    from services.harness_flags_help import PLAIN_HELP

    for key in _LAS_TRES:
        assert key in PLAIN_HELP, f"{key} sin ayuda llana"
        ayuda = PLAIN_HELP[key]
        for campo in ("what", "on_effect", "off_effect", "example"):
            texto = getattr(ayuda, campo)
            assert texto and texto.strip(), f"{key}.{campo} vacio"
        assert ayuda.on_effect.startswith("Si "), f"{key}.on_effect no empieza con 'Si '"
        assert ayuda.off_effect.startswith("Si "), f"{key}.off_effect no empieza con 'Si '"


def test_las_dos_que_escriben_declaran_su_madre():
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

    assert _spec(_OFF_COMMIT).requires == _ON
    assert _spec(_OFF_VARS).requires == "STACKY_PIPELINE_TRIGGER_ENABLED"
    assert _spec(_ON).requires is None, "R4: la madre no declara requires"

    # test_requires_map_is_frozen compara con == : declarar requires SIN
    # registrarlo en el mapa congelado deja ese archivo rojo desde el commit.
    assert _REQUIRES_MAP_FROZEN.get(_OFF_COMMIT) == _ON
    assert _REQUIRES_MAP_FROZEN.get(_OFF_VARS) == "STACKY_PIPELINE_TRIGGER_ENABLED"


def test_health_payload_expone_las_tres_y_no_pierde_las_de_antes():
    """C6/C15 — es lo que cablea las 3 flags desde F1 y lo que la UI lee para
    decidir que habilitar (healthKey de la seccion nueva)."""
    from api.devops import _health_payload

    payload = _health_payload()
    for clave in (
        "pipeline_wizard_enabled",
        "pipeline_wizard_commit_enabled",
        "pipeline_trigger_vars_enabled",
    ):
        assert clave in payload, f"_health_payload no expone {clave}"

    # no-regresion del payload: las de antes siguen con el MISMO nombre
    for clave in ("trigger_enabled", "generator_enabled", "pipeline_inventory_enabled"):
        assert clave in payload, f"_health_payload perdio {clave}"


def test_las_tres_aparecen_como_literal_en_codigo_productivo():
    """C6 — es exactamente la condicion que evalua `_production_corpus()` de
    test_flag_wiring.py:30-53: la key debe aparecer como LITERAL en algun archivo
    de backend/ que no sea tests/, services/harness_flags.py ni
    services/harness_flags_help.py.

    NOTA HONESTA sobre el alcance de este caso: config.py entra en ese corpus, asi
    que este caso solo prueba que la flag NO nacio inerte. Quien vigila el
    `_health_payload` en particular es el caso anterior.
    """
    corpus: list[str] = []
    for path in sorted(_BACKEND.rglob("*.py")):
        rel = path.relative_to(_BACKEND).as_posix()
        if rel.startswith("tests/") or rel in (
            "services/harness_flags.py",
            "services/harness_flags_help.py",
        ):
            continue
        corpus.append(path.read_text(encoding="utf-8", errors="ignore"))
    texto = "\n".join(corpus)

    muertas = [k for k in _LAS_TRES if k not in texto]
    assert muertas == [], (
        f"flags registradas SIN consumidor en codigo productivo: {muertas}. "
        f"test_flag_wiring.py::test_every_non_reserved_flag_is_wired las marcaria."
    )
