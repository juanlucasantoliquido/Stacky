"""Plan 133 F0 — Las 5 flags nuevas del contrato de inyección de contexto.

Patrón triple (Plan 127): FlagSpec default=True + _CURATED_DEFAULTS_ON +
config.py default "true". Este archivo verifica las 3 patas para las 5 flags
nuevas y, en F7, las 2 promociones existentes.
"""
from __future__ import annotations

import importlib

import pytest

_NEW_FLAGS = [
    "STACKY_RUN_TICKET_REFRESH_ENABLED",
    "STACKY_BUSINESS_PREFLIGHT_ENABLED",
    "STACKY_ADO_BLOCKER_BLOCK_ENABLED",
    "STACKY_RUN_DIRECTIVE_ENABLED",
    "STACKY_REQUIRED_BLOCKS_ENABLED",
]

# F7 — promociones a default ON.
_PROMOTED_FLAGS = [
    "STACKY_CONTEXT_DEDUP_ENABLED",
    "STACKY_RUN_PREFLIGHT_GATE_ENABLED",
]


@pytest.mark.parametrize("flag_key", _NEW_FLAGS)
def test_las_cinco_flags_existen_en_registry_con_default_true(flag_key):
    from services.harness_flags import FLAG_REGISTRY, declared_default

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert flag_key in by_key, f"{flag_key} no está en FLAG_REGISTRY"
    assert declared_default(by_key[flag_key]) is True, f"{flag_key}: default debe ser True"


@pytest.mark.parametrize("flag_key", _NEW_FLAGS)
def test_las_cinco_flags_tienen_config_attr_default_true(flag_key, monkeypatch):
    monkeypatch.delenv(flag_key, raising=False)
    import config as config_module

    importlib.reload(config_module)
    try:
        assert getattr(config_module.config, flag_key) is True, (
            f"{flag_key}: config attr debe ser True sin env"
        )
    finally:
        importlib.reload(config_module)


@pytest.mark.parametrize("flag_key", _NEW_FLAGS)
def test_flag_off_por_env(flag_key, monkeypatch):
    monkeypatch.setenv(flag_key, "false")
    import config as config_module

    importlib.reload(config_module)
    try:
        assert getattr(config_module.config, flag_key) is False, (
            f"{flag_key}: env 'false' debe apagar el atributo"
        )
    finally:
        monkeypatch.delenv(flag_key, raising=False)
        importlib.reload(config_module)


@pytest.mark.parametrize("flag_key", _NEW_FLAGS + _PROMOTED_FLAGS)
def test_flags_en_curated_defaults_on(flag_key):
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert flag_key in _CURATED_DEFAULTS_ON, f"{flag_key} falta en _CURATED_DEFAULTS_ON"


def test_dedup_flag_default_on():
    """F7 — STACKY_CONTEXT_DEDUP_ENABLED ya estaba en 'true' (verificado, config.py)."""
    import config as config_module

    assert config_module.config.STACKY_CONTEXT_DEDUP_ENABLED is True


def test_run_preflight_gate_default_on():
    """F7 — promoción explícita del gate de precondiciones G0.1 a default ON."""
    import importlib as _importlib

    import config as config_module

    _importlib.reload(config_module)
    assert config_module.config.STACKY_RUN_PREFLIGHT_GATE_ENABLED is True
