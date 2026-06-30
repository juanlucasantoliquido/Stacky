"""Plan 46 F1 — Flag STACKY_OPERATIONAL_HEALTH_ENABLED en el registry."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_operational_health_flag_is_registered():
    from services.harness_flags import FLAG_REGISTRY
    assert "STACKY_OPERATIONAL_HEALTH_ENABLED" in [f.key for f in FLAG_REGISTRY]


def test_operational_health_flag_is_bool_and_global():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(f for f in FLAG_REGISTRY if f.key == "STACKY_OPERATIONAL_HEALTH_ENABLED")
    assert spec.type == "bool"
    assert spec.group == "global"
    assert spec.env_only is True
