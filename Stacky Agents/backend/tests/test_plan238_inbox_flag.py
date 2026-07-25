"""tests/test_plan238_inbox_flag.py -- Plan 238 F0: flag STACKY_INCIDENT_INBOX_ENABLED.

Este archivo hace importlib.reload(config) y contamina tests flag-off de la
misma sesion pytest. Correr SIEMPRE por archivo (como todo el arnes).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS  # noqa: E402

KEY = "STACKY_INCIDENT_INBOX_ENABLED"


def test_flag_registrada_bool_default_on():
    spec = next((s for s in FLAG_REGISTRY if s.key == KEY), None)
    assert spec is not None, f"{KEY} no esta en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True


def test_flag_categorizada_interfaz_ui():
    assert KEY in _CATEGORY_KEYS["interfaz_ui"]


def test_flag_tiene_ayuda_llana():
    """C1 v2: sin esto, test_harness_flags_help se pone rojo por culpa de este plan."""
    from services.harness_flags_help import PLAIN_HELP
    assert KEY in PLAIN_HELP
    entry = PLAIN_HELP[KEY]
    assert entry.on_effect.startswith("Si ")
    assert entry.off_effect.startswith("Si ")
    assert 10 <= len(entry.what.strip()) <= 200


def test_config_default_efectivo_on(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    import config as config_module
    importlib.reload(config_module)
    assert getattr(config_module.config, KEY) is True


def test_config_env_off_apaga(monkeypatch):
    monkeypatch.setenv(KEY, "false")
    import config as config_module
    importlib.reload(config_module)
    assert getattr(config_module.config, KEY) is False
