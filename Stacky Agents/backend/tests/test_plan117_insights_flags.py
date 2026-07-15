"""Plan 117 F0 — flags del arnés + defaults en config (5 flags, default OFF)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config
from services.harness_flags import FLAG_REGISTRY, categorize

_MASTER = "STACKY_LOCAL_INSIGHTS_ENABLED"
_CHILDREN = (
    "STACKY_LOCAL_INSIGHTS_SWEEP_SEC",
    "STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE",
    "STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS",
    "STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED",
)
_ALL = (_MASTER,) + _CHILDREN


def _spec(key):
    return next(s for s in FLAG_REGISTRY if s.key == key)


def test_flags_registered():
    keys = {s.key for s in FLAG_REGISTRY}
    for k in _ALL:
        assert k in keys, k
        assert categorize(k) == "avanzado", k


def test_master_has_no_requires():
    assert _spec(_MASTER).requires in (None, "")


def test_children_require_master():
    for k in _CHILDREN:
        assert _spec(k).requires == _MASTER, k


def test_numeric_bounds():
    assert (_spec("STACKY_LOCAL_INSIGHTS_SWEEP_SEC").min_value,
            _spec("STACKY_LOCAL_INSIGHTS_SWEEP_SEC").max_value) == (30, 3600)
    assert (_spec("STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE").min_value,
            _spec("STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE").max_value) == (1, 20)
    assert (_spec("STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS").min_value,
            _spec("STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS").max_value) == (1, 90)


def test_no_explicit_default_on_numeric_children():
    """Los 3 hijos numéricos nunca declaran default en el spec (valor real vive
    en Config, mismo gotcha que STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC)."""
    for k in (
        "STACKY_LOCAL_INSIGHTS_SWEEP_SEC",
        "STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE",
        "STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS",
    ):
        assert _spec(k).default is None, k


def test_master_and_narrative_default_on():
    """Promovidos a default ON 2026-07-15 (directiva operador: requiere modelo
    local/Ollama instalado, pero eso se configura después desde la UI; sin
    modelo local disponible el endpoint degrada, no revienta)."""
    assert _spec(_MASTER).default is True
    assert _spec("STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED").default is True


def test_config_defaults():
    assert config.STACKY_LOCAL_INSIGHTS_ENABLED is True
    assert config.STACKY_LOCAL_INSIGHTS_SWEEP_SEC == 180
    assert config.STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE == 3
    assert config.STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS == 7
    assert config.STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED is True
