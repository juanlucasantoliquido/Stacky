"""Plan 260 F0 — tres flags, en sus 7 patas.

STACKY_PIPELINE_ENV_DECLARE_ENABLED (OFF, EXCEPCION DURA B: escribe en el
proveedor real del operador) + STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED (ON,
solo lee) + STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED (ON, solo puede
impedir una fuga). Ninguna de las dos ON dispara las excepciones duras: no hay
loop/daemon/polling (corren a pedido dentro de un request) y no escriben nada.
"""
import os

import pytest

KEY_DECLARE = "STACKY_PIPELINE_ENV_DECLARE_ENABLED"
KEY_TRIGGER_GATE = "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED"
KEY_SECRET_GATE = "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED"
KEYS = (KEY_DECLARE, KEY_TRIGGER_GATE, KEY_SECRET_GATE)


def test_f0_tres_flags_en_registry():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in KEYS:
        assert key in by_key, f"{key} no esta en FLAG_REGISTRY"
        assert by_key[key].type == "bool"
        assert by_key[key].env_only is False, f"{key} debe ser editable por UI"


def test_f0_tres_flags_en_categoria_devops():
    from services.harness_flags import _CATEGORY_KEYS

    for key in KEYS:
        assert key in _CATEGORY_KEYS["devops"], f"{key} no esta en _CATEGORY_KEYS['devops']"


def test_f0_defaults():
    from services.harness_flags import FLAG_REGISTRY, default_is_known
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    by_key = {s.key: s for s in FLAG_REGISTRY}

    # Las dos ON: default declarado True Y presentes en el conjunto curado.
    for key in (KEY_TRIGGER_GATE, KEY_SECRET_GATE):
        spec = by_key[key]
        assert spec.default is True, f"{key} debe declarar default=True"
        assert default_is_known(spec) is True
        assert key in _CURATED_DEFAULTS_ON, f"{key} debe estar en _CURATED_DEFAULTS_ON"

    # La OFF: SIN default declarado (spec.default is None) y AUSENTE del curado.
    spec_declare = by_key[KEY_DECLARE]
    assert spec_declare.default is None, (
        f"{KEY_DECLARE} no debe declarar default= (el default EFECTIVO vive en config.py)"
    )
    assert default_is_known(spec_declare) is False
    assert KEY_DECLARE not in _CURATED_DEFAULTS_ON


def test_f0_config_efectivo():
    """El default EFECTIVO lo decide config.py, no la FlagSpec — el falso verde real."""
    for key in KEYS:
        assert os.getenv(key) is None, (
            f"{key} esta seteada en el entorno de test: este caso mide el DEFAULT"
        )

    import config

    assert getattr(config.config, KEY_DECLARE) is False
    assert getattr(config.config, KEY_TRIGGER_GATE) is True
    assert getattr(config.config, KEY_SECRET_GATE) is True


def test_f0_requires_profundidad_1():
    """Ninguna de las 3 apunta a una flag que a su vez declare requires (R4)."""
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in KEYS:
        spec = by_key[key]
        assert spec.requires is not None, f"{key} debe declarar requires"
        master = by_key[spec.requires]
        assert master.requires is None, (
            f"{key}.requires={spec.requires!r} ya declara requires: cadena prohibida"
        )

    assert by_key[KEY_DECLARE].requires == "STACKY_DEVOPS_PANEL_ENABLED"
    assert by_key[KEY_TRIGGER_GATE].requires == "STACKY_PIPELINE_TRIGGER_ENABLED"
    assert by_key[KEY_SECRET_GATE].requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_f0_plain_help_existe_y_entra_en_240():
    from services.harness_flags_help import PLAIN_HELP

    for key in KEYS:
        assert key in PLAIN_HELP, f"{key} sin ayuda en lenguaje llano"
        help_ = PLAIN_HELP[key]
        assert help_.what and help_.on_effect and help_.off_effect and help_.example
        assert len(help_.what) <= 200
        assert len(help_.on_effect) <= 240
        assert len(help_.off_effect) <= 240
        assert len(help_.example) <= 300
        assert help_.on_effect.startswith("Si ")
        assert help_.off_effect.startswith("Si ")
