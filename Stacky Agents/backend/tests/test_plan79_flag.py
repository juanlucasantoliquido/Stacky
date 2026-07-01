"""Plan 79 — F0: flag maestro STACKY_DETERMINISTIC_TASK_STATES_ENABLED.

Verifica: registrado en FLAG_REGISTRY, categorizado en "flujo_funcional",
default OFF, y el lector `deterministic_task_states_enabled()` lee de
Config (no de os.getenv directo) para que la edición por UI surta efecto.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.harness_flags import FLAG_REGISTRY, categorize  # noqa: E402


FLAG_KEY = "STACKY_DETERMINISTIC_TASK_STATES_ENABLED"


def _find_spec():
    for spec in FLAG_REGISTRY:
        if spec.key == FLAG_KEY:
            return spec
    return None


def test_flag_registered_in_registry():
    spec = _find_spec()
    assert spec is not None, f"{FLAG_KEY} no está en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.env_only is False


def test_flag_categorized_in_flujo_funcional():
    assert categorize(FLAG_KEY) == "flujo_funcional"


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(FLAG_KEY, raising=False)
    # Recargar config para reflejar la ausencia de la env var.
    import importlib

    import config as config_module

    importlib.reload(config_module)
    assert config_module.Config.STACKY_DETERMINISTIC_TASK_STATES_ENABLED is False
    importlib.reload(config_module)


def test_reader_reads_from_config_not_env(monkeypatch):
    from config import Config
    from harness.task_states import deterministic_task_states_enabled

    monkeypatch.delenv(FLAG_KEY, raising=False)
    monkeypatch.setattr(Config, "STACKY_DETERMINISTIC_TASK_STATES_ENABLED", True, raising=False)
    assert FLAG_KEY not in os.environ
    assert deterministic_task_states_enabled() is True

    monkeypatch.setattr(Config, "STACKY_DETERMINISTIC_TASK_STATES_ENABLED", False, raising=False)
    assert deterministic_task_states_enabled() is False
