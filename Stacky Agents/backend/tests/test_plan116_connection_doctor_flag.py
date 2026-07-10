"""Plan 116 F2 — flag 5 patas del doctor de conexiones (default OFF, requires panel)."""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from config import config
from services.harness_flags import FLAG_REGISTRY, categorize

_KEY = "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED"


def _spec(key):
    return next(s for s in FLAG_REGISTRY if s.key == key)


def _load_devops_health():
    """Carga api/devops.py aislado (stub del paquete api roto en HEAD por WIP ajeno:
    SyntaxError preexistente en api/devops_servers.py)."""
    if "api" not in sys.modules or not hasattr(sys.modules.get("api"), "__path__"):
        pkg = types.ModuleType("api")
        pkg.__path__ = [str(_BACKEND / "api")]
        sys.modules["api"] = pkg
    helpers = types.ModuleType("api._helpers")
    helpers.current_user = lambda: "op"
    sys.modules["api._helpers"] = helpers
    spec = importlib.util.spec_from_file_location("api.devops", str(_BACKEND / "api" / "devops.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["api.devops"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_flag_registered_in_devops_category():
    assert categorize(_KEY) == "devops"


def test_flag_spec_bool_not_env_only_requires_panel():
    s = _spec(_KEY)
    assert s.type == "bool"
    assert s.env_only is False
    assert s.requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_flag_default_off_in_config():
    # Sin STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED en el env → atributo False.
    from config import Config
    assert Config().STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED is False


def test_health_payload_has_connection_doctor_key(monkeypatch):
    devops = _load_devops_health()
    monkeypatch.setattr(config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", True, raising=False)
    assert devops._health_payload()["connection_doctor_enabled"] is True
    monkeypatch.setattr(config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", False, raising=False)
    assert devops._health_payload()["connection_doctor_enabled"] is False
