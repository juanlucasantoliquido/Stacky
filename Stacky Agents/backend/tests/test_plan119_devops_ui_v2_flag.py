"""Plan 119 F0 — flag del shell DevOps minimalista (default OFF, requires panel).

Replica el molde de test_plan116_connection_doctor_flag.py / test_plan110_pr_review_flags.py:
registro + categoría devops + editable por UI + requires profundidad-1 al master del panel +
default OFF en config.py + surface aditiva en /api/devops/health.
"""
from __future__ import annotations

import importlib

from services.harness_flags import FLAG_REGISTRY, categorize, _CATEGORY_KEYS

_KEY = "STACKY_DEVOPS_UI_V2_ENABLED"


def _spec(key):
    return next(s for s in FLAG_REGISTRY if s.key == key)


def test_flag_registered_in_devops_category():
    assert _spec(_KEY) is not None, f"{_KEY} no está en FLAG_REGISTRY"
    assert categorize(_KEY) == "devops"
    assert _KEY in _CATEGORY_KEYS["devops"]


def test_flag_spec_bool_editable_by_ui_requires_panel():
    s = _spec(_KEY)
    assert s.type == "bool"
    assert s.env_only is False
    assert s.requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_flag_no_explicit_default_not_curated():
    """SIN default= (gotcha Plan 63): solo _CURATED_DEFAULTS_ON puede declarar default ON."""
    assert _spec(_KEY).default is None
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    assert _KEY not in _CURATED_DEFAULTS_ON


def test_flag_default_off_in_config(monkeypatch):
    monkeypatch.delenv(_KEY, raising=False)
    import config as config_module
    importlib.reload(config_module)
    try:
        assert config_module.config.STACKY_DEVOPS_UI_V2_ENABLED is False
    finally:
        importlib.reload(config_module)


def test_health_payload_has_ui_v2_key(monkeypatch):
    # NOTA: re-importar `config` (módulo) en vez de bindear la instancia a nivel de módulo del
    # test — otro test de este archivo hace importlib.reload(config) y reasigna el singleton
    # config.config; leerlo fresco acá evita parchear una instancia vieja que api.devops ya no usa.
    import config as config_module
    import api.devops as devops

    monkeypatch.setattr(config_module.config, "STACKY_DEVOPS_UI_V2_ENABLED", False, raising=False)
    assert devops._health_payload()["ui_v2_enabled"] is False

    monkeypatch.setattr(config_module.config, "STACKY_DEVOPS_UI_V2_ENABLED", True, raising=False)
    assert devops._health_payload()["ui_v2_enabled"] is True
