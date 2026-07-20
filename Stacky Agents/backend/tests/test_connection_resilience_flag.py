"""Plan 192 F0 - flag STACKY_CONNECTION_RESILIENCE_ENABLED (registro triple).

G5: este archivo hace importlib.reload(config) y contamina tests flag-off de la
misma sesion pytest. Correr SIEMPRE por archivo (como todo el arnes).
"""
import importlib

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

KEY = "STACKY_CONNECTION_RESILIENCE_ENABLED"


def test_flag_registrada_bool_default_on():
    spec = next((s for s in FLAG_REGISTRY if s.key == KEY), None)
    assert spec is not None, f"{KEY} no esta en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True


def test_flag_categorizada_interfaz_ui():
    assert KEY in _CATEGORY_KEYS["interfaz_ui"]


def test_config_default_efectivo_on(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    import config as config_module
    importlib.reload(config_module)
    assert getattr(config_module.config, KEY) is True
