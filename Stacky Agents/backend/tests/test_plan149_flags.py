"""Plan 149 — Flags nuevas (patrón triple): STACKY_TYPED_ERROR_ENVELOPE_ENABLED (F0)
y STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED (F4)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_typed_error_flag_registered_and_on():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert "STACKY_TYPED_ERROR_ENVELOPE_ENABLED" in by_key
    assert by_key["STACKY_TYPED_ERROR_ENVELOPE_ENABLED"].default is True


def test_typed_error_flag_default_in_config():
    assert "STACKY_TYPED_ERROR_ENVELOPE_ENABLED" not in os.environ
    from config import Config
    assert Config().STACKY_TYPED_ERROR_ENVELOPE_ENABLED is True


def test_intake_quarantine_surface_flag_registered_and_on():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED" in by_key
    assert by_key["STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED"].default is True


def test_intake_quarantine_surface_flag_default_in_config():
    assert "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED" not in os.environ
    from config import Config
    assert Config().STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED is True
