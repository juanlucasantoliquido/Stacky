"""Plan 148 F2 — Flag master STACKY_INTEGRATION_DEGRADATION_ENABLED (patron triple)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_plan148_flag_default_on():
    # Entorno limpio: el archivo corre aislado (pytest por archivo, regla del repo),
    # sin STACKY_INTEGRATION_DEGRADATION_ENABLED seteado -> debe resolver al default.
    assert "STACKY_INTEGRATION_DEGRADATION_ENABLED" not in os.environ
    from config import Config
    assert Config().STACKY_INTEGRATION_DEGRADATION_ENABLED is True
