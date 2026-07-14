"""Plan 121 F0 — flags del centinela de egreso + defaults en config (4 flags, default OFF)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config
from services.harness_flags import FLAG_REGISTRY, categorize

_MASTER = "STACKY_EGRESS_SENTINEL_ENABLED"
_CHILDREN = (
    "STACKY_EGRESS_SENTINEL_MAX_PER_CYCLE",
    "STACKY_EGRESS_SENTINEL_LOOKBACK_DAYS",
    "STACKY_EGRESS_SENTINEL_MAX_CHARS",
)
_ALL = (_MASTER,) + _CHILDREN


def _spec(key):
    return next(s for s in FLAG_REGISTRY if s.key == key)


def test_sentinel_flags_registered():
    keys = {s.key for s in FLAG_REGISTRY}
    for k in _ALL:
        assert k in keys, k
        assert categorize(k) == "avanzado", k


def test_master_has_no_requires():
    assert _spec(_MASTER).requires in (None, "")


def test_sentinel_children_require_master():
    for k in _CHILDREN:
        assert _spec(k).requires == _MASTER, k


def test_sentinel_int_bounds():
    assert (_spec("STACKY_EGRESS_SENTINEL_MAX_PER_CYCLE").min_value,
            _spec("STACKY_EGRESS_SENTINEL_MAX_PER_CYCLE").max_value) == (1, 20)
    assert (_spec("STACKY_EGRESS_SENTINEL_LOOKBACK_DAYS").min_value,
            _spec("STACKY_EGRESS_SENTINEL_LOOKBACK_DAYS").max_value) == (1, 90)
    assert (_spec("STACKY_EGRESS_SENTINEL_MAX_CHARS").min_value,
            _spec("STACKY_EGRESS_SENTINEL_MAX_CHARS").max_value) == (0, 200000)


def test_no_explicit_default_on_new_flags():
    for k in _ALL:
        assert _spec(k).default is None, k


def test_sentinel_master_default_off():
    assert config.STACKY_EGRESS_SENTINEL_ENABLED is False
    assert config.STACKY_EGRESS_SENTINEL_MAX_PER_CYCLE == 3
    assert config.STACKY_EGRESS_SENTINEL_LOOKBACK_DAYS == 7
    assert config.STACKY_EGRESS_SENTINEL_MAX_CHARS == 24000
