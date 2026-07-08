"""tests/test_plan105_remote_console_flag.py — Plan 105 F0.

Tests de flag + health + requires para la consola remota DevOps.
"""
from __future__ import annotations

import os

import pytest

import config as _config
import services.harness_flags as _harness_flags
import services.harness_flags_help as _harness_flags_help
from api.devops import _health_payload


class TestF0FlagDefaults:
    """F0 — Test que la flag existe y default OFF."""

    def test_f0_flag_default_off(self, monkeypatch):
        """La flag default es False con entorno limpio."""
        # Limpiar environment
        for k in list(os.environ.keys()):
            if "STACKY_DEVOPS_REMOTE_CONSOLE" in k:
                monkeypatch.delenv(k, raising=False)

        # Reload config (patrón de test_plan104_*)
        import importlib
        importlib.reload(_config)
        assert _config.config.STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED is False

    def test_f0_flag_registered_in_registry(self):
        """La key existe en el registry con env_only=False y requires correcto."""
        by_key = {s.key: s for s in _harness_flags.FLAG_REGISTRY}
        spec = by_key["STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED"]
        assert spec.env_only is False  # editable por UI
        assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"  # R4 profundidad-1

    def test_f0_flag_has_plain_help(self):
        """La key existe en el dict de help (para HarnessFlagsPanel)."""
        assert "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED" in _harness_flags_help.PLAIN_HELP

    def test_f0_health_exposes_remote_console(self):
        """GET /api/devops/health incluye remote_console_enabled."""
        payload = _health_payload()
        assert "remote_console_enabled" in payload
        assert isinstance(payload["remote_console_enabled"], bool)
