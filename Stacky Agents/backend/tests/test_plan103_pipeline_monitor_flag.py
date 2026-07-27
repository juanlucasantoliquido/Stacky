"""Plan 103 F0 — flag STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED (6 patas, default ON).

El monitor vivo del ultimo pipeline es solo-lectura: no dispara nada, no escribe en
ningun sistema del operador y no gasta tokens de LLM. Ninguna de las 4 excepciones
duras aplica, asi que va default ON.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = "STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED"


def test_flag_registrada_en_el_registro():
    from services.harness_flags import FLAG_REGISTRY

    spec = next((s for s in FLAG_REGISTRY if s.key == KEY), None)
    assert spec is not None, f"{KEY} no esta en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.env_only is False, "debe ser editable por UI (Configuracion -> Arnes)"


def test_flag_categorizada_en_devops():
    """Una flag sin categoria no aparece en el panel de la UI."""
    from services.harness_flags import _CATEGORY_KEYS

    assert KEY in _CATEGORY_KEYS["devops"]


def test_requires_declara_el_panel_devops():
    from services.harness_flags import FLAG_REGISTRY

    spec = next(s for s in FLAG_REGISTRY if s.key == KEY)
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_default_on_efectivo_en_config():
    """El default EFECTIVO lo decide config.py, no la FlagSpec.

    Sin la variable de entorno seteada, el atributo tiene que nacer en True.
    """
    from services.harness_flags import FLAG_REGISTRY

    spec = next(s for s in FLAG_REGISTRY if s.key == KEY)
    assert spec.default is True, "la FlagSpec debe espejar el default de config.py"

    assert os.getenv(KEY) is None, (
        f"{KEY} esta seteada en el entorno de test: este caso mide el DEFAULT"
    )
    import config

    assert getattr(config.config, KEY) is True


def test_health_expone_la_key():
    """El frontend gatea el badge por esta key del health del panel."""
    import config
    from api.devops import _health_payload

    if not getattr(config.config, KEY):
        pytest.skip("flag apagada por entorno")
    payload = _health_payload()
    assert payload["pipeline_monitor_enabled"] is True


def test_ayuda_en_llano_registrada():
    """Sexta pata: sin PlainHelp la flag queda sin explicacion en la UI."""
    from services.harness_flags_help import PLAIN_HELP

    assert KEY in PLAIN_HELP
    help_ = PLAIN_HELP[KEY]
    assert help_.what and help_.on_effect and help_.off_effect and help_.example
