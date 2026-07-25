"""Plan 239 F0 — las 6+1 patas de STACKY_DEVOPS_COCKPIT_ENABLED y la promoción del 119.

Molde: test_plan119_devops_ui_v2_flag.py (registro + categoría devops + editable por UI +
requires profundidad-1 al master del panel + default en config.py + surface en /api/devops/health).
La 7ª pata (alta en _CURATED_DEFAULTS_ON) es obligatoria porque la FlagSpec lleva default=True.
"""
from __future__ import annotations

import importlib

import pytest

from services.harness_flags import FLAG_REGISTRY, categorize, _CATEGORY_KEYS

_KEY = "STACKY_DEVOPS_COCKPIT_ENABLED"
_UI_V2 = "STACKY_DEVOPS_UI_V2_ENABLED"


def _spec(key):
    return next((s for s in FLAG_REGISTRY if s.key == key), None)


@pytest.fixture
def app_panel_on():
    """App con el master del panel encendido (no toca el resto de las flags)."""
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_PANEL_ENABLED", False)
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = original


# ── Pata 2 — categoría ───────────────────────────────────────────────────────
def test_cockpit_flag_en_categoria_devops():
    assert _spec(_KEY) is not None, f"{_KEY} no está en FLAG_REGISTRY"
    assert categorize(_KEY) == "devops"
    assert _KEY in _CATEGORY_KEYS["devops"]


# ── Pata 3 — FlagSpec ────────────────────────────────────────────────────────
def test_cockpit_flag_tiene_flagspec():
    s = _spec(_KEY)
    assert s.type == "bool"
    assert s.default is True, "default=True es lo que hace que la flag nazca ON"
    assert s.env_only is False, "el operador la tiene que poder tocar por UI"


# ── Pata 4 — ayuda llana ─────────────────────────────────────────────────────
def test_cockpit_flag_tiene_help_llano():
    from services.harness_flags_help import PLAIN_HELP

    h = PLAIN_HELP.get(_KEY)
    assert h is not None, f"falta la ayuda llana de {_KEY}"
    for campo in ("what", "on_effect", "off_effect", "example"):
        valor = getattr(h, campo)
        assert isinstance(valor, str) and valor.strip(), f"{campo} vacío en la ayuda de {_KEY}"


# ── Pata 7 — mapa congelado de requires ──────────────────────────────────────
def test_cockpit_flag_requires_panel():
    assert _spec(_KEY).requires == "STACKY_DEVOPS_PANEL_ENABLED"


# ── Pata 1 — default ON en config.py ─────────────────────────────────────────
def test_cockpit_default_on(monkeypatch):
    monkeypatch.delenv(_KEY, raising=False)
    import config as config_module
    importlib.reload(config_module)
    try:
        assert config_module.config.STACKY_DEVOPS_COCKPIT_ENABLED is True
    finally:
        importlib.reload(config_module)


# ── Pata 5 — surface en /api/devops/health ───────────────────────────────────
def test_health_expone_cockpit_enabled(app_panel_on):
    client = app_panel_on.test_client()
    resp = client.get("/api/devops/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "cockpit_enabled" in data
    assert isinstance(data["cockpit_enabled"], bool)


def test_health_cockpit_off(app_panel_on, monkeypatch):
    import config as config_module

    monkeypatch.setattr(config_module.config, _KEY, False, raising=False)
    client = app_panel_on.test_client()
    resp = client.get("/api/devops/health")
    assert resp.status_code == 200, "health es SIEMPRE 200, con la flag como esté"
    assert resp.get_json()["cockpit_enabled"] is False


# ── KPI-3 — promoción del plan 119 ───────────────────────────────────────────
def test_ui_v2_default_on(monkeypatch):
    """KPI-3: la presentación profesional del plan 119 es la de fábrica."""
    monkeypatch.delenv(_UI_V2, raising=False)
    import config as config_module
    importlib.reload(config_module)
    try:
        assert config_module.config.STACKY_DEVOPS_UI_V2_ENABLED is True
    finally:
        importlib.reload(config_module)


# ── Paridad estructural bootstrap ↔ health ───────────────────────────────────
def test_bootstrap_health_paridad(app_panel_on, monkeypatch):
    """El health embebido en /bootstrap trae las MISMAS keys que /health.

    Precondiciones declaradas (si no, el rojo sería por motivos ajenos al plan):
      - /bootstrap es 404 con STACKY_DEVOPS_BOOTSTRAP_ENABLED OFF ⇒ se fuerza a True;
      - /bootstrap es 400 sin ?project= ⇒ se pide con un project cualquiera.
    """
    import api.devops as devops
    import config as config_module

    monkeypatch.setattr(config_module.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", True, raising=False)
    client = app_panel_on.test_client()
    resp = client.get("/api/devops/bootstrap?project=paridad-plan239")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    embedded = resp.get_json()["health"]
    assert set(embedded.keys()) == set(devops._health_payload().keys())
    assert "cockpit_enabled" in embedded
