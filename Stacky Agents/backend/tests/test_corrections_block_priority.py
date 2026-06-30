"""Plan 41 F3 — El bloque operator-corrections tiene máxima prioridad."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_corrections_block_is_highest_priority():
    from services.context_enrichment import _BLOCK_PRIORITY, _block_priority
    corr = _block_priority({"id": "operator-corrections"})
    # Debe superar a TODO otro bloque registrado.
    assert corr > max(v for k, v in _BLOCK_PRIORITY.items() if k != "operator-corrections")


def test_preflight_flags_registered():
    from services.harness_flags import FLAG_REGISTRY
    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert by_key["INTENT_PREFLIGHT_ENABLED"].type == "bool"
    assert by_key["INTENT_PREFLIGHT_ENABLED"].group == "preflight"
    assert by_key["INTENT_PREFLIGHT_AUTO_APPROVE"].type == "bool"
    assert by_key["INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF"].type == "float"
