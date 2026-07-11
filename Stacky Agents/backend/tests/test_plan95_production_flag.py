"""
Plan 95 F0 — Flag STACKY_DEVOPS_PRODUCTION_ENABLED (6 patas).
Tests patrón de flag del arnés: registro, categoría, help, requires, default OFF.
"""

import pytest
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

_KEY = "STACKY_DEVOPS_PRODUCTION_ENABLED"


def _spec():
    return next((s for s in FLAG_REGISTRY if s.key == _KEY), None)


def test_f0_flag_in_registry():
    """F0 — La flag está en FLAG_REGISTRY con atributos correctos."""
    spec = _spec()
    assert spec is not None, f"{_KEY} no está en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.env_only is False, "env_only debe ser False (editable por UI)"
    assert spec.default is True, "default debe ser True (activación operador 2026-07-09, curada en _CURATED_DEFAULTS_ON)"
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"
    assert spec.group == "global"
    assert spec.label, "label debe estar presente (visible en UI)"
    assert spec.description, "description debe estar presente"
    assert "Merge Request" in spec.description or "Pull Request" in spec.description, \
        "description debe mencionar MR/PR"


def test_f0_flag_in_category_devops():
    """F0 — La flag está en la categoría devops."""
    assert _KEY in _CATEGORY_KEYS["devops"]


def test_f0_config_default_on(monkeypatch):
    """F0 — Default ON (config.py lee true si no está seteada; activación operador 2026-07-09)."""
    monkeypatch.delenv(_KEY, raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_DEVOPS_PRODUCTION_ENABLED is True


def test_f0_flag_has_plain_help():
    """F0 — La flag tiene PlainHelp registrado."""
    assert _KEY in PLAIN_HELP, f"No hay PlainHelp para {_KEY}"


def test_f0_harness_defaults_contains_flag():
    """F0 — harness_defaults.env contiene la línea con false."""
    backend_root = Path(__file__).parent.parent
    defaults_path = backend_root / "harness_defaults.env"
    assert defaults_path.exists()
    content = defaults_path.read_text(encoding="utf-8")
    assert "STACKY_DEVOPS_PRODUCTION_ENABLED=false" in content


def test_f0_flag_requires_edge_in_requires_map():
    """F0 — Arista PRODUCTION → PANEL en _REQUIRES_MAP_FROZEN (C1 del plan)."""
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN
    assert _KEY in _REQUIRES_MAP_FROZEN, \
        f"Falta arista {_KEY} en _REQUIRES_MAP_FROZEN"
    assert _REQUIRES_MAP_FROZEN[_KEY] == "STACKY_DEVOPS_PANEL_ENABLED", \
        "Arista debe apuntar a STACKY_DEVOPS_PANEL_ENABLED"


def test_f0_flag_no_regression():
    """F0 — No-regresión: meta-tests de flags intactos."""
    from tests.test_harness_flags_requires import test_requires_map_is_frozen
    test_requires_map_is_frozen()  # No debe lanzar
