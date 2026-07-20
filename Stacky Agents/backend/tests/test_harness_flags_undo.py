"""Plan 185 F0 — Flag de arnés STACKY_UNDO_UNIVERSAL_ENABLED (kill-switch, default ON).

Espeja la forma de acceso al registry del test vecino test_harness_flags_requires.py
(import de services.harness_flags, consulta de FLAG_REGISTRY) — NO usa
getattr(config, FLAG) sobre el módulo (gotcha: devuelve siempre el default).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

FLAG = "STACKY_UNDO_UNIVERSAL_ENABLED"


def test_undo_flag_exists_default_on():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert FLAG in by_key, f"{FLAG} no está registrada en FLAG_REGISTRY"
    spec = by_key[FLAG]
    assert spec.type == "bool"
    assert spec.default is True


def test_undo_flag_in_curated_defaults_on():
    # _CURATED_DEFAULTS_ON canónico vive en el test vecino (fuente de verdad del
    # test_default_known_only_for_curated). Espejamos ese import.
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert FLAG in _CURATED_DEFAULTS_ON


def test_undo_flag_no_requires():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert by_key[FLAG].requires is None


def test_undo_flag_is_categorized():
    from services.harness_flags import categorize

    assert categorize(FLAG) == "interfaz_ui"
