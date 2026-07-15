"""Plan 122 F0 — Flags del arnés para el Comparador de BD entre ambientes.

Ver Stacky Agents/docs/122_PLAN_DB_COMPARE_NUCLEO_AMBIENTES_CONEXION_READONLY_Y_SNAPSHOT.md
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_master_flag_declared_default_on():
    """Promovido a default ON 2026-07-15 (directiva operador: "dejá todo ON, la
    config se hace después desde la UI"). Read-only hasta que el operador
    registre un ambiente en EnvironmentsPanel; sin ambientes registrados la
    tab queda visible pero vacía (no dispara ninguna conexión sola)."""
    from services.harness_flags import FLAG_REGISTRY
    from config import Config

    by_key = {s.key: s for s in FLAG_REGISTRY}
    spec = by_key["STACKY_DB_COMPARE_ENABLED"]
    assert spec.type == "bool"
    assert Config.STACKY_DB_COMPARE_ENABLED is True


def test_timeout_flag_bounds():
    from services.harness_flags import FLAG_REGISTRY
    from config import Config

    by_key = {s.key: s for s in FLAG_REGISTRY}
    spec = by_key["STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC"]
    assert spec.type == "int"
    assert spec.min_value == 1
    assert spec.max_value == 120
    assert spec.requires == "STACKY_DB_COMPARE_ENABLED"
    # spec.default se deja en None a propósito (ver comentario en harness_flags.py):
    # default_is_known() trata cualquier default no-None como "curado" y exige alta
    # en _CURATED_DEFAULTS_ON, set reservado a promociones bool. El valor real "10"
    # se verifica vía Config, no vía spec.default.
    assert spec.default is None
    assert Config.STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC == 10


def test_category_comparador_bd_exists():
    from services.harness_flags import FLAG_CATEGORIES, _CATEGORY_KEYS

    cat_ids = {c.id for c in FLAG_CATEGORIES}
    assert "comparador_bd" in cat_ids
    assert "STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC" in _CATEGORY_KEYS["comparador_bd"]
    assert "STACKY_DB_COMPARE_ENABLED" in _CATEGORY_KEYS["capacidades_optin"]
