"""Plan 257 F5 — alta REAL de las 9 entradas de configuracion en la interfaz.

El atributo en `config.py` NO basta: el panel de configuracion no lee
`config.py`, lee `FLAG_REGISTRY` de `services/harness_flags.py`. Faltarle uno
de los lugares del cableado pone un archivo del arnes en rojo.

`LOG_LEVEL` NO entra en esta tabla: va por `api/global_config.py` (C14), y su
guardia vive en tests/test_plan257_log_level_ui.py.

Correr POR ARCHIVO:
    .venv\\Scripts\\python.exe -m pytest tests/test_plan257_flags.py -v
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# Las 9 entradas del plan: 8 flags de comportamiento + la de retencion, que
# reemplaza a la constante congelada del modulo de logging.
_KEYS_257 = (
    "STACKY_LOG_THROTTLE_ENABLED",
    "STACKY_LOG_THROTTLE_WINDOW_S",
    "STACKY_LOG_THROTTLE_MAX_SIGNATURES",
    "STACKY_LOG_THROTTLE_FLUSH_S",
    "STACKY_LOG_SIZE_ROTATION_ENABLED",
    "STACKY_LOG_MAX_BYTES",
    "STACKY_LOG_MAX_PARTS_PER_DAY",
    "STACKY_LOG_RETENTION_DAYS",
    "STACKY_UI_LOG_NOISE_CARD_ENABLED",
)

_DEFAULTS_ON_257 = {
    "STACKY_LOG_THROTTLE_ENABLED",
    "STACKY_LOG_SIZE_ROTATION_ENABLED",
    "STACKY_UI_LOG_NOISE_CARD_ENABLED",
}

# Las 3 que se consumen UNA sola vez en el arranque (install_throttle_filter y
# el constructor del filtro): un cambio por interfaz persiste pero no aplica
# hasta reiniciar, y la interfaz tiene que decirlo.
_RESTART_257 = {
    "STACKY_LOG_THROTTLE_ENABLED",
    "STACKY_LOG_THROTTLE_WINDOW_S",
    "STACKY_LOG_THROTTLE_MAX_SIGNATURES",
}

_REQUIRES_257 = {
    "STACKY_LOG_THROTTLE_WINDOW_S": "STACKY_LOG_THROTTLE_ENABLED",
    "STACKY_LOG_THROTTLE_MAX_SIGNATURES": "STACKY_LOG_THROTTLE_ENABLED",
    "STACKY_LOG_THROTTLE_FLUSH_S": "STACKY_LOG_THROTTLE_ENABLED",
    "STACKY_LOG_MAX_BYTES": "STACKY_LOG_SIZE_ROTATION_ENABLED",
    "STACKY_LOG_MAX_PARTS_PER_DAY": "STACKY_LOG_SIZE_ROTATION_ENABLED",
}

_CATEGORIA_257 = {k: "observabilidad_notif" for k in _KEYS_257}
_CATEGORIA_257["STACKY_UI_LOG_NOISE_CARD_ENABLED"] = "interfaz_ui"


def _index():
    from services.harness_flags import _REGISTRY_INDEX

    return _REGISTRY_INDEX


def test_las_9_keys_estan_en_el_registry():
    faltan = [k for k in _KEYS_257 if k not in _index()]
    assert faltan == [], f"keys sin FlagSpec: {faltan}"


def test_las_9_keys_estan_categorizadas():
    from services.harness_flags import categorize

    mal = {k: categorize(k) for k in _KEYS_257 if categorize(k) != _CATEGORIA_257[k]}
    assert mal == {}, f"categorias equivocadas (o 'otros'): {mal}"


def test_defaults_on_estan_curados():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    idx = _index()
    declaradas = {k for k in _KEYS_257 if idx[k].default is True}
    assert declaradas == _DEFAULTS_ON_257
    assert _DEFAULTS_ON_257 <= set(_CURATED_DEFAULTS_ON)
    # Las numericas NO declaran default (default_is_known se volveria True y
    # rompe test_default_known_only_for_curated).
    for key in set(_KEYS_257) - _DEFAULTS_ON_257:
        assert idx[key].default is None, f"{key}: no debe declarar default"


def test_las_9_keys_tienen_plain_help():
    from services.harness_flags_help import PLAIN_HELP
    from tests.test_harness_flags_help import JARGON_DENYLIST

    faltan = [k for k in _KEYS_257 if k not in PLAIN_HELP]
    assert faltan == [], f"keys sin ayuda en lenguaje llano: {faltan}"

    violaciones: list[str] = []
    for key in _KEYS_257:
        entrada = PLAIN_HELP[key]
        assert entrada.on_effect.startswith("Si "), f"{key}: on_effect no empieza con 'Si '"
        assert entrada.off_effect.startswith("Si "), f"{key}: off_effect no empieza con 'Si '"
        for campo in (entrada.what, entrada.on_effect, entrada.off_effect, entrada.example):
            for term in JARGON_DENYLIST:
                if re.search(rf"\b{re.escape(term)}s?\b", campo, re.IGNORECASE):
                    violaciones.append(f"{key}: '{term}'")
    assert violaciones == [], f"jerga prohibida: {violaciones}"


def test_requires_apunta_a_su_master_y_es_profundidad_1():
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

    idx = _index()
    for hija, master in _REQUIRES_257.items():
        assert idx[hija].requires == master, f"{hija}: requires equivocado"
        # R4 — profundidad 1: el master NO declara requires a su vez.
        assert idx[master].requires is None, f"{master}: cadena prohibida"
        assert idx[master].type == "bool"
        assert _REQUIRES_MAP_FROZEN.get(hija) == master, f"{hija}: falta en el mapa congelado"


def test_bounds_declarados_estan_congelados():
    from tests.test_harness_flags_bounds import _FROZEN_BOUNDS

    idx = _index()
    for key in _KEYS_257:
        spec = idx[key]
        if spec.min_value is None and spec.max_value is None:
            continue
        assert _FROZEN_BOUNDS.get(key) == (spec.min_value, spec.max_value), (
            f"{key}: bounds no congelados"
        )


def test_config_tiene_los_9_atributos():
    from config import config

    faltan = [k for k in _KEYS_257 if not hasattr(config, k)]
    assert faltan == [], f"atributos ausentes en la configuracion: {faltan}"


def test_restart_required_declarado_donde_corresponde():
    idx = _index()
    declaradas = {k for k in _KEYS_257 if idx[k].restart_required}
    assert declaradas == _RESTART_257
