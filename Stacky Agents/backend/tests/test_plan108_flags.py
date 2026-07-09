"""tests/test_plan108_flags.py — Plan 108 F1: flag STACKY_DEVOPS_REMOTE_TARGET_ENABLED."""
from __future__ import annotations

import pytest

import config as _config
from services.harness_flags import FLAG_REGISTRY, FlagSpec, _CATEGORY_KEYS
from services.harness_flags import _REGISTRY_INDEX


class TestPlan108Flags:
    """Tests F1 — flag STACKY_DEVOPS_REMOTE_TARGET_ENABLED."""

    def test_flag_default_off(self):
        """La flag es False por default (sin env var)."""
        # Por defecto sin env var es False
        assert _config.config.STACKY_DEVOPS_REMOTE_TARGET_ENABLED is False

    def test_flag_registered_devops_category(self):
        """La flag está registrada en la categoría devops."""
        devops_keys = _CATEGORY_KEYS.get("devops", [])
        assert "STACKY_DEVOPS_REMOTE_TARGET_ENABLED" in devops_keys

    def test_flag_requires_panel_master(self):
        """La flag requiere STACKY_DEVOPS_PANEL_ENABLED (R4 profundidad-1)."""
        spec = _REGISTRY_INDEX.get("STACKY_DEVOPS_REMOTE_TARGET_ENABLED")
        assert spec is not None, "Flag no registrada en _REGISTRY_INDEX"
        assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"

    def test_health_exposes_remote_target(self):
        """GET /api/devops/health expone remote_target_enabled."""
        # Usar cliente Flask
        from api.devops import _health_payload
        payload = _health_payload()
        assert "remote_target_enabled" in payload
        # Por default es False
        assert payload["remote_target_enabled"] is False

    def test_flag_editable_from_ui(self):
        """La flag es editable desde UI (env_only=False)."""
        spec = _REGISTRY_INDEX.get("STACKY_DEVOPS_REMOTE_TARGET_ENABLED")
        assert spec is not None
        assert spec.env_only is False
