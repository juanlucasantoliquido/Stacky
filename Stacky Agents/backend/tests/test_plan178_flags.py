"""Plan 178 F0 — Flags del radar de ambientes (registro, defaults, bounds, categoría).

Ver Stacky Agents/docs/178_PLAN_RADAR_DE_AMBIENTES_...md §F0.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS


def _spec(key: str):
    for s in FLAG_REGISTRY:
        if s.key == key:
            return s
    return None


def test_radar_flag_registrada_bool_default_on():
    spec = _spec("STACKY_DB_COMPARE_RADAR_ENABLED")
    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == "STACKY_DB_COMPARE_ENABLED"


def test_flags_int_sin_default_con_bounds():
    interval = _spec("STACKY_DB_COMPARE_WATCH_INTERVAL_MIN")
    budget = _spec("STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY")
    assert interval is not None and budget is not None
    assert interval.type == "int" and budget.type == "int"
    # NO default= en int (gotcha _CURATED_DEFAULTS_ON): quedan None.
    assert interval.default is None
    assert budget.default is None
    assert (interval.min_value, interval.max_value) == (5, 1440)
    assert (budget.min_value, budget.max_value) == (1, 100)
    assert interval.requires == "STACKY_DB_COMPARE_ENABLED"
    assert budget.requires == "STACKY_DB_COMPARE_ENABLED"


def test_flags_en_categoria_comparador_bd():
    keys = _CATEGORY_KEYS["comparador_bd"]
    assert "STACKY_DB_COMPARE_RADAR_ENABLED" in keys
    assert "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN" in keys
    assert "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY" in keys


def test_config_attrs_existen_con_tipo():
    # Determinista (fix C10): solo verifica tipos, no valores dependientes del env.
    import config as _config

    assert isinstance(_config.config.STACKY_DB_COMPARE_RADAR_ENABLED, bool)
    assert isinstance(_config.config.STACKY_DB_COMPARE_WATCH_INTERVAL_MIN, int)
    assert isinstance(_config.config.STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY, int)
