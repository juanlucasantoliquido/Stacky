"""Plan 256 F5 — alta de las 3 flags en la UI.

Un atributo en `config.py` NO alcanza para que una flag aparezca en el panel: el
panel se alimenta de `FLAG_REGISTRY`. Saltear cualquiera de los cuatro lugares
deja la flag invisible (o el arnes en rojo). Este archivo los cubre a los cuatro
mas la ayuda en lenguaje llano.

Modelado sobre tests/test_plan149_flags.py.
Correr POR ARCHIVO:
    .venv\\Scripts\\python.exe -m pytest tests/test_plan256_flags.py -v
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


_FLAGS_ON = (
    "STACKY_INTAKE_QUARANTINE_SIDECAR_ENABLED",
    "STACKY_INTAKE_PRESERVE_ORIGINAL_ENABLED",
)
_FLAG_OFF = "STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED"
_LAS_3 = _FLAGS_ON + (_FLAG_OFF,)
_CATEGORIA = "fiabilidad_ciclo_vida"

_CONFIG_PY = Path(__file__).resolve().parents[1] / "config.py"


def _specs() -> dict:
    from services.harness_flags import FLAG_REGISTRY

    return {spec.key: spec for spec in FLAG_REGISTRY}


def _default_de_config(key: str) -> str:
    """El default EFECTIVO es el 2do argumento de os.getenv en config.py, no el
    `default=` de la FlagSpec. Se leen del fuente para comparar los dos."""
    fuente = _CONFIG_PY.read_text(encoding="utf-8")
    m = re.search(rf'os\.getenv\(\s*"{re.escape(key)}",\s*"([^"]+)"\s*\)', fuente)
    assert m, f"{key} no tiene atributo con os.getenv en config.py"
    return m.group(1)


def test_las_3_flags_estan_en_el_registry():
    specs = _specs()
    faltan = [k for k in _LAS_3 if k not in specs]
    assert faltan == [], f"flags invisibles en el panel: {faltan}"
    for key in _LAS_3:
        assert specs[key].type == "bool"
        # env_only=False es obligatorio: las 3 SI son atributos de Config.
        assert specs[key].env_only is False, f"{key}: env_only deberia ser False"


def test_las_3_flags_estan_categorizadas():
    from services.harness_flags import categorize

    for key in _LAS_3:
        assert categorize(key) == _CATEGORIA, f"{key} cayo fuera de {_CATEGORIA}"


def test_defaults_declarados_coinciden_con_config():
    """Si el default declarado miente respecto de config.py, el panel muestra un
    estado y el sistema se comporta con el otro.

    OJO con la de descarte: una flag que nace APAGADA NO declara `default=False`.
    `declared_default` cae al type-zero (False) igual, pero `default_is_known`
    tiene que quedar en False o el centinela de defaults curados se pone rojo.
    """
    from services.harness_flags import declared_default, default_is_known

    specs = _specs()
    for key in _FLAGS_ON:
        assert specs[key].default is True
        assert declared_default(specs[key]) is True
        assert default_is_known(specs[key]) is True
        assert _default_de_config(key) == "true"

    off = specs[_FLAG_OFF]
    assert off.default is None, "una flag default-OFF no declara `default=`"
    assert declared_default(off) is False
    assert default_is_known(off) is False
    assert _default_de_config(_FLAG_OFF) == "false"


def test_solo_discard_nace_off():
    """Excepcion dura declarada: accion irreversible desde la UI. Las otras dos
    no son destructivas y nacen encendidas."""
    from config import config

    for key in _FLAGS_ON:
        assert getattr(config, key) is True, f"{key} deberia nacer encendida"
    assert getattr(config, _FLAG_OFF) is False, "el descarte NO puede nacer encendido"


def test_las_3_tienen_ayuda_en_lenguaje_llano():
    """El meta-test del arnes exige cobertura 100% de PLAIN_HELP. Ese archivo
    tiene rojos ajenos preexistentes, asi que la entrada propia se valida aca."""
    from services.harness_flags_help import PLAIN_HELP

    for key in _LAS_3:
        assert key in PLAIN_HELP, f"{key} sin ayuda en lenguaje llano"
        entrada = PLAIN_HELP[key]
        assert entrada.on_effect.startswith("Si ")
        assert entrada.off_effect.startswith("Si ")
        assert 10 <= len(entrada.what) <= 200
        assert len(entrada.on_effect) <= 240
        assert len(entrada.off_effect) <= 240
        assert len(entrada.example) <= 300
