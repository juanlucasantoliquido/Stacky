"""Plan 250 F3 — las DOS flags, cableadas en las 6 patas y editables desde la UI.

Las 6 patas reales (los docs dicen 5; la sexta es harness_flags_help.py):
config.py, FLAG_REGISTRY, _CATEGORY_KEYS, PLAIN_HELP, _CURATED_DEFAULTS_ON y el
/health de DevOps que gatea la seccion del panel.
"""
from __future__ import annotations

import pytest

from services.harness_flags import (
    FLAG_REGISTRY,
    categorize,
    declared_default,
    default_is_known,
    read_current,
    validate_requires_graph,
)
from services.harness_flags_help import PLAIN_HELP

ANALISIS = "STACKY_PIPELINE_NL_EDIT_ENABLED"
COMMIT = "STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED"


def _spec(key: str):
    return next(s for s in FLAG_REGISTRY if s.key == key)


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_las_dos_flags_estan_en_el_catalogo_que_consume_la_ui():
    actuales = {f["key"]: f for f in read_current()}
    for key in (ANALISIS, COMMIT):
        assert key in actuales, "la flag no llega al panel del arnes"
        assert _spec(key).env_only is False, "tiene que ser editable desde la UI"
        assert _spec(key).type == "bool"
        assert _spec(key).label and _spec(key).description
    # y el health de DevOps publica las dos llaves que gatean la seccion
    from api.devops import _health_payload

    payload = _health_payload()
    assert "pipeline_nl_edit_enabled" in payload
    assert "pipeline_nl_edit_commit_enabled" in payload


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_la_flag_que_escribe_no_esta_curada_como_default_on():
    """Contracara de ser default OFF: la unica ruta que pushea al Azure DevOps real
    del operador NO puede venir encendida de fabrica (excepcion dura 2)."""
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert COMMIT not in _CURATED_DEFAULTS_ON
    # y NO declara `default=` en la FlagSpec: declararlo (aun como False) la volveria
    # `default_is_known` y pondria roja a test_default_known_only_for_curated.
    assert _spec(COMMIT).default is None
    assert default_is_known(_spec(COMMIT)) is False
    # el default EFECTIVO vive en config.py y es OFF
    import config as _config

    assert _config.Config().STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED is False
    assert declared_default(_spec(COMMIT)) is False   # type-zero de bool


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_la_flag_de_analisis_si_esta_curada_default_on():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert ANALISIS in _CURATED_DEFAULTS_ON
    assert declared_default(_spec(ANALISIS)) is True
    assert default_is_known(_spec(ANALISIS)) is True


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_las_dos_flags_tienen_categoria_y_ayuda_llana():
    for key in (ANALISIS, COMMIT):
        assert categorize(key) != "otros", "falta la entrada en _CATEGORY_KEYS"
        assert key in PLAIN_HELP, "falta la ayuda para mortales (6a pata)"
        ayuda = PLAIN_HELP[key]
        assert ayuda.on_effect.startswith("Si ")
        assert ayuda.off_effect.startswith("Si ")


def test_el_requires_no_rompe_la_regla_de_profundidad_1():
    assert _spec(COMMIT).requires == ANALISIS
    assert _spec(ANALISIS).requires is None
    assert validate_requires_graph() == []


@pytest.mark.parametrize("key", [ANALISIS, COMMIT])
def test_la_descripcion_dice_que_pasa_con_off(key):
    assert "OFF" in _spec(key).description
