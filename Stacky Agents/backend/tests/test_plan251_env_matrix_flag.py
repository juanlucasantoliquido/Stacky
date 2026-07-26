"""Plan 251 F0 — la flag en sus 7 patas. Sin esto, el resto es un modulo inerte."""
from __future__ import annotations

from services.harness_flags import (
    FLAG_REGISTRY,
    categorize,
    default_is_known,
    read_current,
    validate_requires_graph,
)
from services.harness_flags_help import PLAIN_HELP

KEY = "STACKY_PIPELINE_ENV_MATRIX_ENABLED"


def _spec():
    return next(s for s in FLAG_REGISTRY if s.key == KEY)


def test_f0_flag_en_registry():
    assert _spec().type == "bool"
    assert _spec().env_only is False, "tiene que ser editable desde la UI"
    assert KEY in {f["key"] for f in read_current()}


def test_f0_flag_en_categoria_devops():
    assert categorize(KEY) != "otros", "falta la entrada en _CATEGORY_KEYS"


def test_f0_default_on():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert _spec().default is True
    assert KEY in _CURATED_DEFAULTS_ON
    assert default_is_known(_spec()) is True


def test_f0_config_efectivo_on():
    """C10 — cierra un falso verde REAL: el default EFECTIVO lo manda config.py, no el
    FlagSpec. Con FlagSpec(default=True) y config.py en False los otros tests pasan
    verdes y en produccion el endpoint devuelve 404."""
    import config

    assert getattr(config.config, KEY) is True
    assert config.Config().STACKY_PIPELINE_ENV_MATRIX_ENABLED is True


def test_f0_requires_es_el_master_del_panel():
    """R4 profundidad 1: NUNCA colgar de STACKY_DEVOPS_VARIABLES_ENABLED, que ya
    declara su propio `requires`."""
    assert _spec().requires == "STACKY_DEVOPS_PANEL_ENABLED"
    madre = next(s for s in FLAG_REGISTRY if s.key == "STACKY_DEVOPS_PANEL_ENABLED")
    assert madre.requires is None
    assert validate_requires_graph() == []


def test_f0_plain_help_existe():
    assert KEY in PLAIN_HELP, "6a pata: la ayuda para mortales"
    ayuda = PLAIN_HELP[KEY]
    assert ayuda.on_effect.startswith("Si ") and ayuda.off_effect.startswith("Si ")


def test_f0_registrado_en_las_dos_listas_del_ratchet():
    """7a pata (C7): el meta-test parsea SOLO el .sh, asi que olvidar el .ps1 NO da
    rojo y el runner de dev del operador deja de cubrir 5 archivos en silencio."""
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    sh = (backend / "scripts" / "run_harness_tests.sh").read_text(encoding="utf-8")
    ps1 = (backend / "scripts" / "run_harness_tests.ps1").read_text(encoding="utf-8")
    archivos = ("test_plan251_env_matrix_flag.py", "test_plan251_env_matrix_extract.py",
                "test_plan251_env_matrix_build.py", "test_plan251_env_matrix_resolve.py",
                "test_plan251_env_matrix_endpoints.py")
    for nombre in archivos:
        assert "tests/%s" % nombre in sh, nombre
        assert '"tests/%s"' % nombre in ps1, nombre
