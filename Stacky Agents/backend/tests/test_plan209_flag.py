"""Plan 209 F0 — Flag STACKY_VALIDATION_PLAYBOOK_ENABLED (default ON, editable por UI)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_KEY = "STACKY_VALIDATION_PLAYBOOK_ENABLED"


def test_flag_registrada():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

    spec = next((s for s in FLAG_REGISTRY if s.key == _KEY), None)
    assert spec is not None, f"{_KEY} no está en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.env_only is False, "debe ser editable desde la UI (HarnessFlagsPanel)"
    assert _KEY in _CATEGORY_KEYS["calidad_verificacion"]


def test_flag_default_on(monkeypatch):
    from config import config as cfg
    from services.validation_playbook import flag_enabled

    assert getattr(cfg, _KEY) is True
    assert flag_enabled() is True

    monkeypatch.setattr(cfg, _KEY, False, raising=False)
    assert flag_enabled() is False, (
        "flag_enabled debe leer la INSTANCIA config.config, no el módulo"
    )


def test_flag_en_curated():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert _KEY in _CURATED_DEFAULTS_ON
