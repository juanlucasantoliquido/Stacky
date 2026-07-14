"""Plan 126 F0 — Flags de paridad de DATOS del Comparador de BD (hijas del
master STACKY_DB_COMPARE_ENABLED, Plan 122).

Ver Stacky Agents/docs/126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md #F0.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_data_diff_enabled_flag_declared_default_off():
    from services.harness_flags import FLAG_REGISTRY
    from config import Config

    by_key = {s.key: s for s in FLAG_REGISTRY}
    spec = by_key["STACKY_DB_COMPARE_DATA_DIFF_ENABLED"]
    assert spec.type == "bool"
    assert spec.requires == "STACKY_DB_COMPARE_ENABLED"
    assert Config.STACKY_DB_COMPARE_DATA_DIFF_ENABLED is False


def test_data_max_rows_flag_bounds_sin_default_curado():
    from services.harness_flags import FLAG_REGISTRY
    from config import Config

    by_key = {s.key: s for s in FLAG_REGISTRY}
    spec = by_key["STACKY_DB_COMPARE_DATA_MAX_ROWS"]
    assert spec.type == "int"
    assert spec.min_value == 100
    assert spec.max_value == 200000
    assert spec.requires == "STACKY_DB_COMPARE_ENABLED"
    # [FIX C2] spec.default se deja en None a propósito: default_is_known() trata
    # cualquier default no-None (bool o numérico) como "curado" y exige alta en
    # _CURATED_DEFAULTS_ON, set reservado a promociones bool=True. El valor
    # sugerido "5000" vive solo en config.py, no en spec.default.
    assert spec.default is None
    assert Config.STACKY_DB_COMPARE_DATA_MAX_ROWS == 5000


def test_ambas_flags_requires_master_exacto():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in ("STACKY_DB_COMPARE_DATA_DIFF_ENABLED", "STACKY_DB_COMPARE_DATA_MAX_ROWS"):
        assert by_key[key].requires == "STACKY_DB_COMPARE_ENABLED", key


def test_categoria_comparador_bd_incluye_las_2_keys_nuevas():
    from services.harness_flags import _CATEGORY_KEYS

    cat = _CATEGORY_KEYS["comparador_bd"]
    assert "STACKY_DB_COMPARE_DATA_DIFF_ENABLED" in cat
    assert "STACKY_DB_COMPARE_DATA_MAX_ROWS" in cat
    # [FIX C7] la tupla existente del 122 (timeout) sigue presente: se EXTIENDE,
    # no se reemplaza.
    assert "STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC" in cat


def test_requires_map_frozen_incluye_las_2_aristas_nuevas():
    """[FIX C1] Ambas FlagSpec con requires deben estar en _REQUIRES_MAP_FROZEN."""
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

    assert _REQUIRES_MAP_FROZEN.get("STACKY_DB_COMPARE_DATA_DIFF_ENABLED") == "STACKY_DB_COMPARE_ENABLED"
    assert _REQUIRES_MAP_FROZEN.get("STACKY_DB_COMPARE_DATA_MAX_ROWS") == "STACKY_DB_COMPARE_ENABLED"
