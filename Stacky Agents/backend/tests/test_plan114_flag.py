"""Plan 114 F0 — Flag `STACKY_DOCS_STALENESS_ENABLED` (default OFF, editable por UI)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config
from services.harness_flags import FLAG_REGISTRY, categorize

_MASTER = "STACKY_DOCS_STALENESS_ENABLED"


def _spec(key):
    return next(s for s in FLAG_REGISTRY if s.key == key)


def test_flag_default_on():
    # Activación operador 2026-07-10: capacidad opt-in, default ON.
    assert categorize(_MASTER) == "capacidades_optin"
    assert config.STACKY_DOCS_STALENESS_ENABLED is True


def test_flag_requires_graph():
    s = _spec(_MASTER)
    assert s.requires == "STACKY_DOCS_GRAPH_ENABLED"
    assert s.type == "bool"
    assert s.env_only is False


def test_flag_has_plain_help():
    from services.harness_flags_help import PLAIN_HELP
    assert _MASTER in PLAIN_HELP
