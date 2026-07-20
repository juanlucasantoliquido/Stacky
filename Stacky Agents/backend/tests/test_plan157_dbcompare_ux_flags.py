"""Plan 157 F0 — Flags del arnés del Comparador de BD UX (config en contexto,
import web.config, panel de migración). 3 flags bool default ON bajo el master 122.

Ver Stacky Agents/docs/157_PLAN_DB_COMPARE_CONFIG_IN_PLACE_WEBCONFIG_IMPORT_Y_PANEL_MIGRACION.md
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_KEYS = (
    "STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED",
    "STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED",
    "STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED",
)


def _by_key():
    from services.harness_flags import FLAG_REGISTRY

    return {s.key: s for s in FLAG_REGISTRY}


def test_las_tres_flags_existen_en_registry():
    by_key = _by_key()
    for k in _KEYS:
        assert k in by_key, f"{k} falta en FLAG_REGISTRY"


def test_las_tres_flags_default_on():
    # `flag_default` no existe en el módulo; el invariante equivalente y real es
    # declared_default(spec) is True (spec.default explícito True).
    from services.harness_flags import declared_default

    by_key = _by_key()
    for k in _KEYS:
        assert declared_default(by_key[k]) is True, f"{k}: default debe ser True"


def test_las_tres_flags_son_bool():
    by_key = _by_key()
    for k in _KEYS:
        assert by_key[k].type == "bool", f"{k}: type debe ser bool"


def test_las_tres_flags_requieren_master():
    by_key = _by_key()
    for k in _KEYS:
        assert by_key[k].requires == "STACKY_DB_COMPARE_ENABLED", (
            f"{k}: requires debe ser STACKY_DB_COMPARE_ENABLED"
        )


def test_las_tres_flags_categorizadas_en_comparador_bd():
    from services.harness_flags import _CATEGORY_KEYS

    for k in _KEYS:
        assert k in _CATEGORY_KEYS["comparador_bd"], (
            f"{k} no está en _CATEGORY_KEYS['comparador_bd']"
        )


def test_config_expone_las_tres_flags_default_on():
    import config as cfg

    for k in _KEYS:
        assert getattr(cfg.config, k) is True, f"config.{k} debe ser True por default"
