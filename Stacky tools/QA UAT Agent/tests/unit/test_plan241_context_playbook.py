"""test_plan241_context_playbook.py — Plan 241 F4.

FrmDetalleClie.aspx SOLO se abre con un cliente seleccionado, y el enlace real
lleva un ?q= ENCRIPTADO POR SESION que no se puede reconstruir. El contexto se
gana NAVEGANDO (click en la fila de la agenda), no sintetizando URLs.
"""
import json

import pytest

import playbook_synthesizer as ps
from playbook_synthesizer import (
    ensure_playbook_with_context, build_context_playbook, DEFAULT_ROW_SELECTOR,
)


def _fake_ui_map():
    return {
        "ok": True,
        "screen": "FrmDetalleClie.aspx",
        "elements": [
            {"alias_semantic": "panel_datos_cliente", "id": "pnlDatosCliente",
             "kind": "div", "label": "Datos del Cliente",
             "selector_recommended": "#pnlDatosCliente",
             "fallback_selectors": ["#pnlDatosCliente"], "robustness": "high"},
            {"alias_semantic": "grid_telefonos", "id": "gvTelefonos",
             "kind": "table", "label": "Telefonos",
             "selector_recommended": "#gvTelefonos",
             "fallback_selectors": ["#gvTelefonos"], "robustness": "high"},
        ],
    }


def test_declara_requires_context():
    pb = build_context_playbook("FrmDetalleClie.aspx", anchor="#pnlDatosCliente")
    assert pb["requires_context"] is True
    assert pb["target_screen"] == "FrmDetalleClie.aspx"


def test_navigation_steps_sin_q_param():
    """Ratchet del Plan 240: ningun string del playbook contiene ?q=."""
    pb = build_context_playbook("FrmDetalleClie.aspx", anchor="#pnlDatosCliente")
    assert ps._has_q_param(pb) is False
    assert "?q=" not in json.dumps(pb)
    # Y jamas un goto directo a la pantalla de destino.
    gotos = [s for s in pb["navigation_steps"] if s.get("action") == "goto"]
    assert all(s.get("screen") != "FrmDetalleClie.aspx" for s in gotos)


def test_click_en_fila_antes_del_wait():
    pb = build_context_playbook("FrmDetalleClie.aspx", anchor="#pnlDatosCliente")
    actions = [s.get("action") for s in pb["navigation_steps"]]
    assert actions[0] == "goto"
    assert "click" in actions
    assert actions.index("click") < actions.index("waitFor")
    click_step = next(s for s in pb["navigation_steps"] if s.get("action") == "click")
    assert click_step["selector"] == DEFAULT_ROW_SELECTOR


def test_sin_grilla_devuelve_error_honesto(monkeypatch, tmp_path):
    """Fake sin filas => ok False con error explicito. NO inventa un ancla."""
    def _fake_harvest(screen, **kwargs):
        return {"ok": False, "error": "GRID_EMPTY: la agenda no tiene filas",
                "anchor": None, "ui_map": None, "landing_url": None}
    monkeypatch.setattr(ps, "_harvest_screen_with_context", _fake_harvest)
    res = ensure_playbook_with_context(
        "FrmDetalleClie.aspx", playbooks_dir=tmp_path, ui_maps_dir=tmp_path)
    assert res["ok"] is False
    assert res["anchor"] is None
    assert "GRID_EMPTY" in res["error"]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
